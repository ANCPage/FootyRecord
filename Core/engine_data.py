import csv
import glob
import logging
import os
from collections import defaultdict
from typing import Any, Dict

import Core.config as config
from Core.elo_engine import EloEngine
from Core.geometry import xy_to_grid
from Core.models import MatchInfo, TransitionEdge

# Phase 3 (2026-08-26): the profiling math lives in Core.profiler, the
# read-only accessors in Core.queries — DataIngestor is a facade over them.
from Core.profiler import (
    accumulate_match_positions,
)
from Core.profiler import (
    bake_players as _bake_players_impl,
)
from Core.profiler import (
    build_fit_rows as _build_fit_rows_impl,
)
from Core.profiler import (
    fit_calibration as _fit_calibration_impl,
)
from Core.profiler import (
    fit_decay as _fit_decay_impl,
)
from Core.profiler import (
    recombine as _recombine_impl,
)
from Core.queries import (
    average_matrix as _average_matrix_impl,
)
from Core.queries import (
    player_matrix as _player_matrix_impl,
)

logger = logging.getLogger(__name__)

# Bump when profiling semantics change (normalization, decay, grid logic, ...)
# so stale profile caches are rejected (audit E5).
CACHE_VERSION = 8  # v8: per-team POST_ elo-history tails (v7's 2-team tail left
                    # 16/18 teams without a final rating; load path rebuilds the
                    # round index from the tails — get_team_elo was dead post-load)


class DataIngestor:
    def __init__(self, csv_dir: str, db_path: str = None):
        self.csv_dir = csv_dir
        self.db_path = db_path  # one-store DB (None -> default; tests pass a temp path)
        self.match_chains = defaultdict(list)
        self.match_info = {}
        self.team_history = defaultdict(list)
        self.team_positions = defaultdict(list)  # team -> [(m_id, pos_list)]; pos_list[d] = edge->raw weight (distance d from chain end)
        self.match_positions = {}                # m_id -> (h_pos, a_pos)
        self._player_positions = {}              # m_id -> (h_player, a_player) distance-bucketed
        self.team_player_history = defaultdict(list)
        self.actual_winners = {}
        self.actual_match_matrices = {}
        self.match_performance = {} # (match_id) -> {expected, expected_delta, actual}
        self.team_elo_history = defaultdict(list) # team_id -> [(match_id, elo_before_match)]
        self.elo_engine = EloEngine()
        # Phase 1 (2026-08-26): calibration travels with the ingestor — every
        # decision path reads ing.calibration. Shipped fallback until a load
        # replaces it, so the attribute always exists.
        from Core.calibration import Calibration
        self.calibration = Calibration.fallback()

    @staticmethod
    def _cache_fingerprint() -> str:
        """Version stamp for the profile cache (audit E5): rejects pickles built
        by older code OR with different engine settings, even when CSVs haven't
        changed (the stale-cache footgun that bit the E2 normalization change)."""
        import hashlib

        import Core.calibration as cal
        c = config.config
        raw = (f"{CACHE_VERSION}|{c.decay_factor}|{c.window_size}"
               f"|{c.elo_k}|{c.elo_margin_divisor}|{cal.WINDOW_SEASONS}")
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    @staticmethod
    def _csv_fingerprint(files) -> str:
        """Identity of the source data (names + sizes + mtimes) — the pickle
        era's max-mtime check was beatable (any newer file passed); exact
        identity is the robust guard (one-store, 2026-08-11)."""
        import hashlib
        raw = '\n'.join(sorted(f"{os.path.basename(f)}|{os.path.getsize(f)}|{os.path.getmtime(f)}"
                               for f in files))
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    def load_all_data(self, light: bool = False):
        """Load state from the one-store SQLite DB (fingerprint-gated), or
        ingest the CSVs + profile + save (one-store overhaul, 2026-08-11:
        the pickle cache is gone).

        light=True (perf 2026-08-12): skip the chains table on the LOAD
        path — compute/render never need match_chains (profiling does, and
        profiling only runs on the ingest path, which always builds chains).
        """
        import Core.state_store as state_store
        files = glob.glob(os.path.join(self.csv_dir, 'flattened_stats_202*.csv'))
        files = [f for f in files if 'simple' not in f]

        conn = state_store.connect(self.db_path)
        fp = self._cache_fingerprint()
        saved_fp = state_store.meta_get(conn, 'fingerprint')
        csv_fp = self._csv_fingerprint(files) if files else ''
        saved_csv_fp = state_store.meta_get(conn, 'csv_fingerprint') or ''
        if saved_fp == fp and saved_csv_fp == csv_fp:
            logger.info('Loading state from one-store DB (fingerprint match)...')
            state = state_store.load_state(conn, skip_chains=light)
            conn.close()
            self.__dict__.update(state)
            self.elo_engine = EloEngine()
            # The engine's per-round index is not persisted — rebuild it from
            # the stored history (2026-08-25: without this, get_team_elo
            # returned 1500 for every team after any load -> ladder tiers
            # all MID-TABLE, journeys Rating 1500, live elo_diff = 0)
            self.elo_engine.rebuild_index(self.team_elo_history, self.match_info)
            # Tier cutoffs are DERIVED from the live Elo field — rebuild on
            # load, don't trust the stored values (2026-08-26: stale stored
            # cutoffs equalled the boundary team's own rating, so tiers
            # flipped on floating-point epsilons; midpoint cutoffs keep every
            # team clearly inside its tier)
            import Core.calibration as cal
            latest = {}
            for team, hist in getattr(self, 'team_elo_history', {}).items():
                if hist:
                    latest[team] = hist[-1][1]
            if latest:
                self.calibration.tier_cutoffs = cal.compute_tier_cutoffs(list(latest.values()))
            self._skip_profiling = True
            # Phase 1 (2026-08-26): no module global — callers read
            # ing.calibration. Guarantee it exists on this load path.
            if getattr(self, 'calibration', None) is None:
                self.calibration = cal.Calibration.fallback()
            return

        conn.close()
        self._skip_profiling = False
        logger.info(f'Loading {len(files)} seasonal data files...')
        chains_raw = defaultdict(lambda: {'team': '', 'outcome': '', 'grids': [], 'players': [], 'matchId': ''})
        match_scores = defaultdict(lambda: defaultdict(int))
        for f_path in files:
            with open(f_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                seen_stats = set()
                for row_idx, row in enumerate(reader):
                    try:
                        m_id = row['matchId']
                        if not m_id: continue
                        r_num = int(row['round'])
                        if r_num > config.MAX_ROUNDS: continue
                        if m_id not in self.match_info:
                            self.match_info[m_id] = MatchInfo(season=int(row['season']), round=r_num, home=row['homeTeamId'], away=row['awayTeamId'])
                        stat_key = (row['chain_period'], row['stat_periodSeconds'], row['x'], row['y'], row['stat_playerId'])
                        if stat_key in seen_stats: continue
                        seen_stats.add(stat_key)
                        if row.get('stat_description') == 'Goal':
                            match_scores[m_id][row['stat_teamId']] += 6
                        elif row.get('stat_description') == 'Behind':
                            match_scores[m_id][row['stat_teamId']] += 1
                        c_idx = row['chain_index']
                        c_id = f'{m_id}_{c_idx}'
                        chains_raw[c_id]['team'] = row['chain_teamId']
                        chains_raw[c_id]['outcome'] = row['chain_finalState_class']
                        chains_raw[c_id]['matchId'] = m_id
                        if row['x'] and row['y'] and row['stat_class'] in ['POSSESSION', 'DISPOSAL', 'SCORE']:
                            grid_cell = xy_to_grid(row['x'], row['y'], row['venueLength'], row['venueWidth'])
                            if grid_cell:
                                chains_raw[c_id]['grids'].append(grid_cell)
                                chains_raw[c_id]['players'].append(row['stat_playerId'])
                    except Exception as e:
                        logger.warning(f"Skipping malformed row {row_idx} in {f_path}: {e}")
                        continue
        for c_id, chain in chains_raw.items():
            if chain['grids']: self.match_chains[chain['matchId']].append(chain)
        for m_id, scores in match_scores.items():
            h_team = self.match_info[m_id].home; a_team = self.match_info[m_id].away
            h_s, a_s = scores.get(h_team, 0), scores.get(a_team, 0)
            self.match_info[m_id].match_id = m_id
            self.match_info[m_id].home_score = h_s
            self.match_info[m_id].away_score = a_s
            if h_s > a_s: self.actual_winners[m_id] = h_team
            elif a_s > h_s: self.actual_winners[m_id] = a_team
            else: self.actual_winners[m_id] = 'DRAW'

    def profile_all_teams(self):
        if getattr(self, '_skip_profiling', False):
            return

        sorted_matches = sorted(self.match_info.keys(), key=lambda x: (self.match_info[x].season, self.match_info[x].round))
        logger.info('Profiling teams using per-position storage (Option B)...')

        # Pass 1: accumulate DECAY-INDEPENDENT per-position weights
        # (pos_list[d] = raw edge weights at distance d from the chain end).
        for m_id in sorted_matches:
            info = self.match_info[m_id]
            h_pos, a_pos, h_player, a_player = self._accumulate_positions(m_id)
            self.match_positions[m_id] = (h_pos, a_pos)
            self.team_positions[info.home].append((m_id, h_pos))
            self.team_positions[info.away].append((m_id, a_pos))
            self._player_positions[m_id] = (h_player, a_player)

        # Fit decay: maximize net-delta sign agreement with actual results
        # (Elo-free criterion — no circularity). Becomes the ACTIVE decay.
        import Core.calibration as cal
        fitted_decay, fit_acc = self._fit_decay()
        self.fitted_decay = fitted_decay
        # Phase 1: the fitted calibration lives on the ingestor, not a global.
        self.calibration = cal.Calibration(decay_factor=fitted_decay)
        logger.info(f'Decay fitted: {fitted_decay} (delta-sign agreement {100*fit_acc:.1f}%)')

        # Pass 2: expectations + actuals + player history at the FITTED decay
        from Core.engine_core import MatchupEngine
        for m_id in sorted_matches:
            info = self.match_info[m_id]
            h_team, a_team = info.home, info.away

            # Expectations based on previous state (decay-aware reader)
            m_a = self.get_team_average_matrix(h_team, up_to_season=info.season, up_to_round=info.round)
            m_b = self.get_team_average_matrix(a_team, up_to_season=info.season, up_to_round=info.round)
            if m_a and m_b:
                delta_dict = MatchupEngine.calculate_delta(m_a, m_b)
                exp_delta = sum(delta_dict.values())
                # expected_delta: the FULL pre-match delta matrix (walk-forward
                # consistent by construction — computed before this match was
                # appended). Rendered arrows read this from the results DB.
                self.match_performance[m_id] = {'expected': exp_delta,
                                                'expected_delta': delta_dict,
                                                'actual': 0.0}

            # Actuals at the fitted decay
            h_pos, a_pos = self.match_positions[m_id]
            h_mat = self._recombine(h_pos, fitted_decay)
            a_mat = self._recombine(a_pos, fitted_decay)
            self.actual_match_matrices[m_id] = (h_mat, a_mat)
            if m_id in self.match_performance and h_mat and a_mat:
                self.match_performance[m_id]['actual'] = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())

            # Player history baked at the fitted decay
            h_player, a_player = self._player_positions[m_id]
            self.team_player_history[h_team].append((m_id, self._bake_players(h_player, fitted_decay)))
            self.team_player_history[a_team].append((m_id, self._bake_players(a_player, fitted_decay)))

        # Delegate ELO calculation entirely to EloEngine after profiling matrices
        self.team_elo_history = self.elo_engine.compute_elo_history(sorted_matches, self.match_info, self.actual_match_matrices)

        # Dynamic calibration (audit follow-up 2026-08-10): fit the decision
        # coefficients on matches strictly before the latest round, rolling
        # window. Becomes the active calibration for all decision paths.
        self.calibration = self._fit_calibration(cal.WINDOW_SEASONS)
        self.calibration.decay_factor = fitted_decay

        import Core.state_store as state_store
        conn = state_store.connect(self.db_path)
        state_store.save_state(conn, self)
        state_store.meta_set(conn, 'fingerprint', self._cache_fingerprint())
        files = glob.glob(os.path.join(self.csv_dir, 'flattened_stats_202*.csv'))
        files = [f for f in files if 'simple' not in f]
        state_store.meta_set(conn, 'csv_fingerprint', self._csv_fingerprint(files))
        conn.close()
        logger.info("Saving state to one-store DB...")

    def _accumulate_positions(self, m_id):
        """Per-match, per-distance raw edge weights (decay-independent).
        Delegates to Core.profiler (Phase 3)."""
        info = self.match_info[m_id]
        return accumulate_match_positions(self.match_chains[m_id], info.home, info.away)

    @staticmethod
    def _recombine(pos_list, decay):
        """Recombine per-position weights at a decay and apply E2
        normalization (delegates to Core.profiler, Phase 3)."""
        return _recombine_impl(pos_list, decay)

    @staticmethod
    def _bake_players(player_pos, decay):
        """Bake distance-bucketed player credits at a decay (delegates to
        Core.profiler, Phase 3)."""
        return _bake_players_impl(player_pos, decay)

    def _fit_decay(self, candidates=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.9, 1.0)):
        """Fit decay on net-delta sign agreement with actual results
        (delegates to Core.profiler, Phase 3)."""
        return _fit_decay_impl(self.match_positions, self.match_info,
                               self.actual_winners, candidates)

    def _build_fit_rows(self):
        """Rows for calibration fitting (delegates to Core.profiler, Phase 3).
        NOTE: evaluate.py calls this directly — keep the facade."""
        return _build_fit_rows_impl(self.match_info, self.team_elo_history,
                                    self.match_performance)

    def _fit_calibration(self, window_seasons=None):
        """Fit dynamic calibration + distribution-relative tier cutoffs
        (delegates to Core.profiler, Phase 3)."""
        rows = self._build_fit_rows()
        return _fit_calibration_impl(rows, self.team_elo_history, window_seasons)

    def get_team_average_matrix(self, team_id: str, window: int = None, up_to_match_id: str = None, up_to_season: int = None, up_to_round: int = None, return_history_info: bool = False) -> Any:
        # Phase 3: delegates to Core.queries (same semantics, contract-tested)
        return _average_matrix_impl(self.team_positions, self.match_info,
                                    self.calibration, team_id, window,
                                    up_to_match_id, up_to_season, up_to_round,
                                    return_history_info)

    def get_team_player_matrix(self, team_id: str, window: int = None, up_to_match_id: str = None, up_to_season: int = None, up_to_round: int = None) -> Dict[str, Dict[TransitionEdge, float]]:
        # Phase 3: delegates to Core.queries (same semantics, contract-tested)
        return _player_matrix_impl(self.team_player_history, self.match_info,
                                   team_id, window, up_to_match_id,
                                   up_to_season, up_to_round)

    def get_team_elo(self, team_id: str, season: int, round_num: int) -> float:
        return self.elo_engine.get_team_elo(team_id, season, round_num)

    def get_team_tier(self, elo: float) -> str:
        # Phase 1: pass OUR calibration (was the module global)
        return self.elo_engine.get_team_tier(elo, self.calibration)

    def get_league_rankings(self, season: int, round_num: int) -> Dict[str, int]:
        return self.elo_engine.get_league_rankings(season, round_num)
