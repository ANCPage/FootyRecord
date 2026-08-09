import csv
from collections import defaultdict

MATCH = 'CD_M20260142106'
CSV = 'CSV_DATA/flattened_stats_2026.csv'

zone_labels = {
    'A1': 'LBP', 'B1': 'LHB', 'C1': 'LW', 'D1': 'LHF', 'E1': 'LFP',
    'A2': 'FB',  'B2': 'CHB', 'C2': 'C',  'D2': 'CHF', 'E2': 'FF',
    'A3': 'RBP', 'B3': 'RHB', 'C3': 'RW', 'D3': 'RHF', 'E3': 'RFP'
}

# Build raw chains preserving order, including stat_class and coords
chains = defaultdict(lambda: {'team': '', 'outcome': '', 'events': []})
with open(CSV, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['matchId'] != MATCH:
            continue
        c_id = f"{MATCH}_{row['chain_index']}"
        chains[c_id]['team'] = row['chain_teamId']
        chains[c_id]['outcome'] = row['chain_finalState_class']
        g = row['grid']
        if g and row['stat_class'] in ['POSSESSION', 'DISPOSAL', 'SCORE']:
            chains[c_id]['events'].append(g)

print(f"Total chains in match: {len(chains)}")
print(f"Scoring chains: {sum(1 for c in chains.values() if c['outcome']=='SCORE')}")
print()

# --- 1. RAW adjacency check: LFP<->FB anywhere in raw event sequence of any chain ---
print("=== RAW LFP(E1) <-> FB(A2) adjacencies in any chain ===")
raw_found = 0
for c_id, chain in sorted(chains.items()):
    ev = chain['events']
    for i in range(len(ev)-1):
        a, b = ev[i], ev[i+1]
        la, lb = zone_labels.get(a), zone_labels.get(b)
        if (la, lb) in [('LFP','FB'),('FB','LFP')]:
            raw_found += 1
            print(f"  {c_id}: ...{la}({a}) -> {lb}({b})... (outcome={chain['outcome']}, team={chain['team']})")
print(f"total raw LFP<->FB adjacencies: {raw_found}")
print()

# --- 2. Engine-style collapse on SCORING chains: LFP<->FB edges ---
print("=== Engine-style collapsed LFP(E1)<->FB(A2) edges (scoring chains only) ===")
eng_found = 0
for c_id, chain in sorted(chains.items()):
    if chain['outcome'] != 'SCORE':
        continue
    ev = chain['events']
    collapsed = []
    for g in ev:
        if not collapsed or collapsed[-1] != g:
            collapsed.append(g)
    for i in range(len(collapsed)-1):
        a, b = collapsed[i], collapsed[i+1]
        la, lb = zone_labels.get(a), zone_labels.get(b)
        if (la, lb) in [('LFP','FB'),('FB','LFP')]:
            eng_found += 1
            print(f"  {c_id}: {zone_labels.get(a)}({a}) -> {zone_labels.get(b)}({b})  [collapsed len={len(collapsed)}]")
print(f"total engine-collapsed LFP<->FB edges: {eng_found}")
