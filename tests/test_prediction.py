"""Smoke tests for the shared matchup computation (reuse pass #7).

Uses the same synthetic two-team fixture as test_integration — no real data.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Core'))

from Core.engine_data import DataIngestor
from Core.prediction import compute_matchup

COLUMNS = ['matchId', 'round', 'season', 'homeTeamId', 'awayTeamId',
           'venueLength', 'venueWidth', 'chain_period', 'stat_periodSeconds',
           'x', 'y', 'stat_playerId', 'stat_description', 'stat_teamId',
           'chain_index', 'chain_teamId', 'chain_finalState_class', 'stat_class']


def _make_ingestor(tmp_path):
    csv_dir = str(tmp_path)
    path = os.path.join(csv_dir, 'flattened_stats_2026.csv')
    rows = []
    # 4 matches so profiles exist before round 3; each team scores a goal
    # from its own forward pocket each game (home H / away A alternating)
    for m_idx, (h, a) in enumerate([('H', 'A'), ('A', 'H'), ('H', 'A'), ('A', 'H')], 1):
        for cid, team in [(0, h), (1, a)]:
            rows.append([f'CD_M202600{m_idx}', m_idx, 2026, h, a, 170, 130,
                         1, 10, 70, 0, f'P{m_idx}{cid}', 'Goal', team, cid,
                         team, 'SCORE', 'SCORE'])
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    ing = DataIngestor(csv_dir, db_path=str(tmp_path / 'test.db'))
    ing.load_all_data()
    ing.profile_all_teams()
    return ing


def test_compute_matchup_returns_full_prediction(tmp_path):
    ing = _make_ingestor(tmp_path)
    pred = compute_matchup(ing, 'H', 'A', 2026, 4)
    assert pred is not None
    assert pred.winner_id in ('H', 'A')
    assert pred.home == 'H' and pred.away == 'A'
    assert pred.net_delta == sum(pred.delta.values())
    assert 0.0 < pred.prob_home < 1.0
    assert pred.home_score >= 10 and pred.away_score >= 10
    assert pred.h_elo > 1000 and pred.a_elo > 1000
    assert pred.h_tier in ('ELITE', 'CONTENDER', 'MID-TABLE', 'REBUILDING')
    assert pred.a_rank >= 1 and pred.h_rank >= 1
    # winner consistent with the decision edge (dead-even -> higher Elo)
    from engine_core import home_favored
    assert pred.winner_id == ('H' if home_favored(pred.net_delta, pred.h_elo, pred.a_elo) else 'A')


def test_compute_matchup_elo_overrides(tmp_path):
    ing = _make_ingestor(tmp_path)
    pred = compute_matchup(ing, 'H', 'A', 2026, 4, elo_overrides={'H': 1800.0})
    assert pred.h_elo == 1800.0


def test_compute_matchup_missing_profiles_returns_none(tmp_path):
    csv_dir = str(tmp_path)
    ing = DataIngestor(csv_dir, db_path=str(tmp_path / 'test.db'))  # no data at all
    ing.load_all_data()
    ing.profile_all_teams()
    assert compute_matchup(ing, 'X', 'Y', 2026, 1) is None
