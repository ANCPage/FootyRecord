import csv
import glob
import logging
import os
from collections import defaultdict
from typing import Any, Dict

import config
from elo_engine import EloEngine
from engine_core import Graph
from geometry import xy_to_grid
from models import MatchInfo, TransitionEdge

logger = logging.getLogger(__name__)

# Bump when profiling semantics change (normalization, decay, grid logic, ...)
# so stale profile caches are rejected (audit E5).
CACHE_VERSION = 4  # v4: dynamic calibration fitted on cache build (audit follow-up)


class DataIngestor:
    def __init__(self, csv_dir: str):
        self.csv_dir = csv_dir
        self.match_chains = defaultdict(list)
        self.match_info = {}
        self.team_history = defaultdict(list)
        self.team_player_history = defaultdict(list)
        self.actual_winners = {}
        self.actual_match_matrices = {}
        self.match_performance = {} # (match_id) -> {expected_delta: float, actual_delta: float}
        self.team_elo_history = defaultdict(list) # team_id -> [(match_id, elo_before_match)]
        self.elo_engine = EloEngine()

    @staticmethod
    def _cache_fingerprint() -> str:
        """Version stamp for the profile cache (audit E5): rejects pickles built
        by older code OR with different engine settings, even when CSVs haven't
        changed (the stale-cache footgun that bit the E2 normalization change)."""
        import hashlib

        import calibration as cal
        c = config.config
        raw = (f"{CACHE_VERSION}|{c.decay_factor}|{c.time_decay_factor}|{c.window_size}"
               f"|{c.elo_k}|{c.elo_margin_divisor}|{cal.WINDOW_SEASONS}")
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    def load_all_data(self):
        import pickle
        cache_dir = os.path.join(self.csv_dir, '.cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'ingestor_state.pkl')

        files = glob.glob(os.path.join(self.csv_dir, 'flattened_stats_202*.csv'))
        files = [f for f in files if 'simple' not in f]

        if os.path.exists(cache_path):
            cache_mtime = os.path.getmtime(cache_path)
            cache_fresh = all(os.path.getmtime(f) <= cache_mtime for f in files)
            version_ok = False
            payload = None
            try:
                with open(cache_path, 'rb') as f:
                    payload = pickle.load(f)
                version_ok = (isinstance(payload, dict)
                              and payload.get('__cache_version__')
                              == self._cache_fingerprint())
            except Exception:
                version_ok = False
            if cache_fresh and version_ok:
                logger.info('Loading data and profiled teams from cache...')
                self.__dict__.update(payload['state'])
                if not hasattr(self, 'elo_engine') or self.elo_engine is None:
                    self.elo_engine = EloEngine()
                    sorted_matches = sorted(self.match_info.keys(), key=lambda x: (self.match_info[x].season, self.match_info[x].round))
                    self.team_elo_history = self.elo_engine.compute_elo_history(sorted_matches, self.match_info, self.actual_match_matrices)
                self._skip_profiling = True
                # Restore the active calibration fitted at cache-build time
                # (dynamic calibration, audit follow-up 2026-08-10).
                import calibration as cal
                cal.current = getattr(self, 'calibration', cal.Calibration.fallback())
                return

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
                        if r_num > 24: continue
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
        logger.info('Profiling teams using integrated edge-based decay logic...')

        for m_id in sorted_matches:
            info = self.match_info[m_id]
            h_team, a_team = info.home, info.away
            h_graph, a_graph = Graph(h_team), Graph(a_team)

            # Calculate expectations based on previous state
            m_a = self.get_team_average_matrix(h_team, up_to_season=info.season, up_to_round=info.round)
            m_b = self.get_team_average_matrix(a_team, up_to_season=info.season, up_to_round=info.round)
            from engine_core import MatchupEngine
            if m_a and m_b:
                exp_delta = sum(MatchupEngine.calculate_delta(m_a, m_b).values())
                self.match_performance[m_id] = {'expected': exp_delta, 'actual': 0.0}

            h_player_scores = defaultdict(lambda: defaultdict(float))
            a_player_scores = defaultdict(lambda: defaultdict(float))

            for chain in self.match_chains[m_id]:
                has_score = (chain.get('outcome') == 'SCORE')
                if not has_score: continue

                grids = chain['grids']; collapsed = []
                players = chain.get('players', []); collapsed_players = []
                for g, p in zip(grids, players):
                    if not collapsed or collapsed[-1] != g:
                        collapsed.append(g)
                        collapsed_players.append(set([p]))
                    else:
                        collapsed_players[-1].add(p)

                if not collapsed: continue
                edges = []
                for i in range(len(collapsed) - 1): edges.append((collapsed[i], collapsed[i+1]))
                edges.append((collapsed[-1], 'SCORE'))
                n = len(edges)

                for i, (start, end) in enumerate(edges, 1):
                    decay = config.config.decay_factor ** (n - i)
                    h_graph.add_edge_score(start, end, decay, chain['team'])
                    a_graph.add_edge_score(start, end, decay, chain['team'])

                    if decay > 0:
                        inv_players = list(collapsed_players[i-1]) if i-1 < len(collapsed_players) else []
                        for p in inv_players:
                            if chain['team'] == h_team:
                                h_player_scores[p][(start, end)] += decay
                            else:
                                a_player_scores[p][(start, end)] += decay

            h_mat = h_graph.get_edge_matrix()
            a_mat = a_graph.get_edge_matrix()

            # Normalize each match's matrix by total activity weight so deltas
            # measure tactical PATTERN, not attack volume / chain length
            # (audit item E2). sum(abs) preserves the net (own minus opponent)
            # structure while removing the volume scaling.
            h_abs = sum(abs(v) for v in h_mat.values())
            a_abs = sum(abs(v) for v in a_mat.values())
            if h_abs > 0:
                h_mat = {e: v / h_abs for e, v in h_mat.items()}
            if a_abs > 0:
                a_mat = {e: v / a_abs for e, v in a_mat.items()}

            self.team_history[h_team].append((m_id, h_mat))
            self.team_history[a_team].append((m_id, a_mat))
            self.team_player_history[h_team].append((m_id, {k: {TransitionEdge(*edge): score for edge, score in v.items()} for k, v in h_player_scores.items()}))
            self.team_player_history[a_team].append((m_id, {k: {TransitionEdge(*edge): score for edge, score in v.items()} for k, v in a_player_scores.items()}))
            self.actual_match_matrices[m_id] = (h_mat, a_mat)
            if m_id in self.match_performance:
                actual_delta = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())
                self.match_performance[m_id]['actual'] = actual_delta

        # Delegate ELO calculation entirely to EloEngine after profiling matrices
        self.team_elo_history = self.elo_engine.compute_elo_history(sorted_matches, self.match_info, self.actual_match_matrices)

        # Dynamic calibration (audit follow-up 2026-08-10): fit the decision
        # coefficients on matches strictly before the latest round, rolling
        # window. Becomes the active calibration for all decision paths.
        import calibration as cal
        self.calibration = self._fit_calibration(cal.WINDOW_SEASONS)
        cal.current = self.calibration

        import pickle
        cache_dir = os.path.join(self.csv_dir, '.cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'ingestor_state.pkl')
        logger.info("Saving state to cache...")
        with open(cache_path, 'wb') as f:
            pickle.dump({'__cache_version__': self._cache_fingerprint(),
                         'state': self.__dict__}, f)

    def _build_fit_rows(self):
        """Rows for calibration fitting: (season, round, expected net_delta,
        elo diff, actual margin, actual total) — all pre-match expectations
        and post-match outcomes, no-lookahead by construction (expected deltas
        were computed before the match was appended to history)."""
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
            if info.home_score == info.away_score:
                continue  # draws excluded, consistent with evaluation
            exp = self.match_performance.get(m_id, {}).get('expected')
            if exp is None:
                continue
            eh = elo_at.get(m_id, {}).get(info.home)
            ea = elo_at.get(m_id, {}).get(info.away)
            if eh is None or ea is None:
                continue
            rows.append((info.season, info.round, exp, eh - ea,
                         info.home_score - info.away_score,
                         info.home_score + info.away_score))
        return rows

    def _fit_calibration(self, window_seasons=None):
        """Fit dynamic calibration on matches before the latest round."""
        import calibration as cal
        rows = self._build_fit_rows()
        if not rows:
            return cal.Calibration.fallback()
        cur_season = max(r[0] for r in rows)
        sel = cal.select_window(rows, cur_season, window_seasons)
        label = f'roll{window_seasons}' if window_seasons else 'expanding'
        return cal.fit_or_fallback(sel, label)

    def get_team_average_matrix(self, team_id: str, window: int = None, up_to_match_id: str = None, up_to_season: int = None, up_to_round: int = None, return_history_info: bool = False) -> Any:
        if window is None:
            window = config.config.window_size
        history = self.team_history.get(team_id, [])
        filtered_history = []
        for m_id, mat in history:
            if up_to_match_id and m_id == up_to_match_id: break
            if up_to_season is not None and up_to_round is not None:
                info = self.match_info.get(m_id)
                if info and (info.season > up_to_season or (info.season == up_to_season and info.round >= up_to_round)):
                    continue
            filtered_history.append((m_id, mat))

        history = filtered_history[-window:]
        if not history:
            return ({}, []) if return_history_info else {}

        avg_matrix = defaultdict(float)
        used_matches = []
        for m_id, mat in history:
            info = self.match_info.get(m_id)
            if info:
                used_matches.append(f"R{info.round}_{info.season}")
            else:
                used_matches.append(m_id)
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
        return self.elo_engine.get_team_tier(elo)

    def get_league_rankings(self, season: int, round_num: int) -> Dict[str, int]:
        return self.elo_engine.get_league_rankings(season, round_num)
