# ruff: noqa: E402  (imports follow the path bootstrap below)
from Core.engine_core import MatchupEngine
from Core.engine_data import DataIngestor
from Core.mappings import TEAM_DATA

ZONE = {n: lbl for lbl, n in [
    ('LBP','A1'),('LHB','B1'),('LW','C1'),('LHF','D1'),('LFP','E1'),
    ('FB','A2'),('CHB','B2'),('C','C2'),('CHF','D2'),('FF','E2'),
    ('RBP','A3'),('RHB','B3'),('RW','C3'),('RHF','D3'),('RFP','E3')]}

csv_path = 'CSV_DATA'
ingestor = DataIngestor(csv_path)
ingestor.load_all_data()
ingestor.profile_all_teams()

h_id, a_id = 'CD_T80', 'CD_T100'
h_n = TEAM_DATA.get(h_id)['name']
a_n = TEAM_DATA.get(a_id)['name']
print(f"Matchup: {h_n} (home {h_id}) vs {a_n} (away {a_id})")

m_a = ingestor.get_team_average_matrix(h_id)
m_b = ingestor.get_team_average_matrix(a_id)
delta = MatchupEngine.calculate_delta(m_a, m_b)

print(f"\nTotal edges in delta matrix: {len(delta)}")
print(f"Net delta (home advantage): {sum(delta.values()):+.3f}")

# Search for any edge where, in the HOME-frame label shown on the field, source=LFP target=FB
hit = [(e, v) for e, v in delta.items() if e.source == 'E1' and e.target == 'A2']
print("\nEdges rendered as LFP->FB (E1->A2) in the Absolute Matchup Ownership panel:")
for e, v in hit:
    owner = h_n if v > 0 else a_n
    print(f"  {ZONE[e.source]}->{ZONE[e.target]}  score={v:+.3f}  owned by: {owner}")

# Also show edges that touch E1 or A2 at all (to show what these zones DO show)
print("\nAll delta edges touching LFP(E1) or FB(A2) in the home label frame:")
for e, v in sorted(delta.items(), key=lambda x: -abs(x[1])):
    if e.source in ('E1','A2') or e.target in ('E1','A2'):
        owner = h_n if v>0 else a_n
        print(f"  {ZONE.get(e.source,e.source)}->{ZONE.get(e.target,e.target)}  score={v:+.3f}  {owner}")

# Source-trace: where does the LFP->FB advantage come from?
from Core.models import TransitionEdge

print("\n=== SOURCE TRACE for LFP->FB (E1->A2) in the delta ===")
# In calculate_delta: delta[E1->A2] = val_a(E1->A2) - val_b(rotate(E1->A2))
# rotate(E1->A2): E1->A3, A2->E2  =>  A3 -> E2
print(f"Home ({h_n}) value E1->A2          : {m_a.get(TransitionEdge('E1','A2'), 0.0):+.4f}")
print(f"Away ({a_n}) value E1->A2 (raw, unrotated frame): {m_b.get(TransitionEdge('E1','A2'), 0.0):+.4f}")
print(f"Away ({a_n}) value A3->E2 (should equal E1->A2 in home frame): {m_b.get(TransitionEdge('A3','E2'), 0.0):+.4f}")
print(f"Computed delta E1->A2 = val_a(E1->A2) - val_b(A3->E2) = {delta.get(TransitionEdge('E1','A2'),0.0):+.4f}")
