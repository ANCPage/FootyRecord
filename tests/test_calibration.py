"""Tests for dynamic calibration (audit follow-up 2026-08-10).

Covers: coefficient recovery on synthetic data, no-intercept semantics,
rolling vs expanding window selection, and the too-little-data fallback.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Core'))
import numpy as np

from Core.calibration import MIN_FIT_MATCHES, Calibration, fit_or_fallback, select_window


def _synthetic_rows(n=400, true_b1=1.5, true_b2=0.002, true_m1=1.5,
                    true_m2=0.2, true_total=160.0, seasons=None):
    """Consistent synthetic data: margin determines the win (margin > 0),
    so the probability fit and margin fit recover the same truth.
    FitRow format: (season, round, net, elo, margin, total, actual_delta)."""
    rng = np.random.default_rng(42)
    nets = rng.normal(0, 0.3, n)
    elos = rng.normal(0, 100, n)
    margins = true_m1 * nets + true_m2 * (elos / 100.0) + rng.normal(0, 1.2, n)
    totals = np.full(n, true_total) + rng.normal(0, 25, n)
    actuals = nets + rng.normal(0, 0.1, n)
    if seasons is None:
        seasons = [2024] * n
    rounds = [(i % 23) + 1 for i in range(n)]
    return [(seasons[i], rounds[i], nets[i], elos[i], margins[i], totals[i],
             actuals[i]) for i in range(n)]


def test_fit_recovers_margin_signal():
    """The margin regression (the single calibrated output) recovers the
    generating signal; sign and ratio both correct (cleanest-model: no
    probability layer anymore)."""
    rows = _synthetic_rows(n=5000)
    cal = Calibration.fit([r[2] for r in rows], [r[3] for r in rows],
                          [r[4] for r in rows], [r[5] for r in rows])
    assert cal.margin_b1 > 0 and cal.margin_b2 > 0
    assert cal.n_matches == len(rows)
    # margin_b2 is on elo/100: true_m2 = 0.002 * 100 = 0.2
    assert abs(cal.margin_b2 - 0.2) < 0.1


def test_fit_recovers_margin_and_total():
    rows = _synthetic_rows(n=5000)
    cal = Calibration.fit([r[2] for r in rows], [r[3] for r in rows],
                          [r[4] for r in rows], [r[5] for r in rows],
                          [r[6] for r in rows])
    # margin coefficients recover in ratio (both features scale together)
    true_ratio = 0.2 / 1.5
    fit_ratio = cal.margin_b2 / cal.margin_b1
    assert abs(fit_ratio - true_ratio) / true_ratio < 0.2
    assert abs(cal.total_mean - 160.0) < 3.0


def test_fit_computes_dynamic_margin_divisor():
    rows = _synthetic_rows(n=200)
    acts = [r[6] for r in rows]
    expected = float(np.median(np.abs(acts))) / 1.1
    cal = Calibration.fit([r[2] for r in rows], [r[3] for r in rows],
                          [r[4] for r in rows], [r[5] for r in rows], acts)
    assert abs(cal.margin_divisor - expected) < 1e-9
    assert cal.margin_divisor > 0


def test_tier_cutoffs_and_tier():
    from calibration import compute_tier_cutoffs
    elos = [1400 + i * 12 for i in range(18)]  # 1400..1604
    cutoffs = compute_tier_cutoffs(elos)
    assert len(cutoffs) == 3
    elite_min, contender_min, mid_min = cutoffs
    s = sorted(elos, reverse=True)
    assert elite_min == s[3] and contender_min == s[7] and mid_min == s[12]
    cal = Calibration(tier_cutoffs=cutoffs)
    assert cal.tier(s[0]) == 'ELITE'
    assert cal.tier(s[4]) == 'CONTENDER'
    assert cal.tier(s[8]) == 'MID-TABLE'
    assert cal.tier(s[17]) == 'REBUILDING'
    # small field -> absolute fallback
    assert compute_tier_cutoffs([1500.0, 1501.0]) == ()
    assert Calibration().tier(1650.0) == 'ELITE'


def test_fit_or_fallback_below_min_matches():
    rows = _synthetic_rows(n=MIN_FIT_MATCHES - 10)
    cal = fit_or_fallback(rows, 'roll2')
    assert cal.window == 'fallback'
    assert cal.margin_b1 == Calibration.fallback().margin_b1


def test_fit_or_fallback_above_min_matches():
    rows = _synthetic_rows(n=MIN_FIT_MATCHES + 10)
    cal = fit_or_fallback(rows, 'roll2')
    assert cal.window == 'roll2'
    assert cal.n_matches == len(rows)


def test_select_window_rolling():
    rows = [(2021, 1, 0.0, 0.0, 10.0, 160.0)] * 10
    rows += [(2022, 1, 0.0, 0.0, 10.0, 160.0)] * 10
    rows += [(2023, 1, 0.0, 0.0, 10.0, 160.0)] * 10
    sel = select_window(rows, 2023, 2)
    assert all(r[0] >= 2022 for r in sel)
    assert len(sel) == 20


def test_select_window_expanding():
    rows = [(2021, 1, 0.0, 0.0, 10.0, 160.0)] * 5
    sel = select_window(rows, 2026, None)
    assert len(sel) == 5


def test_margin_and_display_prob_helpers():
    cal = Calibration(margin_b1=50.0, margin_b2=0.0)
    assert cal.margin(0.1, 1.0) == 5.0
    # display-only transform: margin 0 -> 50/50; positive margin -> > 0.5
    assert abs(cal.prob_from_margin(0.0) - 0.5) < 1e-9
    assert cal.prob_from_margin(20.0) > 0.5
    assert cal.prob_from_margin(-20.0) < 0.5


def test_evaluate_aggregate_tuple_layout():
    """Regression: aggregate/run_mode must not confuse tuple positions — a past
    bug squared (season - p) ~ 4e6 and fed won/margin as fit rows. Uses the
    collect_rows layout (7-tuple) that run_mode expects."""
    from evaluate import aggregate, run_mode
    rows = _synthetic_rows(n=120)
    # convert FitRow -> collect_rows layout:
    # (season, round, net, elo, won, margin, total, actual_delta, m_id, home, away)
    rows = [(r[0], r[1], r[2], r[3], r[4] > 0.0, r[4], r[5], r[6],
             f'M{i}', 'H', 'A') for i, r in enumerate(rows)]
    out, _, cals = run_mode(rows, 2, 'roll2')
    n, acc, mae, rmse = aggregate(out)
    assert n == len(out)
    assert 0.0 <= acc <= 1.0
    assert mae >= 0.0
    assert rmse >= 0.0
    assert cals  # per-round calibration provenance captured
    # every row layout: (season, round, margin_pred, won, margin_pred,
    # actual_margin, match_id, home, away, elo_diff)
    for r in out:
        assert isinstance(r[0], int)
        assert isinstance(r[3], (bool, np.bool_))
