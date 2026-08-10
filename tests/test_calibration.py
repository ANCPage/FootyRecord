"""Tests for dynamic calibration (audit follow-up 2026-08-10).

Covers: coefficient recovery on synthetic data, no-intercept semantics,
rolling vs expanding window selection, and the too-little-data fallback.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Core'))
import numpy as np
from calibration import MIN_FIT_MATCHES, Calibration, fit_or_fallback, select_window


def _synthetic_rows(n=400, true_b1=1.5, true_b2=0.002, true_m1=1.5,
                    true_m2=0.2, true_total=160.0, seasons=None):
    """Consistent synthetic data: margin determines the win (margin > 0),
    so the probability fit and margin fit recover the same truth."""
    rng = np.random.default_rng(42)
    nets = rng.normal(0, 0.3, n)
    elos = rng.normal(0, 100, n)
    margins = true_m1 * nets + true_m2 * (elos / 100.0) + rng.normal(0, 1.2, n)
    totals = np.full(n, true_total) + rng.normal(0, 25, n)
    if seasons is None:
        seasons = [2024] * n
    rounds = [(i % 23) + 1 for i in range(n)]
    return [(seasons[i], rounds[i], nets[i], elos[i], margins[i], totals[i])
            for i in range(n)]


def test_fit_recovers_probability_coefficients():
    rows = _synthetic_rows(n=5000)
    cal = Calibration.fit([r[2] for r in rows], [r[3] for r in rows],
                          [r[4] for r in rows], [r[5] for r in rows])
    # Logistic fit on probit-generated wins recovers the SIGNAL, not the exact
    # scale (logit-vs-probit approximation is not exactly proportional at heavy
    # tails) — assert sign, no-intercept, and high correlation with the truth.
    nets = np.array([r[2] for r in rows])
    elos = np.array([r[3] for r in rows])
    true_logit = 1.5 * nets + 0.002 * elos
    fit_logit = cal.logit(nets, elos)
    assert np.corrcoef(true_logit, fit_logit)[0, 1] > 0.99
    assert cal.prob_b1 > 0 and cal.prob_b2 > 0
    assert cal.prob_b0 == 0.0  # no venue advantage, by design
    assert cal.n_matches == len(rows)


def test_fit_recovers_margin_and_total():
    rows = _synthetic_rows(n=5000)
    cal = Calibration.fit([r[2] for r in rows], [r[3] for r in rows],
                          [r[4] for r in rows], [r[5] for r in rows])
    # margin coefficients recover in ratio (both features scale together)
    true_ratio = 0.2 / 1.5
    fit_ratio = cal.margin_b2 / cal.margin_b1
    assert abs(fit_ratio - true_ratio) / true_ratio < 0.2
    assert abs(cal.total_mean - 160.0) < 3.0


def test_fit_or_fallback_below_min_matches():
    rows = _synthetic_rows(n=MIN_FIT_MATCHES - 10)
    cal = fit_or_fallback(rows, 'roll2')
    assert cal.window == 'fallback'
    assert cal.prob_b1 == Calibration.fallback().prob_b1


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


def test_prob_home_and_margin_helpers():
    cal = Calibration(prob_b1=1.0, prob_b2=0.0, margin_b1=50.0, margin_b2=0.0)
    assert abs(cal.prob_home(1.0, 0.0) - 1.0 / (1.0 + math.exp(-1.0))) < 1e-9
    assert cal.margin(0.1, 1.0) == 5.0 + 0.0
    assert cal.logit(0.0, 0.0) == 0.0


def test_evaluate_aggregate_tuple_layout():
    """Regression: aggregate/run_mode must not confuse tuple positions — a past
    bug squared (season - p) ~ 4e6 and fed won/margin as fit rows. Uses the
    collect_rows layout (7-tuple) that run_mode expects."""
    from evaluate import aggregate, run_mode
    rows = _synthetic_rows(n=120)
    # convert FitRow -> collect_rows layout: (season, round, net, elo, won, margin, total)
    rows = [(r[0], r[1], r[2], r[3], r[4] > 0.0, r[4], r[5]) for r in rows]
    out, _ = run_mode(rows, 2, 'roll2')
    n, acc, brier, mae, rmse = aggregate(out)
    assert n == len(out)
    assert 0.0 <= acc <= 1.0
    assert 0.0 <= brier <= 1.0
    assert mae >= 0.0
    # every row layout: (season, p, won, margin_pred, actual_margin)
    for r in out:
        assert isinstance(r[0], int)
        assert 0.0 <= r[1] <= 1.0
        assert isinstance(r[2], (bool, np.bool_))
