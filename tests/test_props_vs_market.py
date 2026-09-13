"""Gate C machinery, verified without prices or a model.

The comparison that decides whether the model beats a bookmaker must itself be
trustworthy, so it is tested with a hand-computed fixture: known prices, known
model probabilities, known results.
"""
import math

from Core.tools.props_vs_market import evaluate, two_way_prob


def test_two_way_normalisation_removes_the_margin():
    assert two_way_prob(2.0, 2.0) == 0.5
    # 1.8 / 2.2 -> implied 0.5556 / 0.4545 => 0.55 for the over
    assert abs(two_way_prob(1.8, 2.2) - (0.5556 / (0.5556 + 0.4545))) < 1e-3
    assert two_way_prob(1.0, 2.0) is None       # not a price


def _records():
    return [
        {'m_id': 'M1', 'team': 'T1', 'season': 2026, 'round': 1, 'player_name': 'A Player',
         'line': 0.5, 'over_price': 2.0, 'under_price': 2.0, 'actual_over': True},
        {'m_id': 'M1', 'team': 'T1', 'season': 2026, 'round': 1, 'player_name': 'B Player',
         'line': 0.5, 'over_price': 2.0, 'under_price': 2.0, 'actual_over': False},
    ]


def test_logloss_and_the_pre_declared_rule():
    # model says 0.60 for both, market says 0.50: edge = 0.10 -> both are bets
    prob = {'a player': 0.60, 'b player': 0.60}
    rows, s = evaluate(_records(), None, name_to_id={'a player': 'P1', 'b player': 'P2'},
                       prob_fn=lambda conn, team, season, rnd, pid, line:
                       prob['a player'] if pid == 'P1' else prob['b player'])
    assert s['n'] == 2 and s['bets'] == 2
    # one bet wins at 2.0 (+1), one loses (-1) -> net 0, ROI 0
    assert abs(s['return']) < 1e-9
    assert abs(s['roi']) < 1e-9
    expected_ll = (-math.log(0.6) - math.log(0.4)) / 2
    assert abs(s['logloss_model'] - expected_ll) < 1e-9
    assert abs(s['logloss_market'] - (-math.log(0.5))) < 1e-9
    assert s['logloss_model'] > s['logloss_market']   # the model was worse here


def test_no_edge_means_no_bets():
    rows, s = evaluate(_records(), None, name_to_id={'a player': 'P1', 'b player': 'P2'},
                       prob_fn=lambda *a, **k: 0.50)
    assert s['bets'] == 0 and s['roi'] is None


def test_unmatched_players_are_skipped_not_guessed():
    rows, s = evaluate(_records(), None, name_to_id={}, prob_fn=lambda *a, **k: 0.9)
    assert rows == [] and s == {'n': 0}
