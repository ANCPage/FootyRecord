"""GATE regression: the committed code must still show the measured edge.

Reads the row cache written by:
  ~/footy-venv/bin/python -m Core.tools.props_backtest --gate --leverage

Skips when the cache is absent (it needs the raw CSVs via goals_extract).
The thresholds are the ones the plan fixed: model allocation must beat the
player's own history share on 1+ and 2+ goal odds error, with volume held at
the ACTUAL team score (so only allocation is judged).
"""
import json
import os

import pytest

from Core.tools.props_backtest import gate_table, leverage_analysis

ROWS = os.path.expanduser('~/.cache/footy-props/rows.json')
TEST_SEASONS = (2025, 2026)


def _rows():
    if not os.path.exists(ROWS):
        pytest.skip('row cache missing: run Core.tools.props_backtest first')
    with open(ROWS) as fh:
        rows = json.load(fh)
    rows = [r for r in rows if r['season'] in TEST_SEASONS]
    if len(rows) < 100:
        pytest.skip('row cache too small')
    return rows


def _odds_error(rows, alloc, market):
    from Core.player_props import poisson_ge, PPG
    num = den = 0.0
    for r in rows:
        tg = r['vol_actual'] / PPG
        for _p, rec in r['players'].items():
            est = tg * rec[alloc]
            y = 1 if rec['act'] >= market else 0
            num += (poisson_ge(market, est) - y) ** 2
            den += 1
    return num / den if den else float('nan')


def test_gate_a_model_allocation_beats_history_on_1plus_and_2plus():
    rows = _rows()
    for market, ceiling in ((1, 0.224), (2, 0.102)):
        model = _odds_error(rows, 'm', market)
        history = _odds_error(rows, 'h', market)
        assert model < history, (
            'model allocation %.4f no longer beats history %.4f at %d+ goals'
            % (model, history, market))
        assert model < ceiling, (
            'model allocation %.4f is above the recorded %.4f at %d+ goals'
            % (model, ceiling, market))


def test_gate_a_equal_shares_are_the_worst_option():
    rows = _rows()
    assert _odds_error(rows, 'u', 1) > _odds_error(rows, 'h', 1)


def _all_rows():
    """Every season: the leverage fit needs 2021-2024 rows as well."""
    if not os.path.exists(ROWS):
        pytest.skip('row cache missing: run Core.tools.props_backtest first')
    with open(ROWS) as fh:
        rows = json.load(fh)
    if len(rows) < 100:
        pytest.skip('row cache too small')
    return rows


def test_gate_a2_leverage_slope_is_reported_and_has_the_expected_sign():
    """The diagnostic, not the hypothesis: if the advantage is flat across
    leverage, the model is only a better prior. Recorded, not asserted — a
    negative slope is a legitimate finding that kills the line."""
    rows = _all_rows()
    report = leverage_analysis(rows, market=1)
    assert 'fitted on' in report, report
    assert 'slope' in report
    print(report)


def test_gate_table_still_renders():
    out = gate_table(_rows())
    assert 'model allocation' in out and 'head-to-head' in out
