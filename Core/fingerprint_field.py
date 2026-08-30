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

    radius = depth from goal (A-row outermost/deepest, E-row hugging the
    goal); angle = lane (rows 1..3 spread symmetrically around the top).

    NOTE (2026-08-30, caught by a subagent's comprehension question): the
    original implementation had this SWAPPED — lane->radius, depth->angle —
    which put E1 (the attacking end) on the outermost ring next to A1 (the
    defensive end), silently contradicting the docstring and the design.
    """
    import math

    from Core.geometry import GRID_NAMES

    cx, cy, R = 0.5, 0.52, 0.40
    pos = {}
    for lane_i, row in enumerate(GRID_NAMES):   # GRID_NAMES rows = lanes 1..3
        for depth_i, name in enumerate(row):    # GRID_NAMES cols = depth A..E
            radius = R * (0.20 + 0.76 * (4 - depth_i) / 4.0)
            angle = math.radians(90 + (lane_i - 1) * 38)
            pos[name] = (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
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


def build_delta_field(delta: Dict[TransitionEdge, float],
                      pos: Dict[str, Tuple[float, float]],
                      sigma: float = 0.045):
    """Field of the DELTA between two teams (2026-08-30).

    The overlay MUST show the difference, not both teams' full fields.
    Showing both at full strength is a semantic overload: every edge carries
    two meanings at once and — because fingerprints are equal-ink — the card
    reads as a 50/50 tangle no matter who is winning. Austin: "I wouldn't
    understand if it's telling me North was better, or Sydney."

    With the delta field:
      teal ridges  = zones where A wins the flow (delta > 0)
      red ridges   = zones where B wins the flow (delta < 0)
      bare cream   = zones where they're equal (delta ~ 0) — genuine
                     information, not empty space
    So a red-heavy card literally MEANS B is winning, which is what the
    banner says. The picture becomes the verdict instead of hiding it.

    Returns the same dict shape as build_field: xp/yp carry the positive
    (A-winning) flow, xn/yn the negative (B-winning) flow.
    """
    return build_field(delta, pos, sigma=sigma)


def _sample_grid(grid, x, y):
    """Bilinear sample of a field grid at (x, y); NaN-safe outside [0,1]."""
    gx = np.clip(x, 0, 1) * (GRID - 1)
    gy = np.clip(y, 0, 1) * (GRID - 1)
    i0, j0 = int(gx), int(gy)
    i1, j1 = min(i0 + 1, GRID - 1), min(j0 + 1, GRID - 1)
    tx, ty = gx - i0, gy - j0
    return (grid[i0, j0] * (1 - tx) * (1 - ty) + grid[i1, j0] * tx * (1 - ty)
            + grid[i0, j1] * (1 - tx) * ty + grid[i1, j1] * tx * ty)


def trace_streamlines(field, seeds, pos, budget: float, fx=None, fy=None,
                      min_spacing: float = MIN_SPACING,
                      max_len: float = MAX_LEN) -> List[List[Tuple[float, float]]]:
    """Trace ridges from seeds through a field.

    fx/fy: the velocity grids to follow. Callers choose:
      - signed field  (field['x'], field['y'])     — net flow (overlay mode)
      - positive-only (field['xp'], field['yp'])   — own scoring flow
      - negative-only (field['xn'], field['yn'])   — conceded flow
    Tracing a colour through the wrong field is the classic "all one colour"
    bug (2026-08-30: single mode traced both colours through the signed
    field; a conceding team's teal ridges died in their own negative flow).

    Returns list of ridge polylines (in field coords). Stops when:
      - the equal-ink budget (total traced length) is exhausted
      - a step would come within min_spacing of an existing ridge
      - the streamline leaves the whorl area or hits the goal ring
      - max_len reached without progress
    """
    if fx is None:
        fx, fy = field['x'], field['y']

    cx, cy, R = 0.5, 0.52, 0.40
    inner = R * GOAL_RING

    def outside(x, y):
        return (x - cx) ** 2 + (y - cy) ** 2 > R * R

    def near_goal(x, y):
        return (x - cx) ** 2 + (y - cy) ** 2 < inner * inner

    occupied = []  # points already drawn, for min-spacing

    def too_close(x, y):
        if not occupied:
            return False
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
            if length > max_len:  # 2026-08-30: was MISSING — a streamline in
                break             # a circulating field ran 4000 steps, ate the
                                  # whole colour's ink budget in one ridge
            vx, vy = _sample_grid(fx, x, y), _sample_grid(fy, x, y)
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


def balance_ridges(ridges_a, ridges_b, target_a_share: float):
    """Enforce the equal-ink colour balance structurally.

    The trace budget is a CAP, not a target — one colour's field can be more
    continuous than the other's, so its ridges over-consume and the visual
    balance drifts from the data's weight share (2026-08-30: North's teal hit
    63% against a 46.9% data share). Trimming the OVER-represented colour's
    SHORTEST ridges picks the closest achievable ratio to the weight ratio
    (ridges are indivisible, so exact hits aren't always possible — the first
    naive loop dropped ALL of a colour when a single ridge overshot).
    Returns (trimmed_a, trimmed_b).
    """
    def total(ridges):
        return sum(len(r) for r in ridges)

    la, lb = total(ridges_a), total(ridges_b)
    if la + lb == 0:
        return ridges_a, ridges_b
    share = la / (la + lb)

    def best_trim(ordered, fixed_total, target):
        """Drop shortest ridges; return the subset closest to target."""
        best, best_err = list(ordered), abs(total(ordered) / (total(ordered) + fixed_total) - target)
        for i in range(1, len(ordered)):
            cand = ordered[i:]
            if not cand:
                break
            s = total(cand) / (total(cand) + fixed_total)
            err = abs(s - target)
            if err < best_err:
                best, best_err = cand, err
            elif s < target:  # ratio decreases monotonically; stop past target
                break
        return best

    if share > target_a_share:
        return best_trim(sorted(ridges_a, key=len), lb, target_a_share), ridges_b
    if share < target_a_share:
        return ridges_a, best_trim(sorted(ridges_b, key=len), la, 1.0 - target_a_share)
    return ridges_a, ridges_b


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
