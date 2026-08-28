import csv
import glob
import logging
import os
from collections import defaultdict
from typing import Any, Dict

import Core.config as config
from Core.elo_engine import EloEngine
from Core.engine_core import Graph
from Core.geometry import xy_to_grid
from Core.models import MatchInfo, TransitionEdge

logger = logging.getLogger(__name__)

# Bump when profiling semantics change (normalization, decay, grid logic, ...)
# so stale profile caches are rejected (audit E5).
CACHE_VERSION = 8  # v8: per-team POST_ elo-history tails (v7's 2-team tail left
                    # 16/18 teams without a final rating; load path rebuilds the
                    # round index from the tails — get_team_elo was dead post-load)

# Distance buckets for per-position storage (Option B): chain edges are
# bucketed by distance-from-end 0..POSITIONS-1; longer chains lump the tail
# into the last bucket. At decay 0.3 the tail contributes <0.01% of weight.
POSITIONS = 12


def _player_factory():
    """Picklable nested-defaultdict factory for per-distance player credits."""
    return defaultdict(float)


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

        Mirrors the old Graph accumulation exactly: own chains +1 as-is,
        opponent chains -1 rotated 180deg; player credits per distance.
        Returns (h_pos, a_pos, h_player, a_player).
        """
        from Core.engine_core import collapse_chain
        info = self.match_info[m_id]
        h_team, a_team = info.home, info.away
        h_pos = [defaultdict(float) for _ in range(POSITIONS)]
        a_pos = [defaultdict(float) for _ in range(POSITIONS)]
        h_player = [defaultdict(_player_factory) for _ in range(POSITIONS)]
        a_player = [defaultdict(_player_factory) for _ in range(POSITIONS)]
        g = Graph('util')

        for chain in self.match_chains[m_id]:
            if chain.get('outcome') != 'SCORE':
                continue
            edges, collapsed_players = collapse_chain(chain)
            if edges is None:
                continue
            n = len(edges)
            cteam = chain['team']
            for i, (start, end) in enumerate(edges, 1):
                d = n - i
                if d >= POSITIONS:
                    d = POSITIONS - 1
                if cteam == h_team:
                    s, e, sign = start, end, 1.0
                else:
                    s, e, sign = g.rotate_node(start), g.rotate_node(end), -1.0
                if s in g.nodes:
                    h_pos[d][TransitionEdge(s, e)] += sign
                if cteam == a_team:
                    s2, e2, sign2 = start, end, 1.0
                else:
                    s2, e2, sign2 = g.rotate_node(start), g.rotate_node(end), -1.0
                if s2 in g.nodes:
                    a_pos[d][TransitionEdge(s2, e2)] += sign2
                inv = list(collapsed_players[i - 1]) if i - 1 < len(collapsed_players) else []
                for p in inv:
                    # INTENT (re-audit 2026-08-12, C4): player credits track
                    # ONLY the team's OWN players — opponent chains are never
                    # credited here, while the edge matrices DO embed opponent
                    # chains (rotated + negated). Deliberate: the "key drivers"
                    # panel shows YOUR players driving YOUR edges; showing
                    # opponents as negative credits would confuse it. The
                    # player layer is a display decomposition, not the model.
                    if cteam == h_team:
                        h_player[d][p][(start, end)] += 1.0
                    else:
                        a_player[d][p][(start, end)] += 1.0
        return h_pos, a_pos, h_player, a_player

    @staticmethod
    def _recombine(pos_list, decay):
        """Recombine per-position weights at a decay and apply E2 normalization."""
        mat = defaultdict(float)
        for d, pos in enumerate(pos_list):
            if not pos:
                continue
            w = decay ** d
            if w == 0.0:
                continue
            for e, v in pos.items():
                mat[e] += w * v
        total = sum(abs(v) for v in mat.values())
        if total <= 0:
            return {}
        return {e: v / total for e, v in mat.items()}

    @staticmethod
    def _bake_players(player_pos, decay):
        """Bake distance-bucketed player credits at a decay (old schema)."""
        baked = {}
        for d, pid_map in enumerate(player_pos):
            w = decay ** d
            if w == 0.0:
                continue
            for pid, edges in pid_map.items():
                dct = baked.setdefault(pid, {})
                for (s, e), v in edges.items():
                    dct[(s, e)] = dct.get((s, e), 0.0) + w * v
        return {k: {TransitionEdge(*edge): score for edge, score in v.items()}
                for k, v in baked.items()}

    def _fit_decay(self, candidates=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.9, 1.0)):
        """Fit decay on net-delta sign agreement with actual results.

        Elo-free (no circularity) and fast: recombination only, no profiling.
        """
        from Core.engine_core import MatchupEngine
        best, best_acc = None, -1.0
        for cand in candidates:
            correct = total = 0
            for m_id, (h_pos, a_pos) in self.match_positions.items():
                info = self.match_info.get(m_id)
                if info is None or m_id.startswith('POST_'):
                    continue
                actual = self.actual_winners.get(m_id)
                if actual not in (info.home, info.away):
                    continue
                h_mat = self._recombine(h_pos, cand)
                a_mat = self._recombine(a_pos, cand)
                if not h_mat or not a_mat:
                    continue
                net = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())
                if (net > 0) == (actual == info.home):
                    correct += 1
                total += 1
            acc = correct / total if total else 0.0
            if acc > best_acc:
                best, best_acc = cand, acc
        return best, best_acc

    def _build_fit_rows(self):
        """Rows for calibration fitting: (season, round, expected net_delta,
        elo diff, actual margin, actual total, actual delta) — all pre-match
        expectations and post-match outcomes, no-lookahead by construction
        (expected deltas were computed before the match was appended)."""
        elo_at = defaultdict(dict)
        for team, hist in self.team_elo_history.items():
            for m_id, elo in hist:
                if m_id.startswith('POST_'):
                    continue
                elo_at[m_id][team] = elo
        rows = []
        for m_id, info in self.match_info.items():
            if m_id.startswith('POST_'):
                continue
            if info.home_score == 0 and info.away_score == 0:
                continue
            # draws INCLUDED (policy B, 2026-08-11): a draw is a margin-0
            # outcome — valid training point, and a guaranteed miss for the
            # winner-only model (a draw can't be tipped)
            perf = self.match_performance.get(m_id, {})
            exp = perf.get('expected')
            if exp is None:
                continue
            eh = elo_at.get(m_id, {}).get(info.home)
            ea = elo_at.get(m_id, {}).get(info.away)
            if eh is None or ea is None:
                continue
            rows.append((info.season, info.round, exp, eh - ea,
                         info.home_score - info.away_score,
                         info.home_score + info.away_score,
                         perf.get('actual', exp),
                         m_id, info.home, info.away))
        return rows

    def _fit_calibration(self, window_seasons=None):
        """Fit dynamic calibration on matches before the latest round, plus
        distribution-relative tier cutoffs from the live Elo field."""
        import Core.calibration as cal
        rows = self._build_fit_rows()
        if not rows:
            return cal.Calibration.fallback()
        cur_season = max(r[0] for r in rows)
        sel = cal.select_window(rows, cur_season, window_seasons)
        label = f'roll{window_seasons}' if window_seasons else 'expanding'
        c = cal.fit_or_fallback(sel, label)
        # Tier cutoffs: top-4/next-4/next-5 from the CURRENT Elo distribution
        # (fixes the E1 watch item — tiers now read as relative strength).
        latest = {}
        for team, hist in self.team_elo_history.items():
            if hist:
                latest[team] = hist[-1][1]
        c.tier_cutoffs = cal.compute_tier_cutoffs(list(latest.values()))
        return c

    def get_team_average_matrix(self, team_id: str, window: int = None, up_to_match_id: str = None, up_to_season: int = None, up_to_round: int = None, return_history_info: bool = False) -> Any:
        if window is None:
            window = config.config.window_size
        # Decay is DYNAMIC (Option B): recombine per-position weights at the
        # active calibration decay (fallback: config bootstrap).
        # Phase 1: read our OWN calibration, not a module global.
        decay = getattr(self.calibration, 'decay_factor', None) or config.config.decay_factor
        history = self.team_positions.get(team_id, [])
        filtered_history = []
        for m_id, pos in history:
            if up_to_match_id and m_id == up_to_match_id: break
            if up_to_season is not None and up_to_round is not None:
                info = self.match_info.get(m_id)
                if info and (info.season > up_to_season or (info.season == up_to_season and info.round >= up_to_round)):
                    continue
            filtered_history.append((m_id, pos))

        history = filtered_history[-window:]
        if not history:
            return ({}, []) if return_history_info else {}

        avg_matrix = defaultdict(float)
        used_matches = []
        for m_id, pos in history:
            info = self.match_info.get(m_id)
            if info:
                used_matches.append(f"R{info.round}_{info.season}")
            else:
                used_matches.append(m_id)
            mat = self._recombine(pos, decay)
            for edge, score in mat.items(): avg_matrix[edge] += score / len(history)

        if return_history_info:
            return dict(avg_matrix), used_matches
        return dict(avg_matrix)

    def get_team_player_matrix(self, team_id: str, window: int = None, up_to_match_id: str = None, up_to_season: int = None, up_to_round: int = None) -> Dict[str, Dict[TransitionEdge, float]]:
        if window is None:
            window = config.config.window_size
        history = self.team_player_history.get(team_id, [])
        filtered_history = []
        for m_id, mat in history:
            if up_to_match_id and m_id == up_to_match_id: break
            if up_to_season is not None and up_to_round is not None:
                info = self.match_info.get(m_id)
                if info and (info.season > up_to_season or (info.season == up_to_season and info.round >= up_to_round)):
                    continue
            filtered_history.append((m_id, mat))

        history = filtered_history[-window:]
        if not history: return {}
        avg_player_matrix = defaultdict(lambda: defaultdict(float))
        for _, p_mat in history:
            for pid, edges in p_mat.items():
                for edge, score in edges.items():
                    avg_player_matrix[pid][edge] += score / len(history)
        return dict(avg_player_matrix)

    def get_team_elo(self, team_id: str, season: int, round_num: int) -> float:
        return self.elo_engine.get_team_elo(team_id, season, round_num)

    def get_team_tier(self, elo: float) -> str:
        # Phase 1: pass OUR calibration (was the module global)
        return self.elo_engine.get_team_tier(elo, self.calibration)

    def get_league_rankings(self, season: int, round_num: int) -> Dict[str, int]:
        return self.elo_engine.get_league_rankings(season, round_num)
