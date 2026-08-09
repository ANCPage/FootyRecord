"""Audit continuation: verify NO impossible LFP->FB-style arrows can be drawn
by the current visualizer for Hawthorn vs North Melbourne (R21 G6).

Replicates the exact physical-placement math from vector_renderer.py /
visualize_matchup.py for every edge in every panel, then flags any arrow whose
physical start is in the attacking half and physical end in the defending half
(an "impossible backwards" span) or which spans cross the entire pitch.
"""
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
POS = {
    'A1': (-60, 40), 'B1': (-30, 45), 'C1': (0, 50), 'D1': (30, 45), 'E1': (60, 40),
    'A2': (-70, 0), 'B2': (-35, 0), 'C2': (0, 0), 'D2': (35, 0), 'E2': (70, 0),
    'A3': (-60, -40), 'B3': (-30, -45), 'C3': (0, -50), 'D3': (30, -45), 'E3': (60, -40),
    'SCORE': (85, 0), 'AWAY_G': (-85, 0),
}

g = Graph("util")

def phys_of(edge, is_away):
    """Exact replica of vector_renderer.render_vector placement."""
    start, end = edge.source, edge.target
    if is_away:
        phys_start = g.rotate_node(start)
        phys_end = g.rotate_node(end)
        if phys_start == 'SCORE': phys_start = 'AWAY_G'
        elif phys_start == 'AWAY_G': phys_start = 'SCORE'
        if phys_end == 'SCORE': phys_end = 'AWAY_G'
        elif phys_end == 'AWAY_G': phys_end = 'SCORE'
    else:
        phys_start, phys_end = start, end
    return phys_start, phys_end

def implausible(ps, pe):
    """Flag: start in attacking half (x>0) while end in defending half (x<0),
    or vice versa across the whole pitch — a single-step 'backwards' bomb."""
    x1, _ = POS[ps]; x2, _ = POS[pe]
    if x1 > 5 and x2 < -5:   # forward zone -> defensive zone
        return 'BACKWARDS (forward->defensive)'
    if x1 < -5 and x2 > 5:   # defensive zone -> forward zone (a long kick; ok in AFL but note it)
        return 'LONG KICK (defensive->forward)'
    return None

ingestor = DataIngestor('CSV_DATA')
ingestor.load_all_data()
ingestor.profile_all_teams()

h_id, a_id = 'CD_T80', 'CD_T100'
m_a = ingestor.get_team_average_matrix(h_id)
m_b = ingestor.get_team_average_matrix(a_id)
delta = MatchupEngine.calculate_delta(m_a, m_b)

print("=" * 70)
print("PANEL 3: ABSOLUTE MATCHUP OWNERSHIP (delta) — all 165 edges")
print("=" * 70)
flags = 0
for edge, score in sorted(delta.items(), key=lambda x: -abs(x[1])):
    is_away = score < 0
    ps, pe = phys_of(edge, is_away)
    lab_s, lab_e = ZONE[ps], ZONE[pe]
    flag = implausible(ps, pe)
    if flag:
        flags += 1
        owner = 'NORF' if is_away else 'HAWKS'
        print(f"  {ZONE[edge.source]:>9}->{ZONE[edge.target]:<9} score={score:+7.3f} {owner:5s} "
              f"drawn {lab_s:>9}->{lab_e:<9}  *** {flag} ***")
print(f"delta panel: {flags} implausible-placement arrows out of {len(delta)}")

print()
print("=" * 70)
print("PANEL 1: HAWTHORN PROFILE (matrix_a, unrotated) — check E1->A2 & implausibles")
print("=" * 70)
for edge, score in sorted(m_a.items(), key=lambda x: -abs(x[1])):
    ps, pe = phys_of(edge, False)
    flag = implausible(ps, pe)
    if flag or (edge.source == 'E1' and edge.target == 'A2'):
        print(f"  {ZONE[edge.source]:>9}->{ZONE[edge.target]:<9} score={score:+7.3f} "
              f"drawn {ZONE[ps]:>9}->{ZONE[pe]:<9}  {'*** ' + flag + ' ***' if flag else ''}")

print()
print("=" * 70)
print("PANEL 2: NORTH MELBOURNE PROFILE (matrix_b) — as CURRENTLY DRAWN (unrotated)")
print("=" * 70)
n_back = 0
for edge, score in sorted(m_b.items(), key=lambda x: -abs(x[1])):
    ps, pe = phys_of(edge, False)  # current buggy-ish behavior: is_delta=False -> never rotated
    flag = implausible(ps, pe)
    if flag or (edge.source == 'E1' and edge.target == 'A2'):
        n_back += 1
        print(f"  {ZONE[edge.source]:>9}->{ZONE[edge.target]:<9} score={score:+7.3f} "
              f"drawn {ZONE[ps]:>9}->{ZONE[pe]:<9}  {'*** ' + flag + ' ***' if flag else ''}")
print(f"profile panel: {n_back} implausible-placement arrows")

print()
print("=" * 70)
print("SANITY: top-10 Norf edges that WOULD be correct if rotated (as delta panel does)")
print("=" * 70)
for edge, score in sorted(m_b.items(), key=lambda x: -abs(x[1]))[:10]:
    ps, pe = phys_of(edge, True)
    print(f"  Norf {ZONE[edge.source]:>9}->{ZONE[edge.target]:<9} ({score:+7.3f}) "
          f"-> correct placement {ZONE[ps]:>9}->{ZONE[pe]:<9}")
