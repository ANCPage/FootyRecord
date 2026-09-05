#!/usr/bin/env python3
"""PREDICTION liquid export — generic Finals Week 1 2026 matchup.

Model projection BEFORE the game (data through R24 only; the game is never
seen). A attacks the TOP goal (navy), B the bottom (red). Chains = top80 of
each team's own 2026 scoring paths (decayed, own frame), weighted by the
head-to-head matrix delta from compute_matchup. Verdict = compute_matchup in
the home frame with post-R24 elos.

Run from /mnt/projects/FootyRecord. Env: A_ID B_ID HOME_ID [UP_TO]
Writes /tmp/liquid_data.json.
"""
import json
import math
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'liquid'))

from arc_seg import arc_positions, flip
from Core.config import DATA_DIR
from Core.engine_data import DataIngestor
from Core.mappings import TEAM_DATA
from Core.prediction import compute_matchup

A = os.environ.get('A_ID', 'CD_T160')        # top / navy
B = os.environ.get('B_ID', 'CD_T20')         # bottom / red
HOME = os.environ.get('HOME_ID', A)          # fixture home (frame for verdict)
SEASON = int(os.environ.get('SEASON', '2026'))
UP_TO = int(os.environ.get('UP_TO', '24'))
DECAY = 0.3
NAMES = {k: v['name'] for k, v in TEAM_DATA.items()}
AWAY = B if HOME == A else A
DB = '/home/austin/footyrecord-results/footyrecord.db'

conn = sqlite3.connect(DB)
ing = DataIngestor(DATA_DIR)
ing.load_all_data(light=True)


def post_elo(tid):
    r = conn.execute('SELECT elo FROM elo_history WHERE team=? ORDER BY m_id DESC LIMIT 1',
                     (tid,)).fetchone()
    return r[0] if r else 1500.0


ov = {t: post_elo(t) for t in (A, B)}
pred = compute_matchup(ing, HOME, AWAY, SEASON, UP_TO + 1, elo_overrides=ov)
if pred is None:
    raise SystemExit('prediction returned None')
winner_id = pred.winner_id
margin = round(abs(pred.margin_pred))
print('verdict: %s by %d (proj %d-%d, net %+.4f)' %
      (NAMES[winner_id], margin, pred.home_score, pred.away_score, pred.net_delta))

top_pred = compute_matchup(ing, A, B, SEASON, UP_TO + 1, elo_overrides=ov)
bot_pred = compute_matchup(ing, B, A, SEASON, UP_TO + 1, elo_overrides=ov)


def ek(e):
    return (e.source, e.target) if hasattr(e, 'source') else tuple(e)


delta_top = {ek(k): v for k, v in top_pred.delta.items()}
delta_bot = {ek(k): v for k, v in bot_pred.delta.items()}

rows = conn.execute(
    'SELECT c.m_id, c.chain_idx, c.seq, c.team, c.grid, m.home, m.round '
    'FROM chains c JOIN matches m ON c.m_id = m.m_id '
    'WHERE m.season=? AND m.round<=? AND c.team IN (?,?) AND c.outcome=? '
    'ORDER BY c.m_id, c.chain_idx, c.seq', (SEASON, UP_TO, A, B, 'SCORE')).fetchall()
per = {}
for mid, cidx, _seq, team, grid, home, rnd in rows:
    per.setdefault(team, {}).setdefault((mid, cidx), []).append((grid, mid, home, rnd))

from Core.geometry import rotate_node


def collapse(zs):
    out = []
    for z in zs:
        if not out or out[-1] != z:
            out.append(z)
    return out


def team_counter(tid):
    from collections import Counter
    c = Counter()
    for key in per.get(tid, {}):
        cells = per[tid][key]
        rnd = cells[0][3]
        grids = [g for g, _m, _h, _r in cells]
        grids = collapse(grids)
        if len(grids) < 2:
            continue
        home = cells[0][2]
        if home != tid:
            grids = [rotate_node(g) for g in grids]
        w = DECAY ** max(UP_TO - rnd, 0)
        c[tuple(grids)] += w
    return c


def top80(counter, frac=0.80):
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    tot = sum(counter.values()) or 1
    out, acc = [], 0.0
    for path, w in items:
        out.append((path, w))
        acc += w
        if acc / tot >= frac and len(out) >= 12:
            break
    return out


def bow(pts, amount=0.16, samples=6):
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        px, py = -dy / L, dx / L
        sgn = 1.0 if (a[0] + b[0]) / 2 >= 0.5 else -1.0   # bow AWAY from axis
        if px * sgn < 0:
            px, py = -px, -py
        mx, my = (a[0] + b[0]) / 2 + px * L * amount, (a[1] + b[1]) / 2 + py * L * amount
        for s in range(1, samples + 1):
            t = s / samples
            x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * mx + t ** 2 * b[0]
            y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * my + t ** 2 * b[1]
            out.append((x, y))
    return out


def resample(pts, n=160):
    if len(pts) < 3:
        return pts
    L = [0.0]
    for i in range(1, len(pts)):
        L.append(L[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    total = L[-1] or 1.0
    out, j = [], 1
    for k in range(n):
        d = total * k / (n - 1)
        while j < len(L) - 1 and L[j] < d:
            j += 1
        f = (d - L[j - 1]) / max(1e-9, L[j] - L[j - 1])
        out.append((pts[j - 1][0] + (pts[j][0] - pts[j - 1][0]) * f,
                    pts[j - 1][1] + (pts[j][1] - pts[j - 1][1]) * f))
    return out


pos = arc_positions()
pneg = flip(pos)


def to_px(pts):
    return [[round((0.05 + 0.90 * x) * 900, 1), round((0.90 - 0.80 * y) * 1200, 1)]
            for x, y in pts]


def chain_net(path, delta):
    zs = list(path)
    vals = [delta.get((zs[i], zs[i + 1]), 0) for i in range(len(zs) - 1)]
    vals.append(delta.get((zs[-1], 'SCORE'), 0))
    return sum(max(0.0, v) for v in vals) / max(1, len(vals))


ca, cb = team_counter(A), team_counter(B)
sa, sb = top80(ca), top80(cb)
nets = [chain_net(p, delta_top) for p, _w in sa] + [chain_net(p, delta_bot) for p, _w in sb]
mx = max(nets + [1e-6])


def build(sel, pmap, delta, rng_state):
    arr = []
    for path, _w in sel:
        pts = [pmap[z] for z in path if z in pmap]
        if len(pts) < 2:
            continue
        pts.append(pmap['SCORE'])
        n = chain_net(path, delta) / mx
        rng_state[0] = (rng_state[0] * 1103515245 + 12345) & 0x7fffffff
        amt = 0.14 + 0.12 * (rng_state[0] / 0x7fffffff)
        sp = resample(bow(pts, amount=amt))
        arr.append({'pts': to_px(sp), 'w': 1.0,
                    'w2': round(max(0.06, n), 4), 's2': round(max(0.15, n), 3),
                    'mS': round(n, 4), 'kind': 'own'})
    return arr


rng = [987654321]
top = build(sa, pos, delta_top, rng)
bot = build(sb, pneg, delta_bot, rng)


# ------------------------------------------------------------ club colours
# primary + real clash/alt colours (curated 2026-09-05). WHITE = the club's
# real away (rendered as white ribbons with an ink outline by the template).
TEAM_COLOURS = {
    'CD_T10':  ('#002B5C', ['#E21937', '#F2A900']),   # Adelaide
    'CD_T20':  ('#730040', ['#FDB813']),              # Brisbane (maroon/gold)
    'CD_T30':  ('#031A29', ['WHITE']),                # Carlton
    'CD_T40':  ('#101820', ['WHITE']),                # Collingwood
    'CD_T50':  ('#CC2031', ['#101820']),              # Essendon (red primary)
    'CD_T60':  ('#5A2A82', ['WHITE']),                # Fremantle
    'CD_T70':  ('#1C3C63', ['WHITE']),                # Geelong
    'CD_T80':  ('#4D2004', ['#FBBC08']),              # Hawthorn
    'CD_T90':  ('#0F1131', ['#CC2031', '#1A3B8E']),   # Melbourne
    'CD_T100': ('#1A3B8E', ['WHITE']),                # North Melbourne (royal)
    'CD_T110': ('#00A5AC', ['#101820']),              # Port Adelaide
    'CD_T120': ('#101820', ['#FFD200']),              # Richmond
    'CD_T130': ('#ED0F05', ['#101820']),              # St Kilda
    'CD_T140': ('#014896', ['#C70136']),              # Western Bulldogs
    'CD_T150': ('#002B5C', ['#F2AA00']),              # West Coast
    'CD_T160': ('#ED171F', ['WHITE']),                # Sydney
    'CD_T1000':('#E11B0A', ['#FFD200']),              # Gold Coast
    'CD_T1010':('#F15C22', ['#231F20']),              # GWS
}
CREAM_RGB = (241, 237, 227)


def _rgb(h):
    h = h.lstrip('#'); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _dE(h1, h2):
    def f(t): t /= 255.0; return t / 12.92 if t <= 0.04045 else ((t + 0.055) / 1.055) ** 2.4
    def lab(h):
        r, g, b = (f(v) * 100 for v in (_rgb(h) if isinstance(h, str) else h))
        X, Y, Z = (r*0.4124+g*0.3576+b*0.1805, r*0.2126+g*0.7152+b*0.0722, r*0.0193+g*0.1192+b*0.9505)
        def g_(t): return t ** (1/3) if t > 0.008856 else 7.787*t + 16/116
        fx, fy, fz = g_(X/95.047), g_(Y/100.0), g_(Z/108.883)
        return (116*fy-16, 500*(fx-fy), 200*(fy-fz))
    La, Aa, Ba = lab(h1); Lb, Ab, Bb = lab(h2)
    return ((La-Lb)**2 + (Aa-Ab)**2 + (Ba-Bb)**2) ** 0.5


def worn_colours(home_id, away_id):
    """Policy: home always primary; away flips to its real clash colour only
    when its primary clashes with the home primary (dE < 60)."""
    hp = TEAM_COLOURS[home_id][0]
    ap = TEAM_COLOURS[away_id][0]
    if _dE(hp, ap) >= 60.0:
        return hp, ap
    best, best_d = ap, _dE(hp, ap)
    for a in TEAM_COLOURS[away_id][1]:
        da = 60.0 if a == 'WHITE' else min(_dE(a, hp), _dE(a, CREAM_RGB))
        if da > best_d:
            best, best_d = a, da
    return hp, best

_home_col, _away_col = worn_colours(HOME, AWAY)
COLOUR_OF = {HOME: _home_col, AWAY: _away_col}

data = {
    'mode': 'pred',
    'round_label': 'FINALS WEEK 1 \u00b7 PREDICTION',
    'teams': {'top': {'name': NAMES[A], 'colour': COLOUR_OF.get(A, TEAM_COLOURS[A][0])},
              'bottom': {'name': NAMES[B], 'colour': COLOUR_OF.get(B, TEAM_COLOURS[B][0])}},
    'verdict': {'winner': NAMES[winner_id], 'margin': margin,
               'projected': [pred.home_score if A == HOME else pred.away_score,
                             pred.home_score if B == HOME else pred.away_score]},
    'result': {'home_name': NAMES[HOME], 'away_name': NAMES[AWAY],
               'model_winner_name': NAMES[winner_id],
               'pred_margin': margin, 'correct': None},
    'goals': {'top': to_px([pos['SCORE']])[0], 'bottom': to_px([pneg['SCORE']])[0]},
    'ends': {'top': {'own': top}, 'bottom': {'own': bot}},
}
json.dump(data, open('/tmp/liquid_data.json', 'w'))
print('PRED json:', len(top), 'top (', NAMES[A], ') |', len(bot), 'bottom (',
      NAMES[B], ') | winner', NAMES[winner_id], 'by', margin)
print('end net totals: top', round(sum(c['w2'] for c in top), 3),
      'bottom', round(sum(c['w2'] for c in bot), 3))
