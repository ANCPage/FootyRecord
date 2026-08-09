import re
import os
import glob

# 1. Update engine_core.py
with open("Core/engine_core.py", "r") as f:
    core_code = f.read()

# Add imports
core_code = "from models import TransitionEdge, TeamProfile\n" + core_code

# Replace get_edge_matrix return type
core_code = core_code.replace(
    "def get_edge_matrix(self) -> Dict[Tuple[str, str], float]:",
    "def get_edge_matrix(self) -> Dict[TransitionEdge, float]:"
)

# Replace matrix generation loop
old_matrix_loop = """        matrix = {}
        for name, node in self.nodes.items():
            for target, score in node.edges.items():
                matrix[(name, target)] = score
        return matrix"""
new_matrix_loop = """        matrix = {}
        for name, node in self.nodes.items():
            for target, score in node.edges.items():
                matrix[TransitionEdge(name, target)] = score
        return matrix"""
core_code = core_code.replace(old_matrix_loop, new_matrix_loop)

# Update MatchupEngine.calculate_delta
old_delta_sig = """    def calculate_delta(team_a_matrix: Dict[Tuple[str, str], float], 
                        team_b_matrix: Dict[Tuple[str, str], float]) -> Dict[Tuple[str, str], float]:"""
new_delta_sig = """    def calculate_delta(team_a_matrix: Dict[TransitionEdge, float], 
                        team_b_matrix: Dict[TransitionEdge, float]) -> Dict[TransitionEdge, float]:"""
core_code = core_code.replace(old_delta_sig, new_delta_sig)

old_rotate_helper = """        def rotate_edge(edge: Tuple[str, str], g: Graph) -> Tuple[str, str]:
            return (g.rotate_node(edge[0]), g.rotate_node(edge[1]))"""
new_rotate_helper = """        def rotate_edge(edge: TransitionEdge, g: Graph) -> TransitionEdge:
            return TransitionEdge(g.rotate_node(edge.source), g.rotate_node(edge.target))"""
core_code = core_code.replace(old_rotate_helper, new_rotate_helper)

with open("Core/engine_core.py", "w") as f:
    f.write(core_code)

# 2. Update engine_data.py
with open("Core/engine_data.py", "r") as f:
    data_code = f.read()

data_code = "from models import TransitionEdge, MatchInfo\n" + data_code

# Update match_info parsing
old_match_info = """self.match_info[m_id] = {'season': int(row['season']), 'round': r_num, 'home': row['homeTeamId'], 'away': row['awayTeamId']}"""
new_match_info = """self.match_info[m_id] = MatchInfo(season=int(row['season']), round=r_num, home=row['homeTeamId'], away=row['awayTeamId'])"""
data_code = data_code.replace(old_match_info, new_match_info)

# Update sorting matches
old_sorted_matches = """sorted_matches = sorted(self.match_info.keys(), key=lambda x: (self.match_info[x]['season'], self.match_info[x]['round']))"""
new_sorted_matches = """sorted_matches = sorted(self.match_info.keys(), key=lambda x: (self.match_info[x].season, self.match_info[x].round))"""
data_code = data_code.replace(old_sorted_matches, new_sorted_matches)

# Update usages of match_info
data_code = data_code.replace("info['season']", "info.season")
data_code = data_code.replace("info['round']", "info.round")
data_code = data_code.replace("info['home']", "info.home")
data_code = data_code.replace("info['away']", "info.away")
data_code = data_code.replace("self.match_info[m_id]['home']", "self.match_info[m_id].home")
data_code = data_code.replace("self.match_info[m_id]['away']", "self.match_info[m_id].away")

# Update player history keys
old_player_keys = """self.team_player_history[h_team].append((m_id, {k: dict(v) for k, v in h_player_scores.items()}))
            self.team_player_history[a_team].append((m_id, {k: dict(v) for k, v in a_player_scores.items()}))"""
new_player_keys = """self.team_player_history[h_team].append((m_id, {k: {TransitionEdge(*edge): score for edge, score in v.items()} for k, v in h_player_scores.items()}))
            self.team_player_history[a_team].append((m_id, {k: {TransitionEdge(*edge): score for edge, score in v.items()} for k, v in a_player_scores.items()}))"""
data_code = data_code.replace(old_player_keys, new_player_keys)

# Replace Tuple type hints in get_team_player_matrix
data_code = data_code.replace("Dict[str, Dict[Tuple[str, str], float]]", "Dict[str, Dict[TransitionEdge, float]]")

with open("Core/engine_data.py", "w") as f:
    f.write(data_code)

print("Updated Core/engine_data.py and Core/engine_core.py")
