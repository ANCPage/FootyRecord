from models import TransitionEdge, MatchInfo
import csv
import glob
import os
import math
from collections import defaultdict
from typing import List, Dict, Tuple, Any
from engine_core import Graph
import config
from elo_engine import EloEngine

def _get_grid_cell(nx, ny, venue_length, venue_width):
    if nx == "" or ny == "" or not venue_length or not venue_width: return ""
    try:
        nx, ny, venue_length, venue_width = float(nx), float(ny), float(venue_length), float(venue_width)
    except ValueError: return ""
    a = venue_length / 2.0; b = venue_width / 2.0
    u = nx / a; v = ny / b
    r_sq = u**2 + v**2
    if r_sq > 1.0:
        norm = math.sqrt(r_sq); u /= norm; v /= norm
    if u == 0 and v == 0: sx, sy = 0.0, 0.0
    elif abs(u) >= abs(v):
        if u > 0: sx = math.sqrt(u**2 + v**2); sy = sx * (4 / math.pi) * math.atan2(v, u)
        else: sx = -math.sqrt(u**2 + v**2); sy = -sx * (4 / math.pi) * math.atan2(v, -u)
    else:
        if v > 0: sy = math.sqrt(u**2 + v**2); sx = sy * (4 / math.pi) * math.atan2(u, v)
        else: sy = -math.sqrt(u**2 + v**2); sx = -sy * (4 / math.pi) * math.atan2(u, -v)
    col_idx = max(0, min(4, int((sx + 1.0) / 2.0 * 5)))
    row_idx = max(0, min(2, int((sy + 1.0) / 2.0 * 3)))
    return f"{['A', 'B', 'C', 'D', 'E'][col_idx]}{['1', '2', '3'][row_idx]}"

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

    def load_all_data(self):
        import pickle
        cache_dir = os.path.join(self.csv_dir, '.cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'ingestor_state.pkl')
        
        files = glob.glob(os.path.join(self.csv_dir, 'flattened_stats_202*.csv'))
        files = [f for f in files if 'simple' not in f]
        
        if os.path.exists(cache_path):
            cache_mtime = os.path.getmtime(cache_path)
            if all(os.path.getmtime(f) <= cache_mtime for f in files):
                print('Loading data and profiled teams from cache...')
                with open(cache_path, 'rb') as f:
                    state = pickle.load(f)
                self.__dict__.update(state)
                if not hasattr(self, 'elo_engine') or self.elo_engine is None:
                    self.elo_engine = EloEngine()
                    sorted_matches = sorted(self.match_info.keys(), key=lambda x: (self.match_info[x].season, self.match_info[x].round))
                    self.team_elo_history = self.elo_engine.compute_elo_history(sorted_matches, self.match_info, self.actual_match_matrices)
                self._skip_profiling = True
                return
                
        self._skip_profiling = False
        print(f'Loading {len(files)} seasonal data files...')
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
                            grid_cell = _get_grid_cell(row['x'], row['y'], row['venueLength'], row['venueWidth'])
                            if grid_cell:
                                chains_raw[c_id]['grids'].append(grid_cell)
                                chains_raw[c_id]['players'].append(row['stat_playerId'])
                    except Exception as e:
                        print(f"Skipping malformed row {row_idx} in {f_path}: {e}")
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
        print('Profiling teams using integrated edge-based decay logic...')
        
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

        import pickle
        cache_dir = os.path.join(self.csv_dir, '.cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'ingestor_state.pkl')
        print("Saving state to cache...")
        with open(cache_path, 'wb') as f:
            pickle.dump(self.__dict__, f)

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
