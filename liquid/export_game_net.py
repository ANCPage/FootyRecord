#!/usr/bin/env python3
"""Export the ACTUAL NET of one game (repo geometry + local DB).

R24 2026 North v Sydney: each team's real chains from the game.
Per-route net at each end = own traffic - opponent traffic on the
mirrored route. Chains carry w=1 (raw) and w2 = net survival, so the
renderer draws the raw game, then the net lands.
"""
import json
import sqlite3
import sys
sys.path.insert(0, '/mnt/projects/FootyRecord')
from collections import Counter

from Core.fingerprint_field import node_positions
from Core.geometry import rotate_node

DB = '/home/austin/footyrecord-results/footyrecord.db'
TEAM_NAMES = {'CD_T100': 'North Melbourne', 'CD_T160': 'Sydney Swans'}
SEASON, ROUND = 2026, 24
A, B = 'CD_T100', 'CD_T160'   # A attacks the TOP goal, B the bottom

conn = sqlite3.connect(DB)
row = conn.execute(
    'SELECT m_id, home, away, home_score, away_score FROM matches '
    'WHERE season=? AND round=? AND ((home=? AND away=?) OR (home=? AND away=?))',
    (SEASON, ROUND, A, B, B, A)).fetchone()
mid, home, away, hs, aw = row
print('game:', mid, home, hs, '-', aw, away)

rows = conn.execute(
    'SELECT chain_idx, seq, team, grid FROM chains WHERE m_id=? AND outcome=? '
    'ORDER BY chain_idx, seq', (mid, 'SCORE')).fetchall()
raw = {}
for cidx, _seq, team, grid in rows:
    raw.setdefault(team, {}).setdefault(cidx, []).append(grid)

def team_chains(tid):
    out = []
    for cidx in sorted(raw.get(tid, {})):
        zs = raw[tid][cidx]
        if len(zs) < 2:
            continue
        if home != tid:                       # away: rotate into own frame
            zs = [rotate_node(z) for z in zs]
        out.append(zs)
    return out

own_a = team_chains(A)     # attack the TOP goal
own_b = team_chains(B)     # attack the BOTTOM goal

top_edges = Counter()
bot_edges = Counter()
for zs in own_a:
    for i in range(len(zs) - 1):
        top_edges[(zs[i], zs[i + 1])] += 1
    top_edges[(zs[-1], 'SCORE')] += 1
for zs in own_b:
    for i in range(len(zs) - 1):
        bot_edges[(zs[i], zs[i + 1])] += 1
    bot_edges[(zs[-1], 'SCORE')] += 1

def flipped_edge(e):
    a, b = e
    return (rotate_node(a), 'SCORE') if b == 'SCORE' else (rotate_node(a), rotate_node(b))

net_top = {e: c - bot_edges.get(flipped_edge(e), 0) for e, c in top_edges.items()}
net_bot = {e: c - top_edges.get(flipped_edge(e), 0) for e, c in bot_edges.items()}
mx = max([max(0, v) for v in net_top.values()] + [max(0, v) for v in net_bot.values()] + [1])

def chain_net(zs, netmap):
    vals = [netmap.get((zs[i], zs[i + 1]), 0) for i in range(len(zs) - 1)]
    vals.append(netmap.get((zs[-1], 'SCORE'), 0))
    return sum(max(0, v) for v in vals) / max(1, len(vals)) / mx

pos = node_positions()
pneg = {k: (1.0 - x, 1.0 - y) for k, (x, y) in pos.items()}
def to_px(pts):
    return [[round((0.05 + 0.90 * x) * 900, 1), round((0.90 - 0.80 * y) * 1200, 1)]
            for x, y in pts]

def build(zs_list, pmap, netmap):
    arr = []
    for zs in zs_list:
        pts = [pmap[z] for z in zs if z in pmap]
        if len(pts) < 2:
            continue
        pts.append(pmap['SCORE'])
        n = chain_net(zs, netmap)
        arr.append({'pts': to_px(pts), 'w': 1.0,
                    'w2': round(max(0.06, n), 4), 's2': round(max(0.15, n), 3),
                    'mS': round(n, 4), 'kind': 'own'})
    return arr

top = build(own_a, pos, net_top)
bot = build(own_b, pneg, net_bot)
win = home if hs > aw else away
data = {
    'mode': 'net',
    'round_label': f'ROUND {ROUND} \u00b7 THE ACTUAL NET',
    'teams': {'top': {'name': TEAM_NAMES[A]}, 'bottom': {'name': TEAM_NAMES[B]}},
    'verdict': {'winner': TEAM_NAMES.get(win, win), 'margin': abs(hs - aw)},
    'result': {'home_name': TEAM_NAMES.get(home, home), 'away_name': TEAM_NAMES.get(away, away),
               'home_score': hs, 'away_score': aw,
               'model_winner_name': TEAM_NAMES[B], 'pred_margin': 23.1, 'correct': True},
    'goals': {'top': pos['SCORE'], 'bottom': pneg['SCORE']},
    'ends': {'top': {'own': top}, 'bottom': {'own': bot}},
}
json.dump(data, open('/tmp/liquid_data.json', 'w'))
print('NET json:', len(top), 'top |', len(bot), 'bottom | winner', TEAM_NAMES[win])
print('end net totals: top', round(sum(c['w2'] for c in top), 2),
      'bottom', round(sum(c['w2'] for c in bot), 2))
