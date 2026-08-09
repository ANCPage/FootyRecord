"""Focus check: does ANY arrow actually drawn (top-20 delta keys, all three panels)
physically span the LFP(E1)->FB(A2) endpoints? Plus direct values for the
suspicious edges in both team matrices."""
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

def phys_of(edge, is_away):
    start, end = edge.source, edge.target
    if is_away:
        ps = g.rotate_node(start); pe = g.rotate_node(end)
        if ps == 'SCORE': ps = 'AWAY_G'
        elif ps == 'AWAY_G': ps = 'SCORE'
        if pe == 'SCORE': pe = 'AWAY_G'
        elif pe == 'AWAY_G': pe = 'SCORE'
    else:
        ps, pe = start, end
    return ps, pe

ingestor = DataIngestor('CSV_DATA')
ingestor.load_all_data()
ingestor.profile_all_teams()
h_id, a_id = 'CD_T80', 'CD_T100'
m_a = ingestor.get_team_average_matrix(h_id)
m_b = ingestor.get_team_average_matrix(a_id)
delta = MatchupEngine.calculate_delta(m_a, m_b)

print("=== direct values for suspicious edges ===")
for label, mat in (("HAWKS matrix_a", m_a), ("NORF matrix_b", m_b)):
    print(f"  {label}: E1->A2 (LFP->FB) = {mat.get(TransitionEdge('E1','A2'),0.0):+.4f}")
    print(f"  {label}: A3->E2 (RBP->FF) = {mat.get(TransitionEdge('A3','E2'),0.0):+.4f}")
print(f"  DELTA:    E1->A2 (LFP->FB) = {delta.get(TransitionEdge('E1','A2'),0.0):+.4f}")
print(f"  DELTA:    A3->E2 (RBP->FF) = {delta.get(TransitionEdge('A3','E2'),0.0):+.4f}")

print()
print("=== TOP-20 delta edges: drawn placement in the DELTA panel ===")
print(f"{'key (home labels)':<24}{'score':>9} {'owner':<6} {'phys drawn':<24} flag")
top20 = sorted(delta.items(), key=lambda x: -abs(x[1]))[:20]
for edge, score in top20:
    is_away = score < 0
    ps, pe = phys_of(edge, is_away)
    span = f"{ZONE[ps]:>9}->{ZONE[pe]:<9}"
    flag = ''
    if ZONE[ps] == 'LFP' and ZONE[pe] == 'FB': flag = '<<< LFP->FB PHYSICAL'
    if ZONE[ps] == 'FB' and ZONE[pe] == 'LFP': flag = '<<< FB->LFP PHYSICAL'
    print(f"  {ZONE[edge.source]:>9}->{ZONE[edge.target]:<10} {score:+9.3f} "
          f"{'NORF' if is_away else 'HAWKS':<6} {span}  {flag}")

print()
print("=== TOP-20 delta keys as drawn in the NORTH PROFILE panel (matrix_b values) ===")
for edge, _ in top20:
    score = m_b.get(edge, 0.0)
    if abs(score) < 0.01:
        continue
    is_away = score < 0
    ps, pe = phys_of(edge, is_away)
    span = f"{ZONE[ps]:>9}->{ZONE[pe]:<9}"
    flag = ''
    if ZONE[ps] == 'LFP' and ZONE[pe] == 'FB': flag = '<<< LFP->FB PHYSICAL'
    if ZONE[ps] == 'FB' and ZONE[pe] == 'LFP': flag = '<<< FB->LFP PHYSICAL'
    print(f"  {ZONE[edge.source]:>9}->{ZONE[edge.target]:<10} {score:+9.3f} "
          f"{'ROT' if is_away else 'DIR':<4} {span}  {flag}")

print()
print("=== TOP-20 delta keys as drawn in the HAWKS PROFILE panel (matrix_a values) ===")
for edge, _ in top20:
    score = m_a.get(edge, 0.0)
    if abs(score) < 0.01:
        continue
    is_away = score < 0
    ps, pe = phys_of(edge, is_away)
    span = f"{ZONE[ps]:>9}->{ZONE[pe]:<9}"
    flag = ''
    if ZONE[ps] == 'LFP' and ZONE[pe] == 'FB': flag = '<<< LFP->FB PHYSICAL'
    if ZONE[ps] == 'FB' and ZONE[pe] == 'LFP': flag = '<<< FB->LFP PHYSICAL'
    print(f"  {ZONE[edge.source]:>9}->{ZONE[edge.target]:<10} {score:+9.3f} "
          f"{'ROT' if is_away else 'DIR':<4} {span}  {flag}")
