"""Audit conclusion table: current (mirrored) vs corrected placement of the
top-20 delta-panel arrows for Hawthorn vs North Melbourne."""
import sys
sys.path.insert(0, 'Core')
from models import TransitionEdge
from engine_core import Graph, MatchupEngine
from engine_data import DataIngestor

ZONE = {
    'A1': 'LBP', 'B1': 'LHB', 'C1': 'LW', 'D1': 'LHF', 'E1': 'LFP',
    'A2': 'FB', 'B2': 'CHB', 'C2': 'C', 'D2': 'CHF', 'E2': 'FF',
    'A3': 'RBP', 'B3': 'RHB', 'C3': 'RW', 'D3': 'RHF', 'E3': 'RFP',
    'SCORE': 'HOME_GOAL', 'AWAY_G': 'AWAY_GOAL',
}
g = Graph("util")

ingestor = DataIngestor('CSV_DATA')
ingestor.load_all_data()
ingestor.profile_all_teams()
h_id, a_id = 'CD_T80', 'CD_T100'
m_a = ingestor.get_team_average_matrix(h_id)
m_b = ingestor.get_team_average_matrix(a_id)
delta = MatchupEngine.calculate_delta(m_a, m_b)

top = sorted(delta.items(), key=lambda x: -abs(x[1]))[:20]
print(f"{'edge (home labels)':<22}{'score':>9} {'owner':<6} {'CURRENT placement':<24} {'CORRECT placement':<24}")
for edge, score in top:
    is_away = score < 0
    s, e = edge.source, edge.target
    # current (vector_renderer): rotate both + swap goal
    cur_s = s if not is_away else g.rotate_node(s)
    cur_e = e if not is_away else g.rotate_node(e)
    if is_away:
        if cur_s == 'SCORE': cur_s = 'AWAY_G'
        elif cur_s == 'AWAY_G': cur_s = 'SCORE'
        if cur_e == 'SCORE': cur_e = 'AWAY_G'
        elif cur_e == 'AWAY_G': cur_e = 'SCORE'
    # corrected: no zone rotation; goal maps to the owner's attacking goal
    fix_s = s
    fix_e = e if not (is_away and e == 'SCORE') else 'AWAY_G'
    print(f"  {ZONE[s]:>9}->{ZONE[e]:<10} {score:+9.3f} {'NORF' if is_away else 'HAWKS':<6} "
          f"{ZONE[cur_s]:>9}->{ZONE[cur_e]:<10}  {ZONE[fix_s]:>9}->{ZONE[fix_e]:<10}")
