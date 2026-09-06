"""Liquid presentation geometry — the ONLY place zones become pixels.

Presentation-only (no SQL, no model arithmetic): reads a data-space card
payload from Core.cards and returns the exact JSON the canvas template
consumes (goals + px chains). Home of the SHARED-WEB lattice (2026-09-06,
Austin-approved), the outward per-edge bow, arc-length resampling, and the
data->px mapping.

Geometry constants (oval, projection) come from theme.json — the same file
the canvas chrome reads — so the drawn field and the Python lattice can
never disagree.
"""
import json
import math
import os

from Core.geometry import GRID_NAMES, flip_positions

_THEME = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'theme.json')))
FIELD = _THEME['field']
CANVAS = _THEME['canvas']
PROJ = _THEME['projection']

GOAL = (0.5, 0.92)
FIELD_LEN = 2.0 * GOAL[1] - 1.0          # 0.84: top goal y to bottom goal y
SPREAD = 0.68                             # wing lanes ~2/3 of the oval width:
                                          # the CENTRE of the wing corridor
                                          # (0.85 sat on the boundary line;
                                          # 0.50 was too thin)


def _oval_half_width(y):
    """Data-space half-width of the chrome oval at data-y (single source:
    theme field + projection)."""
    py = (PROJ['y']['margin'] - PROJ['y']['scale'] * y) * CANVAS['h']
    t = 1.0 - ((py - FIELD['cy']) / FIELD['ry']) ** 2
    px_w = FIELD['rx'] * math.sqrt(max(0.0, t))
    return px_w / (PROJ['x']['scale'] * CANVAS['w'])


def field_positions():
    """SHARED-WEB lattice (Austin 2026-09-06): one oval-bounded mesh.

    The 15 zones are the CENTRES of real positions on the ground: 5 even
    depth bands spanning the full field (A = own DEFENSIVE end / back pocket
    .. E = the ATTACKING goal square — the model's letter semantics,
    fingerprint_field "A bottom .. E near the goal"; raw chains ascend
    A->E toward the shot), 3 lanes at 85% of the oval's width so the wings
    sit where wingers play (near the boundary at the centre, converging into
    the pocket arcs at the ends). 180-symmetric by construction: a team's
    depth c / lane l and its mirror's depth 4-c / lane 4-l land on the SAME
    nodes, so both teams trace one identical lattice (audit: flip(pos) ==
    pos as a set, 0 gap; every node inside the chrome oval — pinned in
    tests).
    """
    pos = {}
    for lane_i, row in enumerate(GRID_NAMES):        # lane_i 0,1,2 = digits 1,2,3
        side = lane_i - 1                            # -1, 0, +1 (left/centre/right)
        for depth_i, name in enumerate(row):         # depth_i 0..4 = letters A..E
            # DEPTH SEMANTICS (2026-09-06, Austin caught the inversion): the
            # model's letters run A = DEFENSIVE end (back pocket) .. E =
            # ATTACKING end (goal square) — see Core/fingerprint_field.py
            # ("A bottom .. E near the goal") + raw chains ascend A->E toward
            # the shot. Band index is mirrored so A sits at the team's own
            # defensive end and E just below its attacking goal.
            y = GOAL[1] - FIELD_LEN * ((4 - depth_i) + 0.5) / 5.0
            x = 0.5 + side * SPREAD * _oval_half_width(y)
            pos[name] = (x, y)
    pos['SCORE'] = GOAL
    return pos


def flip(pos_map):
    """Away-frame projection mirror (delegates — one spelling, Core.geometry)."""
    return flip_positions(pos_map)


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
    """Data -> px via theme projection. The y-margin (0.913333... in theme)
    sits the play area low enough that the top goal ring clears the verdict
    detail line, AND maps data-y 0.5 to px FIELD.cy exactly — so the chrome
    oval is exactly centred on the data and the shared lattice is exactly
    180-symmetric. (Single source: theme.json projection.)"""
    mx, sx = PROJ['x']['margin'], PROJ['x']['scale']
    my, sy = PROJ['y']['margin'], PROJ['y']['scale']
    return [[round((mx + sx * x) * CANVAS['w'], 1),
             round((my - sy * y) * CANVAS['h'], 1)] for x, y in pts]


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
    pos = field_positions()
    pneg = flip(pos)
    rng = [seed]
    ends = {}
    for end, pmap in (('top', pos), ('bottom', pneg)):
        own = payload['ends'][end].get('own', [])
        ends[end] = {'own': _build_paths(own, pmap, rng)}
    return {
        'version': payload.get('version'),
        'mode': payload['mode'],
        'round_label': payload['round_label'],
        'teams': payload['teams'],
        'verdict': payload['verdict'],
        'result': payload.get('result', {}),
        'goals': {'top': to_px([pos['SCORE']])[0],
                  'bottom': to_px([pneg['SCORE']])[0]},
        'ends': ends,
    }
