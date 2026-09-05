"""Liquid presentation geometry — the ONLY place zones become pixels.

Presentation-only (no SQL, no model arithmetic): reads a data-space card
payload from Core.cards and returns the exact JSON the canvas template
consumes (goals + px chains). Home of the recovered arc/funnel geometry
(arc_seg), the outward per-edge bow, arc-length resampling, and the
data->px mapping.
"""
import math

from Core.geometry import GRID_NAMES

GOAL = (0.5, 0.92)


def arc_positions():
    """Goal-centred funnel: 5 depth arcs x 3 lanes radiating from the top goal.

    lane = angular offset, depth = radius from the goal (deep arcs wide at
    the defensive end, converging at the pole) — the recovered whorl geometry.
    """
    pos = {}
    for lane_i, row in enumerate(GRID_NAMES):
        theta = math.radians((lane_i - 1) * 32)
        for depth_i, name in enumerate(row):
            r = 0.13 + 0.45 * depth_i / 4.0
            pos[name] = (GOAL[0] + r * math.sin(theta),
                         GOAL[1] - r * math.cos(theta))
    pos['SCORE'] = GOAL
    return pos


def flip(pos_map):
    return {k: (1.0 - x, 1.0 - y) for k, (x, y) in pos_map.items()}


def bow(pts, amount=0.16, samples=6):
    """Per-edge quadratic arcs bowed AWAY from the central axis (opened the
    centre in the accepted rebuild)."""
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        px, py = -dy / L, dx / L
        sgn = 1.0 if (a[0] + b[0]) / 2 >= 0.5 else -1.0
        if px * sgn < 0:
            px, py = -px, -py
        mx, my = (a[0] + b[0]) / 2 + px * L * amount, \
                 (a[1] + b[1]) / 2 + py * L * amount
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
        L.append(L[-1] + math.hypot(pts[i][0] - pts[i - 1][0],
                                    pts[i][1] - pts[i - 1][1]))
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


def to_px(pts):
    return [[round((0.05 + 0.90 * x) * 900, 1),
             round((0.90 - 0.80 * y) * 1200, 1)] for x, y in pts]


def _build_paths(chains_list, pmap, rng_state):
    """Zone-sequence chains -> px paths (bow/resample/smooth-ready pts)."""
    out = []
    for ch in chains_list:
        seq = ch['seq']
        pts = [pmap[z] for z in seq if z in pmap]
        if len(pts) < 2:
            continue
        pts.append(pmap['SCORE'])
        rng_state[0] = (rng_state[0] * 1103515245 + 12345) & 0x7fffffff
        amt = 0.14 + 0.12 * (rng_state[0] / 0x7fffffff)
        sp = resample(bow(pts, amount=amt))
        out.append({'pts': to_px(sp), 'w': ch['w'], 'w2': ch['w2'],
                    's2': ch['s2'], 'mS': ch['mS'], 'kind': ch['kind']})
    return out


def materialise(payload, seed=987654321):
    """Data-space card payload -> template JSON (goals + px chains)."""
    pos = arc_positions()
    pneg = flip(pos)
    rng = [seed]
    ends = {}
    for end, pmap in (('top', pos), ('bottom', pneg)):
        own = payload['ends'][end].get('own', [])
        ends[end] = {'own': _build_paths(own, pmap, rng)}
    return {
        'mode': payload['mode'],
        'round_label': payload['round_label'],
        'teams': payload['teams'],
        'verdict': payload['verdict'],
        'result': payload.get('result', {}),
        'goals': {'top': to_px([pos['SCORE']])[0],
                  'bottom': to_px([pneg['SCORE']])[0]},
        'ends': ends,
    }
