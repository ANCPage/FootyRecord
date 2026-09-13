"""Contract tests for the player-goals estimator.

Read-only is the load-bearing property: the model's stored outputs must be
byte-identical with this layer on and off. Data-bound tests skip when the DB is
unavailable (the code mirror has no results DB).
"""
import hashlib
import os
import sqlite3

import pytest

import Core.chains as chains


def _conn():
    try:
        conn = chains.connect()
    except Exception as exc:                      # pragma: no cover
        pytest.skip('no results DB: %s' % exc)
    n = conn.execute('SELECT COUNT(*) FROM player_history').fetchone()[0]
    if n < 100:
        pytest.skip('no player history in DB')
    return conn


def _fixture(conn):
    """A 2026 fixture with a stored prediction and history for both teams."""
    row = conn.execute(
        "SELECT p.season, p.round, p.home, p.away FROM predictions p "
        "WHERE p.season=2026 AND p.delta IS NOT NULL AND p.delta != '' "
        "ORDER BY p.round DESC LIMIT 1").fetchone()
    if not row:
        pytest.skip('no stored predictions with a delta')
    return row


def _db_hash(conn):
    h = hashlib.sha256()
    for table in ('predictions', 'matches', 'chains'):
        h.update(table.encode())
        for r in conn.execute('SELECT * FROM %s ORDER BY 1' % table):
            h.update(repr(r).encode())
    return h.hexdigest()


def test_shares_sum_to_one():
    from Core.player_props import prop_estimates
    conn = _conn()
    season, rnd, home, _away = _fixture(conn)
    est = prop_estimates(conn, home, season, rnd, team_goal_total=12.0)
    assert est, 'no estimates produced'
    assert abs(sum(v['share'] for v in est.values()) - 1.0) < 1e-9


def test_expected_goals_scale_linearly_with_the_supplied_volume():
    from Core.player_props import prop_estimates
    conn = _conn()
    season, rnd, home, _away = _fixture(conn)
    a = prop_estimates(conn, home, season, rnd, team_goal_total=10.0)
    b = prop_estimates(conn, home, season, rnd, team_goal_total=20.0)
    for p in a:
        assert b[p]['expected_goals'] == pytest.approx(2 * a[p]['expected_goals'], rel=1e-9)
        assert b[p]['share'] == pytest.approx(a[p]['share'], rel=1e-12)


def test_probabilities_are_monotone_and_bounded():
    from Core.player_props import prop_estimates
    conn = _conn()
    season, rnd, home, _away = _fixture(conn)
    est = prop_estimates(conn, home, season, rnd, team_goal_total=12.0)
    for v in est.values():
        assert 0.0 <= v['p_4plus'] <= v['p_3plus'] <= v['p_2plus'] <= v['p_1plus'] <= 1.0


def test_volume_falls_back_to_the_prior_not_the_model():
    """No team total supplied -> the walk-forward prior average, never the
    model's projected score."""
    from Core.player_props import prop_estimates, prior_average_score, PPG
    conn = _conn()
    season, rnd, home, _away = _fixture(conn)
    est = prop_estimates(conn, home, season, rnd)
    total = next(iter(est.values()))['team_goal_total']
    prior = prior_average_score(conn, home, season, rnd)
    if prior is not None:
        assert total == pytest.approx(prior / PPG)
    projected = conn.execute(
        'SELECT home_score, away_score FROM predictions WHERE season=? AND round=? AND home=?',
        (season, rnd, home)).fetchone()
    if projected:
        assert total not in (projected[0], projected[1]) or prior is not None


def test_lineup_filter_drops_unselected_players_and_renormalises():
    from Core.player_props import prop_estimates
    conn = _conn()
    season, rnd, home, _away = _fixture(conn)
    full = prop_estimates(conn, home, season, rnd, team_goal_total=12.0)
    keep = sorted(full)[:10]
    filtered = prop_estimates(conn, home, season, rnd, team_goal_total=12.0, lineup=keep)
    assert set(filtered) == set(keep)
    assert abs(sum(v['share'] for v in filtered.values()) - 1.0) < 1e-9


def test_layer_is_read_only():
    from Core.player_props import prop_estimates
    conn = _conn()
    season, rnd, home, _away = _fixture(conn)
    before = _db_hash(conn)
    prop_estimates(conn, home, season, rnd, team_goal_total=12.0)
    after = _db_hash(conn)
    assert before == after, 'player_props wrote to the model DB'
