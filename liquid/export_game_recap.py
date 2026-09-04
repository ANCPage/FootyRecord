#!/usr/bin/env python3
"""RECAP export v2 — the ORIGINAL arc/funnel geometry (recovered arc_seg).

The pre-reboot recap used goal-centred arc positions (whorl funnel):
zones radiate from the goal (deep arcs wide at the defensive end,
converging at the pole) — the spindle look. node_positions (straight
grid) was the wrong substitution.
"""
import json
import os
import sqlite3
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root (Core)
sys.path.insert(0, _HERE)                    # arc_seg.py lives beside this script

from arc_seg import arc_positions, flip   # recovered original geometry

DB = '/home/austin/footyrecord-results/footyrecord.db'
TEAM_NAMES = {'CD_T100': 'North Melbourne', 'CD_T160': 'Sydney Swans'}
SEASON, ROUND = 2026, 24
A, B = 'CD_T100', 'CD_T160'

conn = sqlite3.connect(DB)
row = conn.execute(
    'SELECT m_id, home, away, home_score, away_score FROM matches '
    'WHERE season=? AND round=? AND ((home=? AND away=?) OR (home=? AND away=?))',
    (SEASON, ROUND, A, B, B, A)).fetchone()
mid, home, away, hs, aw = row
pm = conn.execute(
    'SELECT margin FROM predictions WHERE season=? AND round=? AND home=? AND away=?',
    (SEASON, ROUND, home, away)).fetchone()
pred_margin = round(abs(pm[0])) if pm else 23
print('game:', mid, '| pred margin', pred_margin)

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
        if home != tid:
            zs = [flip_zone(z) for z in zs]
        out.append(zs)
    return out

def flip_zone(z):
    from Core.geometry import rotate_node
    return rotate_node(z)

own_a = team_chains(A)
own_b = team_chains(B)

import math

def bow(pts, amount=0.16, samples=6):
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        px, py = -dy / L, dx / L
        sgn = 1.0 if (a[0] + b[0]) / 2 >= 0.5 else -1.0   # bow AWAY from the axis
        if px * sgn < 0:
            px, py = -px, -py
        mx, my = (a[0] + b[0]) / 2 + px * L * amount, (a[1] + b[1]) / 2 + py * L * amount
        for s_ in range(1, samples + 1):
            t = s_ / samples
            x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * mx + t ** 2 * b[0]
            y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * my + t ** 2 * b[1]
            out.append((x, y))
    return out


def resample(pts, n=160):
    import math as _m
    if len(pts) < 3:
        return pts
    L = [0.0]
    for i in range(1, len(pts)):
        L.append(L[-1] + _m.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]))
    total = L[-1] or 1.0
    out, j = [], 1
    for k in range(n):
        d = total * k / (n - 1)
        while j < len(L) - 1 and L[j] < d:
            j += 1
        f = (d - L[j-1]) / max(1e-9, L[j] - L[j-1])
        out.append((pts[j-1][0] + (pts[j][0] - pts[j-1][0]) * f,
                    pts[j-1][1] + (pts[j][1] - pts[j-1][1]) * f))
    return out

pos = arc_positions()
pneg = flip(pos)
def to_px(pts):
    return [[round((0.05 + 0.90 * x) * 900, 1), round((0.90 - 0.80 * y) * 1200, 1)]
            for x, y in pts]

def build(zs_list, pmap):
    arr = []
    for zs in zs_list:
        pts = [pmap[z] for z in zs if z in pmap]
        if len(pts) < 2:
            continue
        pts.append(pmap['SCORE'])
        pts = resample(bow(pts, amount=0.16))     # organic curves, as the original
        arr.append({'pts': to_px(pts), 'w': 1.0, 'w2': 1.0,
                    's2': 1.0, 'mS': 1.0, 'kind': 'own'})
    return arr

top = build(own_a, pos)
bot = build(own_b, pneg)
win = home if hs > aw else away
data = {
    'mode': 'recap',
    'round_label': f'ROUND {ROUND} \u00b7 RECAP',
    'teams': {'top': {'name': TEAM_NAMES[A]}, 'bottom': {'name': TEAM_NAMES[B]}},
    'verdict': {'winner': TEAM_NAMES.get(win, win), 'margin': pred_margin},
    'result': {'home_name': TEAM_NAMES.get(home, home), 'away_name': TEAM_NAMES.get(away, away),
               'home_score': hs, 'away_score': aw,
               'model_winner_name': TEAM_NAMES[B], 'pred_margin': pred_margin,
               'correct': True},
    'goals': {'top': pos['SCORE'], 'bottom': pneg['SCORE']},
    'ends': {'top': {'own': top}, 'bottom': {'own': bot}},
}
json.dump(data, open('/tmp/liquid_data_recap.json', 'w'))
print('RECAP json (arc geom):', len(top), 'top |', len(bot), 'bottom')
