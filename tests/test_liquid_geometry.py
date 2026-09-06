"""Shared-web lattice guarantees (Austin-approved geometry, 2026-09-06).

The liquid card's 15 zones are the centres of real positions on ONE
oval-bounded mesh. The guarantees below are what make it a *shared* web:
- the two teams trace the IDENTICAL lattice (exact 180-symmetry), and
- every node stays inside the chrome oval the canvas draws.
Both are pinned so a future geometry tweak can't silently break them.
"""
import json
import math
import os

from liquid import geom
from Core.geometry import GRID_NAMES, flip_positions


def _theme():
    return json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'liquid', 'theme.json')))


def _in_chrome_oval(p):
    x, y = geom.to_px([p])[0]
    f = _theme()['field']
    return ((x - f['cx']) / f['rx']) ** 2 + ((y - f['cy']) / f['ry']) ** 2 <= 1.0


def test_geom_reads_theme_single_source():
    f = _theme()['field']
    assert (geom.FIELD['cx'], geom.FIELD['cy'],
            geom.FIELD['rx'], geom.FIELD['ry']) == (f['cx'], f['cy'], f['rx'], f['ry'])
    p = _theme()['projection']
    assert (geom.PROJ['y']['margin'], geom.PROJ['y']['scale']) == \
           (p['y']['margin'], p['y']['scale'])


def test_shared_lattice_exact():
    """Both teams' node sets are the SAME set: flip(pos) == pos exactly."""
    pos = geom.field_positions()
    zones = [k for k in pos if k != 'SCORE']
    aset = {tuple(round(v, 9) for v in pos[z]) for z in zones}
    bset = {tuple(round(v, 9) for v in flip_positions(pos)[z]) for z in zones}
    assert aset == bset
    # and every A node has its exact mirror inside the set (no near-misses)
    for z in zones:
        b = flip_positions(pos)[z]
        d = min(math.hypot(b[0] - pos[w][0], b[1] - pos[w][1]) for w in zones)
        assert d < 1e-9, 'lattice gap %.6f for %s' % (d, z)


def test_all_nodes_inside_chrome_oval():
    pos = geom.field_positions()
    zones = [k for k in pos if k != 'SCORE']
    assert all(_in_chrome_oval(pos[z]) for z in zones), \
        [z for z in zones if not _in_chrome_oval(pos[z])]
    assert all(_in_chrome_oval(flip_positions(pos)[z]) for z in zones)


def test_bands_even_and_full_field():
    """5 even depth bands spanning the full field; wings spread wide at the
    centre and converge toward the goals (a real ground map, not a column),
    but INBOARD of the boundary — each node is the centre of its corridor,
    not the line itself."""
    pos = geom.field_positions()
    centre = sorted({pos[z][1] for z in pos if z != 'SCORE'
                     and abs(pos[z][0] - 0.5) < 1e-9})
    assert len(centre) == 5
    gaps = {round(centre[i + 1] - centre[i], 6) for i in range(4)}
    assert len(gaps) == 1, 'bands not even: %s' % centre
    assert centre[0] < 0.20 and centre[-1] > 0.80      # reaches both ends
    # wing spread at the centre band: well wide of the column but inboard of
    # the boundary (boundary edge = 0.5 - hw(centre) ~ 0.16)
    hw = geom._oval_half_width(0.5)
    c1 = pos['C1'][0]
    assert 0.5 - 0.9 * hw < c1 < 0.5 - 0.4 * hw, 'wing x %.3f out of corridor' % c1
    # pockets converge: A-row wings closer to the centre line than C-row
    assert (0.5 - pos['A1'][0]) < (0.5 - pos['C1'][0])
    assert GRID_NAMES and pos['SCORE'] == (0.5, 0.92)
