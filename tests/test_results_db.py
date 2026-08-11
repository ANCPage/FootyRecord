"""Tests for the SQLite results store (compute/render separation)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Core'))

import results_db


def _game(mid='CD_M20260140101', home='H', away='A', margin=12.0, correct=1,
          actual_margin=8, winner='H', round_num=1):
    return {'season': 2026, 'round': round_num, 'match_id': mid, 'home': home, 'away': away,
            'net_delta': 0.1, 'elo_diff': 0.0, 'margin': margin, 'winner': winner,
            'home_elo': 1500.0, 'away_elo': 1490.0, 'home_tier': 'MID-TABLE',
            'away_tier': 'MID-TABLE', 'home_rank': 5, 'away_rank': 6,
            'total': 160.0, 'home_score': 86, 'away_score': 78,
            'grade': 'C', 'actual_margin': actual_margin, 'correct': correct,
            'delta': None}


def test_schema_and_upsert_round(tmp_path):
    db = os.path.join(str(tmp_path), 'test.db')
    conn = results_db.connect(db)
    n = results_db.upsert_round(conn, 2026, 1, [_game()], {
        'decay': 0.5, 'margin_b1': 109.0, 'margin_b2': 3.5, 'total_mean': 164.0,
        'divisor': 0.3, 'window_seasons': 2, 'fitted_at': '2026-08-11T00:00:00+00:00'})
    assert n == 1
    rows = results_db.load_round(conn, 2026, 1)
    assert len(rows) == 1
    assert rows[0]['winner'] == 'H'
    assert rows[0]['margin'] == 12.0
    conn.close()


def test_upsert_is_idempotent(tmp_path):
    db = os.path.join(str(tmp_path), 'test.db')
    conn = results_db.connect(db)
    snap = {'decay': 0.5, 'margin_b1': 1, 'margin_b2': 1, 'total_mean': 1,
            'divisor': 1, 'window_seasons': 2, 'fitted_at': 'x'}
    results_db.upsert_round(conn, 2026, 1, [_game()], snap)
    results_db.upsert_round(conn, 2026, 1, [_game(margin=14.0)], snap)
    rows = results_db.load_round(conn, 2026, 1)
    assert len(rows) == 1          # replaced, not duplicated
    assert rows[0]['margin'] == 14.0
    conn.close()


def test_cumulative_and_team_records(tmp_path):
    db = os.path.join(str(tmp_path), 'test.db')
    conn = results_db.connect(db)
    snap = {'decay': 0.5, 'margin_b1': 1, 'margin_b2': 1, 'total_mean': 1,
            'divisor': 1, 'window_seasons': 2, 'fitted_at': 'x'}
    results_db.upsert_round(conn, 2026, 1, [_game(correct=1), _game(mid='CD_M20260140102', home='C', away='D', winner='C', actual_margin=-4, correct=0)], snap)
    results_db.upsert_round(conn, 2026, 2, [_game(mid='CD_M20260140201', home='H', away='D', winner='H', correct=1, round_num=2)], snap)
    assert results_db.cumulative_record(conn, 2026, 1) == (1, 2)
    assert results_db.cumulative_record(conn, 2026, 2) == (2, 3)
    rec = results_db.team_records(conn, 2026, 2)
    assert rec['H'] == [2, 0]   # won R1 vs A, won R2 vs D
    assert rec['C'] == [1, 0]
    assert rec['D'] == [0, 2]   # lost to C, lost to H
    conn.close()
