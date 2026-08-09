"""Audit LFP->FB ball movement for 2026 R21 Game 6 (matchId CD_M20260142106).

The user reported noticing ball movement LFP -> FB which seems unlikely.
LFP (E1) is the Left Forward Pocket near the attacking goals; FB (A2) is Full
Back near the defending goals.  A direct LFP->FB edge would be a ball moving
from the forward pocket straight back to the full-back defensive zone in a
single step, which would be unusual (a long kick backwards / turnover).
"""
import csv
from collections import defaultdict, Counter

MATCH = 'CD_M20260142106'
CSV = 'CSV_DATA/flattened_stats_2026.csv'

ZONE = {
    'A1':'LBP','B1':'LHB','C1':'LW','D1':'LHF','E1':'LFP',
    'A2':'FB','B2':'CHB','C2':'C','D2':'CHF','E2':'FF',
    'A3':'RBP','B3':'RHB','C3':'RW','D3':'RHF','E3':'RFP',
    'SCORE':'SCORE',
}

rows = [r for r in csv.DictReader(open(CSV, encoding='utf-8-sig')) if r['matchId'] == MATCH]
print(f"total rows for match: {len(rows)}")

# Identify LFP and FB grids present
grids = Counter(r['grid'].strip() for r in rows if r['grid'] and r['grid'].strip())
print(f"\ndistinct grids present: {len(grids)}")
for k, v in sorted(grids.items()):
    print(f"  {k!r} ({ZONE.get(k, '?')}): {v}")

# Build chains preserving order. Represent each chain as list of (grid, stat_class, desc)
chains = defaultdict(lambda: {'team':'', 'outcome':'', 'events':[]})
for r in rows:
    cid = f"{r['chain_index']}"
    chains[cid]['team'] = r['chain_teamId']
    chains[cid]['outcome'] = r['chain_finalState_class']
    g = (r['grid'] or '').strip()
    if g:
        chains[cid]['events'].append((g, r['stat_class'], r['stat_description']))

print(f"\ntotal chains: {len(chains)}")

# Include any grid value that maps to LFP or FB anywhere
lfp_vals = [k for k in grids if ZONE.get(k) == 'LFP']
fb_vals = [k for k in grids if ZONE.get(k) == 'FB']
print(f"\nLFP grids: {lfp_vals}")
print(f"FB grids: {fb_vals}")

# Is any LFP value even present in the data?
print(f"\nLFP present? {bool(lfp_vals)}")

# Count N-step transitions (k=1 direct, k=2, k=3)
dirs = {'LFP': set(lfp_vals), 'FB': set(fb_vals)}

def zone_of(g):
    return ZONE.get(g)

def transitions(k):
    """Count transitions between LFP and FB of window size k across event stream."""
    from_fb_to_lfp = 0
    from_lfp_to_fb = 0
    examples = []
    for cid, ch in chains.items():
        ev = ch['events']
        for i in range(len(ev) - k):
            window = ev[i:i+k+1]
            first, last = zone_of(window[0][0]), zone_of(window[-1][0])
            if first == 'FB' and last == 'LFP':
                from_fb_to_lfp += 1
                if len(examples) < 5:
                    examples.append((cid, window, ch['outcome']))
            if first == 'LFP' and last == 'FB':
                from_lfp_to_fb += 1
                if len(examples) < 5:
                    examples.append((cid, window, ch['outcome']))
    return from_lfp_to_fb, from_fb_to_lfp, examples

for k in (1, 2, 3, 5):
    l2f, f2l, ex = transitions(k)
    tot = l2f + f2l
    print(f"\n=== window size {k}: LFP->FB={l2f}, FB->LFP={f2l}, total={tot} ===")
    for cid, window, outcome in ex:
        seq = ' '.join(f"{zone_of(g)}[{g}]" for g, _, _ in window)
        print(f"   chain {cid} ({outcome}): {seq}")

# Show directed full zone transition matrix within chains (collapsed consecutive)
print("\n=== single-step zone transition matrix (any chain) ===")
edges = Counter()
for cid, ch in chains.items():
    ev = ch['events']
    collapsed = []
    for g, sc, desc in ev:
        if not collapsed or collapsed[-1][0] != g:
            collapsed.append((g, sc, desc))
    for i in range(len(collapsed)-1):
        a = zone_of(collapsed[i][0])
        b = zone_of(collapsed[i+1][0])
        edges[(a, b)] += 1
# Filter to edges touching LFP or FB
print("edges involving LFP or FB:")
for (a, b), cnt in sorted(edges.items()):
    if a in ('LFP','FB') or b in ('LFP','FB'):
        print(f"   {a} -> {b}: {cnt}")
