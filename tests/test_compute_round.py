"""Live-round path test (compute_round on an UNPLAYED round).

Guards the one-store-era live path: predictions written for an unplayed round
must have no actuals, a correct=0 default, and a valid calibration snapshot
(the old 'window_seasons' key bug lived here undetected).
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Core'))

import compute_round
import results_db
from engine_data import DataIngestor

COLUMNS = ['matchId', 'round', 'season', 'homeTeamId', 'awayTeamId',
           'venueLength', 'venueWidth', 'chain_period', 'stat_periodSeconds',
           'x', 'y', 'stat_playerId', 'stat_description', 'stat_teamId',
           'chain_index', 'chain_teamId', 'chain_finalState_class', 'stat_class']


def _fixture(csv_dir):
    """Two teams, R1 played (scores), R2 unplayed (scores 0)."""
    os.makedirs(csv_dir, exist_ok=True)
    path = os.path.join(csv_dir, 'flattened_stats_2026.csv')
    rows = []
    for rnd, played in [(1, True), (2, False)]:
        for cid, team in [(0, 'H'), (1, 'A')]:
            rows.append(['CD_M2026%03d' % rnd, rnd, 2026, 'H', 'A', 170, 130,
                         1, 10, 70, 0, f'P{cid}', 'Goal', team, cid, team,
                         'SCORE', 'SCORE'])
            rows.append(['CD_M2026%03d' % rnd, rnd, 2026, 'H', 'A', 170, 130,
                         2, 20, 55, 0, f'P{cid}', 'Goal', team, cid, team,
                         'SCORE', 'SCORE'])
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    # scores: R1 played -> attach after ingestion via the matches table
    return path


def _scores(conn, m_id, hs, as_):
    conn.execute('UPDATE matches SET home_score=?, away_score=? WHERE m_id=?',
                 (hs, as_, m_id))
    conn.commit()


def test_compute_round_live_path(tmp_path):
    csv_dir = str(tmp_path / 'csv')
    db = str(tmp_path / 'test.db')
    _fixture(csv_dir)

    ing = DataIngestor(csv_dir, db_path=db)
    ing.load_all_data()
    if not ing.team_positions:
        ing.profile_all_teams()  # mirrors compute_round.load_ingestor
    conn = results_db.connect(db)
    _scores(conn, 'CD_M2026001', 90, 60)
    # R1 is played -> guard must refuse it
    refused = compute_round.compute_round(ing, conn, 2026, 1)
    assert refused == 0, 'played round must not be computed by the live path'
    # R2 is unplayed -> live compute
    n = compute_round.compute_round(ing, conn, 2026, 2)
    assert n > 0, 'unplayed round must produce predictions'

    rows = results_db.load_round(conn, 2026, 2)
    assert len(rows) == n
    for r in rows:
        assert r['actual_margin'] is None, 'live round must have no actuals'
        assert r['correct'] == 0
    # calibration snapshot present and schema-valid
    snap = conn.execute('SELECT decay, margin_b1, window FROM calibration_log '
                        'WHERE season=2026 AND round=2').fetchone()
    assert snap is not None and snap[1] != 0.0 and int(snap[2]) == 2
    conn.close()
