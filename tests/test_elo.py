"""Unit tests for EloEngine: update math and season handling (audit #20)."""
from elo_engine import EloEngine
from models import MatchInfo, TransitionEdge


def test_elo_update_home_win_symmetric():
    d_h, d_a, mult = EloEngine.elo_update(1500.0, 1500.0, 0.5)
    assert d_h > 0 and d_a < 0 and abs(d_h + d_a) < 1e-9
    assert 1.0 < mult <= 3.0


def test_elo_update_away_win():
    d_h, d_a, _ = EloEngine.elo_update(1500.0, 1500.0, -0.5)
    assert d_h < 0 and d_a > 0


def test_elo_update_draw_no_change():
    assert EloEngine.elo_update(1500.0, 1500.0, 0.0) == (0.0, 0.0, 0.0)


def test_elo_update_favorite_gains_less_than_upset():
    d_fav, _, _ = EloEngine.elo_update(1550.0, 1500.0, 0.2)
    d_dog, _, _ = EloEngine.elo_update(1500.0, 1550.0, 0.2)
    assert 0 < d_fav < 32
    assert d_dog > d_fav


def test_elo_history_progression():
    eng = EloEngine()
    matches = ['m1', 'm2']
    info = {
        'm1': MatchInfo(season=2026, round=1, home='H', away='A'),
        'm2': MatchInfo(season=2026, round=2, home='A', away='H'),
    }
    e = TransitionEdge('E2', 'SCORE')
    m_h = {e: 0.9}
    m_a = {e: 0.1}
    # tuple is (home_matrix, away_matrix): m2 has A at home
    mats = {'m1': (m_h, m_a), 'm2': (m_a, m_h)}
    hist = eng.compute_elo_history(matches, info, mats)
    # rating BEFORE first match is the baseline
    assert hist['H'][0][1] == 1500.0
    # H won m1 (delta > 0) -> stronger going into m2
    assert hist['H'][1][1] > 1500.0
    assert hist['A'][1][1] < 1500.0
    # final post-match entry exists
    assert hist['H'][-1][0].startswith('POST_')


def test_season_regression_applied():
    eng = EloEngine()
    matches = ['m1', 'm2', 'm3']
    info = {
        'm1': MatchInfo(season=2025, round=1, home='H', away='A'),
        'm2': MatchInfo(season=2025, round=2, home='A', away='H'),
        'm3': MatchInfo(season=2026, round=1, home='H', away='A'),
    }
    e = TransitionEdge('E2', 'SCORE')
    m_h = {e: 0.9}
    m_a = {e: 0.1}
    # note: matrix tuple is (home_matrix, away_matrix) per match
    mats = {'m1': (m_h, m_a), 'm2': (m_a, m_h), 'm3': (m_h, m_a)}
    eng.compute_elo_history(matches, info, mats)
    assert eng.season_start_elos['H'][2025] == 1500.0
    start_2026 = eng.season_start_elos['H'][2026]
    assert 1500.0 < start_2026 < 1700.0  # regressed from 2025 end, above baseline


def test_elo_winner_uses_delta_not_scores():
    # A team can win the scoreboard but lose the tactical delta; Elo follows
    # the delta (delta-Elo design, E1).
    eng = EloEngine()
    matches = ['m1']
    info = {'m1': MatchInfo(season=2026, round=1, home='H', away='A',
                            home_score=100, away_score=80)}  # H won on scoreboard
    e = TransitionEdge('E2', 'SCORE')
    mats = {'m1': ({e: 0.1}, {e: 0.9})}  # ... but delta favours A
    hist = eng.compute_elo_history(matches, info, mats)
    assert hist['A'][0][1] < hist['A'][-1][1]  # A's rating rose


def test_elo_update_divisor_override():
    """E1 A/B: explicit divisor (results-Elo uses median score margin / 1.1)."""
    d_h, d_a, mult = EloEngine.elo_update(1500, 1500, 30.0, divisor=27.0)
    assert mult == min(3.0, max(0.5, 30.0 / 27.0 + 1.0))
    assert d_h > 0 and d_a < 0  # positive delta -> home wins
