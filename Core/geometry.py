"""Single source of truth for pitch geometry (audit E11 / #13).

Consolidates the copies of the oval->5x3 grid mapping that previously lived
in engine_data, engine_scraper and models, and the 180-degree rotation that
was duplicated in engine_core, predict_game, visualize_story and the renderer.
This duplication is what produced the LFP->FB bug class — one copy got
"fixed" differently. Change grid math HERE only.
"""
import math

GRID_NAMES = [
    ["A1", "B1", "C1", "D1", "E1"],
    ["A2", "B2", "C2", "D2", "E2"],
    ["A3", "B3", "C3", "D3", "E3"],
]
POS_MAP = {name: (r, c) for r, row in enumerate(GRID_NAMES)
           for c, name in enumerate(row)}
MAX_R, MAX_C = 2, 4


def xy_to_grid(nx, ny, venue_length, venue_width) -> str:
    """Map physical (x, y) metres onto the 5x3 grid (A1..E3).

    Coordinates are in the possessing team's frame (forward end = +x),
    normalised to the venue's half-length/half-width and squircle-mapped
    onto the oval. Points outside the oval are clamped to the boundary.
    Empty/invalid input returns ''.
    """
    if nx in ("", None) or ny in ("", None) or not venue_length or not venue_width:
        return ""
    try:
        nx, ny, venue_length, venue_width = (float(nx), float(ny),
                                             float(venue_length), float(venue_width))
    except (ValueError, TypeError):
        return ""
    a = venue_length / 2.0
    b = venue_width / 2.0
    u = nx / a
    v = ny / b
    r_sq = u ** 2 + v ** 2
    if r_sq > 1.0:
        norm = math.sqrt(r_sq)
        u /= norm
        v /= norm
    if u == 0 and v == 0:
        sx, sy = 0.0, 0.0
    elif abs(u) >= abs(v):
        if u > 0:
            sx = math.sqrt(u ** 2 + v ** 2)
            sy = sx * (4 / math.pi) * math.atan2(v, u)
        else:
            sx = -math.sqrt(u ** 2 + v ** 2)
            sy = -sx * (4 / math.pi) * math.atan2(v, -u)
    else:
        if v > 0:
            sy = math.sqrt(u ** 2 + v ** 2)
            sx = sy * (4 / math.pi) * math.atan2(u, v)
        else:
            sy = -math.sqrt(u ** 2 + v ** 2)
            sx = -sy * (4 / math.pi) * math.atan2(u, -v)
    col_idx = max(0, min(4, int((sx + 1.0) / 2.0 * 5)))
    row_idx = max(0, min(2, int((sy + 1.0) / 2.0 * 3)))
    return f"{'ABCDE'[col_idx]}{'123'[row_idx]}"


def rotate_node(name: str) -> str:
    """180-degree rotation (team frame <-> home frame). SCORE stays put."""
    if name == 'SCORE' or name not in POS_MAP:
        return name
    r, c = POS_MAP[name]
    return GRID_NAMES[MAX_R - r][MAX_C - c]


def flip_positions(pos_map: dict) -> dict:
    """Mirror a zone->(x, y) map across the centre (1-x, 1-y): the away
    frame's view of the same geometry. THE one spelling of the projection
    flip (dedup audit 2026-09-05, item 3)."""
    return {k: (1.0 - x, 1.0 - y) for k, (x, y) in pos_map.items()}
