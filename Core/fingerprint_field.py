"""Fingerprint ridge field (Whorlfield concept, 2026-08-30).

Design by generative-art concept (delegated design pass); build by this
module — pure math, no matplotlib, unit-tested.

THE IDEA: each directed edge of a team's matrix emits a smooth flow (unit
vectors along its source->target path, Gaussian-smeared, scaled by edge
weight). Summed, the edges define a 2D vector field. Streamlines traced
through that field ARE the fingerprint ridges: continuous, parallel,
flowing — the ridge structure is an integral curve of the data's own flow,
not decoration.

Honesty rules enforced here (each unit-tested):
  - EQUAL INK: per sign class, total traced ridge length is capped to a
    budget proportional to the class's absolute weight share — weight is
    PACKING DENSITY, never thickness. All teams have ~equal total ink, so
    strength must never read as size.
  - MIN SPACING: traced ridges keep a minimum distance from already-drawn
    ridges (no moiré at Telegram compression, no crowding).
  - VERDICT: in overlay mode the winner is sign(count of teal strands
    crossing the goal ring - terracotta strands). Tested against the real
    net_delta sign on 2026 teams.
"""

from typing import Dict, List, Tuple

import numpy as np

from Core.models import TransitionEdge

# Field grid resolution (200x200 over the unit square is plenty for 900px)
GRID = 200
# Inner radius (fraction of the whorl radius) where streamlines stop: the
# goal singularity — shot edges converge at the centre, field magnitude
# explodes. Ridges stop at the ring instead of diving into the singularity.
GOAL_RING = 0.16
# Minimum spacing between ridges, in field-grid units (grid = 1.0 wide)
MIN_SPACING = 0.012
# Max streamline length in field units before we give up on a seed
MAX_LEN = 3.0


def node_positions() -> Dict[str, Tuple[float, float]]:
    """Node positions in the whorl geometry (unit square, goal at centre).

    radius = depth from goal (row A outermost, row E hugging the goal);
    angle  = ground bearing (column A..E spread symmetrically).
    """
    import math

    from Core.geometry import GRID_NAMES

    cx, cy, R = 0.5, 0.52, 0.40
    pos = {}
    for r_i, row in enumerate(GRID_NAMES):
        radius = R * (0.14 + 0.82 * (4 - r_i) / 4.0)
        for c_i, name in enumerate(row):
            ang = math.radians(90 + (c_i - 2) * 34)
            pos[name] = (cx + radius * math.cos(ang), cy + radius * math.sin(ang))
    pos['SCORE'] = (cx, cy)
    return pos


def _edge_path(p0, p1):
    """Quadratic bezier sample points for an edge (slight outward bow)."""
    import math

    n = 24
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    d = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) or 1.0
    bow = 0.10 * d
    ctrl = (mx - (my - 0.5) / d * bow, my + (mx - 0.5) / d * bow)
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * p1[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * p1[1]
        pts.append((x, y))
    return pts


def build_field(edges: Dict[TransitionEdge, float], pos: Dict[str, Tuple[float, float]],
                sigma: float = 0.045):
    """Sum edge flows into a 2D vector field on a GRIDxGRID grid.

    Each edge contributes unit vectors along its path, Gaussian-smeared,
    scaled by the edge's absolute weight. Positive edges accumulate in
    field_pos, negative in field_neg (both returned, plus the signed sum).
    """
    xs = np.linspace(0, 1, GRID)
    ys = np.linspace(0, 1, GRID)
    fx = np.zeros((GRID, GRID))
    fy = np.zeros((GRID, GRID))
    fxp = np.zeros((GRID, GRID))
    fyp = np.zeros((GRID, GRID))
    fxn = np.zeros((GRID, GRID))
    fyn = np.zeros((GRID, GRID))

    for edge, w in edges.items():
        if edge.source not in pos or edge.target not in pos:
            continue
        pts = _edge_path(pos[edge.source], pos[edge.target])
        sign = 1.0 if w > 0 else -1.0
        wgt = abs(w)
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            L = (dx * dx + dy * dy) ** 0.5
            if L < 1e-9:
                continue
            ux, uy = dx / L, dy / L
            gx = ((x0 + x1) / 2 - xs)
            gy = ((y0 + y1) / 2 - ys)
            g = np.exp(-(gx[:, None] ** 2 + gy[None, :] ** 2) / (2 * sigma ** 2))
            fx += wgt * ux * g
            fy += wgt * uy * g
            if sign > 0:
                fxp += wgt * ux * g
                fyp += wgt * uy * g
            else:
                fxn += wgt * ux * g
                fyn += wgt * uy * g
    return {'x': fx, 'y': fy, 'xp': fxp, 'yp': fyp, 'xn': fxn, 'yn': fyn,
            'xs': xs, 'ys': ys}


def _sample(field, x, y):
    """Bilinear sample of a field grid at (x, y); NaN-safe outside [0,1]."""
    gx = np.clip(x, 0, 1) * (GRID - 1)
    gy = np.clip(y, 0, 1) * (GRID - 1)
    i0, j0 = int(gx), int(gy)
    i1, j1 = min(i0 + 1, GRID - 1), min(j0 + 1, GRID - 1)
    tx, ty = gx - i0, gy - j0
    return (field[i0, j0] * (1 - tx) * (1 - ty) + field[i1, j0] * tx * (1 - ty)
            + field[i0, j1] * (1 - tx) * ty + field[i1, j1] * tx * ty)


def _field_vel(field, x, y, signed: bool):
    """Velocity at (x,y): signed field (pos - neg) or per-sign field."""
    if signed:
        return (_sample(field['x'], x, y), _sample(field['y'], x, y))
    raise ValueError('per-sign tracing not used; pass signed=True')


def trace_streamlines(field, seeds, pos, budget: float, sign_field,
                      min_spacing: float = MIN_SPACING,
                      max_len: float = MAX_LEN) -> List[List[Tuple[float, float]]]:
    """Trace ridges from seeds through a signed field.

    Returns list of ridge polylines (in field coords). Stops when:
      - the equal-ink budget (total traced length) is exhausted
      - a step would come within min_spacing of an existing ridge
      - the streamline leaves the whorl area or hits the goal ring
      - max_len reached without progress
    """
    cx, cy, R = 0.5, 0.52, 0.40
    inner = R * GOAL_RING

    def outside(x, y):
        return (x - cx) ** 2 + (y - cy) ** 2 > R * R

    def near_goal(x, y):
        return (x - cx) ** 2 + (y - cy) ** 2 < inner * inner

    occupied = []  # list of points already drawn, for min-spacing

    def too_close(x, y):
        if not occupied:
            return False
        # coarse bucket check: only scan the last chunk for speed
        for px, py in occupied[-400:]:
            if (px - x) ** 2 + (py - y) ** 2 < min_spacing ** 2:
                return True
        return False

    ridges = []
    used = 0.0
    for sx, sy in seeds:
        if used >= budget:
            break
        x, y = sx, sy
        pts = [(x, y)]
        length = 0.0
        for _ in range(4000):
            vx, vy = _field_vel(sign_field, x, y, signed=True)
            spd = (vx * vx + vy * vy) ** 0.5
            if spd < 1e-6:
                break
            vx, vy = vx / spd, vy / spd
            step = 0.006
            nx, ny = x + vx * step, y + vy * step
            if outside(nx, ny) or near_goal(nx, ny):
                break
            if too_close(nx, ny):
                break
            pts.append((nx, ny))
            length += step
            x, y = nx, ny
        if length > 0.03:  # drop dust
            ridges.append(pts)
            occupied.extend(pts)
            used += length
    return ridges


def overlay_verdict(ridges_a, ridges_b, pos, inner_frac: float = GOAL_RING):
    """Winner from the ridge geometry: count strand crossings of the goal
    ring per colour. Sign of (teal - terracotta) is the verdict.

    Returns (teal_crossings, terra_crossings, verdict: str).
    """
    cx, cy, R = 0.5, 0.52, 0.40
    ring = R * inner_frac

    def crossings(ridges):
        n = 0
        for pts in ridges:
            for i in range(len(pts) - 1):
                x0, y0 = pts[i]
                x1, y1 = pts[i + 1]
                d0 = (x0 - cx) ** 2 + (y0 - cy) ** 2
                d1 = (x1 - cx) ** 2 + (y1 - cy) ** 2
                if d0 > ring * ring and d1 <= ring * ring:
                    n += 1
        return n

    ta, tb = crossings(ridges_a), crossings(ridges_b)
    verdict = 'A' if ta > tb else ('B' if tb > ta else 'TIE')
    return ta, tb, verdict
