"""Unit tests for the 2026-08-26 minimal-architecture wins:

- single source of truth for the record summary (round_summary / format_summary)
- schema indexes (chains m_id/outcome, predictions season/round)
- the stale-artifact guard (render_round_from_db wipes the round dir first)
"""

import pytest

from Core import results_db, state_store


def _game(season, rnd, correct, played=True, mid=None):
    return {
        'season': season, 'round': rnd,
        'match_id': mid or f'CD_M{season}14{rnd:02d}{correct}{played}',
        'home': 'CD_T100', 'away': 'CD_T110',
        'net_delta': 0.1, 'elo_diff': 0.0, 'margin': 20.0, 'winner': 'CD_T100',
        'home_elo': 1500, 'away_elo': 1500,
        'home_tier': 'MID', 'away_tier': 'MID',
        'home_rank': 1, 'away_rank': 2,
        'total': 170, 'home_score': 95, 'away_score': 75, 'grade': 'C',
        'actual_margin': 20 if played else None,
        'correct': correct, 'delta': None,
    }


@pytest.fixture()
def conn(tmp_path):
    c = results_db.connect(str(tmp_path / 't.db'))
    yield c
    c.close()


def test_round_summary_counts_played_only(conn):
    for g in (_game(2026, 1, 1, mid='CD_M2026140101'),
              _game(2026, 1, 1, mid='CD_M2026140102'),
              _game(2026, 1, 0, mid='CD_M2026140103'),
              _game(2026, 1, 0, played=False, mid='CD_M2026140104')):
        results_db.upsert_prediction(conn, g)
    conn.commit()
    assert results_db.round_summary(conn, 2026, 1) == (2, 3)  # unplayed NOT counted


def test_round_summary_ignores_other_rounds_and_seasons(conn):
    for g in (_game(2026, 1, 1, mid='CD_M2026140101'),
              _game(2026, 2, 0, mid='CD_M2026140201'),
              _game(2025, 1, 1, mid='CD_M2025140101')):
        results_db.upsert_prediction(conn, g)
    conn.commit()
    assert results_db.round_summary(conn, 2026, 1) == (1, 1)
    assert results_db.round_summary(conn, 2026, 2) == (0, 1)
    assert results_db.round_summary(conn, 2025, 1) == (1, 1)


def test_cumulative_equals_sum_of_rounds(conn):
    games = (_game(2026, 1, 1, mid='CD_M2026140101'),
             _game(2026, 1, 0, mid='CD_M2026140102'),
             _game(2026, 2, 1, mid='CD_M2026140201'),
             _game(2026, 2, 1, mid='CD_M2026140202'))
    for g in games:
        results_db.upsert_prediction(conn, g)
    conn.commit()
    r1 = results_db.round_summary(conn, 2026, 1)
    r2 = results_db.round_summary(conn, 2026, 2)
    s = results_db.cumulative_record(conn, 2026, 2)
    assert (r1[0] + r2[0], r1[1] + r2[1]) == s


def test_format_summary_exact_string():
    assert results_db.format_summary(24, 6, 9, 147, 207) == \
        'ROUND 24 TIPS: 6/9 | SEASON: 147/207 (71.0%)'


def test_format_summary_zero_total_no_crash():
    s = results_db.format_summary(1, 0, 0, 0, 0)
    assert 'ROUND 1 TIPS: 0/0' in s


def test_summary_matches_stored_rows(conn):
    """The renderer's card summary must equal what the rows say (no drift)."""
    games = [_game(2026, 24, 1, mid=f'CD_M202614240{i:02d}') for i in range(7)] + \
            [_game(2026, 24, 0, mid='CD_M2026142499')]
    for g in games:
        results_db.upsert_prediction(conn, g)
    conn.commit()
    correct, total = results_db.round_summary(conn, 2026, 24)
    rows = results_db.load_round(conn, 2026, 24)
    assert correct == sum(1 for r in rows if r['correct'])
    assert total == sum(1 for r in rows if r['actual_margin'] is not None)


def test_schema_indexes_created(tmp_path):
    """Both schemas create the perf indexes (idempotent on every connect)."""
    db = str(tmp_path / 'idx.db')
    c = results_db.connect(db)
    names = {r[1] for r in c.execute('PRAGMA index_list(predictions)')}
    assert 'idx_predictions_season_round' in names
    c.close()
    c = state_store.connect(db)
    names = {r[1] for r in c.execute('PRAGMA index_list(chains)')}
    assert {'idx_chains_mid', 'idx_chains_outcome'} <= names
    c.close()


def test_stale_artifact_guard_wipes_round_dir(monkeypatch, tmp_path):
    """render_round_from_db deletes the round output dir BEFORE rendering —
    a failed re-render can never leave old cards behind for --resume."""
    from generate_round_images import _stale_round_dir
    monkeypatch.chdir(tmp_path)
    stale = tmp_path / 'ROUND_IMAGES_UPDATE' / '2026' / 'R24' / 'Mobile' / 'InstaPost'
    stale.mkdir(parents=True)
    (stale / 'TIPS_RESULTS.png').write_bytes(b'old')
    (stale / 'ladder.png').write_bytes(b'old')
    _stale_round_dir(2026, 24)  # wipes the round dir
    assert not (tmp_path / 'ROUND_IMAGES_UPDATE' / '2026' / 'R24').exists()


def test_stale_guard_absent_dir_is_noop(monkeypatch, tmp_path):
    from generate_round_images import _stale_round_dir
    monkeypatch.chdir(tmp_path)
    _stale_round_dir(2026, 24)  # no dir — must not raise
