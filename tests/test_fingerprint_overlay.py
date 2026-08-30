"""Tests for the fingerprint overlay (2026-08-30, Austin's idea).

The load-bearing identity: sum(delta) == net_a - net_b — the prediction is
literally the balance of the overlay. Also locks the facts that make the
overlay honest (normalised fingerprints -> encode balance not size) and
legible (shot edges carry the sign decision).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from Core.engine_core import MatchupEngine, fingerprint_overlay
from Core.models import TransitionEdge


def T(s, t):
    return TransitionEdge(s, t)


def test_overlay_identity():
    """sum(delta) == net_a - net_b, EXACTLY, with rotation in play."""
    a = {T('C2', 'D2'): 0.30, T('E2', 'SCORE'): 0.20, T('A2', 'SCORE'): -0.10}
    b = {T('C2', 'D2'): 0.10, T('E3', 'SCORE'): 0.25, T('A3', 'SCORE'): -0.05}
    delta, net_a, net_b = fingerprint_overlay(a, b)
    assert sum(delta.values()) == pytest.approx(net_a - net_b, abs=1e-12)
    # and the winner is the sign of that balance
    assert (net_a - net_b > 0) == (sum(delta.values()) > 0)


def test_overlay_empty_second():
    """B missing: delta == A's own matrix (rotation is a bijection, so a
    matrix that contributes nothing maps to nothing)."""
    a = {T('E2', 'SCORE'): 0.4}
    delta, net_a, net_b = fingerprint_overlay(a, {})
    assert net_b == 0.0
    assert sum(delta.values()) == pytest.approx(net_a)


def test_normalised_fingerprints_encode_balance_not_size():
    """Both fingerprints normalise to ~equal total weight — the overlay must
    not be readable as 'bigger wins'. The REAL teams all sum|w| within 1%."""
    from Core.engine_core import fingerprint_overlay as _unused  # noqa: F401
    # two fingerprints of identical total weight, different balance
    a = {T('E2', 'SCORE'): 0.3, T('A2', 'SCORE'): -0.2}
    b = {T('E2', 'SCORE'): 0.1, T('A2', 'SCORE'): -0.4}
    assert sum(abs(v) for v in a.values()) == pytest.approx(
        sum(abs(v) for v in b.values()))
    _, net_a, net_b = fingerprint_overlay(a, b)
    assert net_a != net_b  # same size, different balance -> overlay reads balance


def test_shot_edges_dominate_the_decision():
    """Across 2026 real fingerprints: shot-edge sign matches full-delta sign
    in the overwhelming majority of pairs (measured 95.4%) — so the whorl's
    inner ring (shots) is where the verdict visually lives."""
    import Core.config as config
    from Core.engine_data import DataIngestor
    from Core.mappings import TEAM_DATA

    ing = DataIngestor(config.DATA_DIR)
    ing.load_all_data(light=True)
    mats = {t: m for t in TEAM_DATA
            for m in [ing.get_team_average_matrix(t, up_to_season=2026,
                                                  up_to_round=25)] if m}
    ids = list(mats)
    agree = total = 0
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            d = MatchupEngine.calculate_delta(mats[x], mats[y])
            s = sum(v for e, v in d.items() if e.target == 'SCORE')
            t = sum(d.values())
            if t == 0:
                continue
            total += 1
            if (s > 0) == (t > 0):
                agree += 1
    assert agree / total > 0.9  # measured 0.954 — allow headroom


def test_render_smoke_single_and_overlay(tmp_path):
    """Both modes render a 900x1200 PNG without error."""
    import Core.config as config
    from Core.engine_data import DataIngestor
    from Core.mappings import TEAM_DATA
    from Core.visualize_matchup import MatchupVisualizer

    ing = DataIngestor(config.DATA_DIR)
    ing.load_all_data(light=True)
    v = MatchupVisualizer()

    frem = [t for t in TEAM_DATA if TEAM_DATA[t]['name'] == 'Fremantle'][0]
    syd = [t for t in TEAM_DATA if TEAM_DATA[t]['name'] == 'Sydney Swans'][0]
    m_f = ing.get_team_average_matrix(frem, up_to_season=2026, up_to_round=25)
    m_s = ing.get_team_average_matrix(syd, up_to_season=2026, up_to_round=25)

    out_single = str(tmp_path / 'single.png')
    out_overlay = str(tmp_path / 'overlay.png')
    v.draw_fingerprint(frem, None, m_f, {}, 2026, 25, out_single, single=True)
    v.draw_fingerprint(frem, syd, m_f, m_s, 2026, 25, out_overlay,
                              single=False, net_a=None, net_b=None, delta=None)

    from PIL import Image
    for p in (out_single, out_overlay):
        im = Image.open(p)
        assert im.size == (900, 1200)


def test_single_mode_ridge_balance_matches_weight_share():
    """The all-one-colour regression: a conceding team's fingerprint must be
    roughly proportional to its own scoring vs conceded weight share — NOT
    dominated by the conceded colour because its teal ridges died in the
    negative flow (2026-08-30, caught by Austin eyeballing North's card)."""
    import Core.config as config
    from Core.engine_data import DataIngestor
    from Core.fingerprint_field import (
        balance_ridges,
        build_field,
        node_positions,
        trace_streamlines,
    )
    from Core.mappings import TEAM_DATA
    from Core.visualize_matchup import _whorl_seeds

    ing = DataIngestor(config.DATA_DIR)
    ing.load_all_data(light=True)
    tid = [t for t in TEAM_DATA if TEAM_DATA[t]['name'] == 'North Melbourne'][0]
    m = ing.get_team_average_matrix(tid, up_to_season=2026, up_to_round=25)
    pos = sum(v for v in m.values() if v > 0)
    neg = sum(-v for v in m.values() if v < 0)
    tot = pos + neg
    pos_share = pos / tot

    field = build_field(m, node_positions())
    seeds = _whorl_seeds(48, rings=2, jitter=1.4)
    rp = trace_streamlines(field, seeds, node_positions(), 26.0 * pos_share,
                           fx=field['xp'], fy=field['yp'])
    rn = trace_streamlines(field, seeds, node_positions(), 26.0 * (1 - pos_share),
                           fx=field['xn'], fy=field['yn'])
    rp, rn = balance_ridges(rp, rn, pos_share)  # the renderer's own step
    len_p = sum(len(r) for r in rp)
    len_n = sum(len(r) for r in rn)
    share = len_p / max(len_p + len_n, 1)
    # North is 46.9/53.1 — the rendered balance must be within 12 points of
    # the data balance (tracing is stochastic; it must not be 99/1)
    assert abs(share - pos_share) < 0.12, \
        f'ridge balance {share:.2f} vs data share {pos_share:.2f}'


def test_delta_field_colour_matches_verdict_sign():
    """The overlay's colour balance must AGREE with the banner's verdict.

    This is the readability fix (2026-08-30, Austin: "I wouldn't understand
    if it's telling me North was better, or Sydney"). The overlay traces the
    DELTA field, so the dominant colour IS the winner — if this test fails,
    the picture contradicts the number and the card lies.
    """
    import Core.config as config
    from Core.engine_core import fingerprint_overlay
    from Core.engine_data import DataIngestor
    from Core.fingerprint_field import (
        balance_ridges, build_delta_field, node_positions, trace_streamlines,
    )
    from Core.mappings import TEAM_DATA
    from Core.visualize_matchup import _whorl_seeds

    ing = DataIngestor(config.DATA_DIR)
    ing.load_all_data(light=True)
    north = [t for t in TEAM_DATA if TEAM_DATA[t]['name'] == 'North Melbourne'][0]
    syd = [t for t in TEAM_DATA if TEAM_DATA[t]['name'] == 'Sydney Swans'][0]
    m_n = ing.get_team_average_matrix(north, up_to_season=2026, up_to_round=25)
    m_s = ing.get_team_average_matrix(syd, up_to_season=2026, up_to_round=25)

    delta, net_a, net_b = fingerprint_overlay(m_n, m_s)
    net = net_a - net_b
    pos = node_positions()
    dfield = build_delta_field(delta, pos)
    seeds = _whorl_seeds(56, rings=2, jitter=1.4)
    d_pos = sum(v for v in delta.values() if v > 0)
    d_neg = sum(-v for v in delta.values() if v < 0)
    share = d_pos / (d_pos + d_neg)
    rt = trace_streamlines(dfield, seeds, pos, 38.0 * share,
                           fx=dfield['xp'], fy=dfield['yp'])
    rr = trace_streamlines(dfield, seeds, pos, 38.0 * (1 - share),
                           fx=dfield['xn'], fy=dfield['yn'])
    rt, rr = balance_ridges(rt, rr, share)
    teal_len = sum(len(r) for r in rt)
    terra_len = sum(len(r) for r in rr)

    # Sydney has the better net balance, so the delta favours THEM: the
    # terracotta (B-wins) ridges must dominate, matching the banner.
    assert net < 0, 'Sydney should have the better net balance'
    assert terra_len > teal_len, (
        f'picture contradicts the verdict: teal {teal_len} vs terra {terra_len} '
        f'for net {net:+.4f}')
