"""State-sync gate tests (2026-09-12).

Verification only: these assert the checks FIRE on the two failure modes that
bit us in production — a stale fit and data silently dropped at ingest — and
that a consistent state passes silently. No model numbers are produced here.
"""
import os
import sqlite3
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import Core.state_store as state_store  # noqa: E402
from Core.calibration import Calibration  # noqa: E402


def _db_with_fit(tmp_path, fit_fingerprint='abc123', source='fitted'):
    conn = state_store.connect(str(tmp_path / 'state.db'))
    conn.execute(
        'INSERT OR REPLACE INTO calibration (id, decay, margin_b1, margin_b2,'
        ' total_mean, divisor, window, n_matches, tier_cutoffs, fitted_at,'
        ' fit_fingerprint, fit_n_matches, source)'
        ' VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)',
        (0.5, 110.03, 3.48, 164.9, 0.271, 'roll2', 422, '[]', 'test',
         fit_fingerprint, 1237, source))
    conn.commit()
    return conn


def _fake_ing(match_ids, source='fitted'):
    return types.SimpleNamespace(
        match_info={m: None for m in match_ids},
        calibration=Calibration(margin_b1=110.03, margin_b2=3.48,
                                total_mean=164.9, source=source))


def test_consistent_state_passes(tmp_path):
    conn = _db_with_fit(tmp_path, fit_fingerprint='fp-current')
    ing = _fake_ing({'CD_M1', 'CD_M2'})
    rep = state_store.verify_state(conn, ing, csv_fingerprint='fp-current',
                                   csv_match_ids={'CD_M1', 'CD_M2'})
    assert rep['ok'] is True
    assert rep['coverage_ok'] and rep['provenance_ok']
    assert rep['warnings'] == []


def test_stale_fit_is_flagged(tmp_path):
    """The fit was made from different data than we're using now."""
    conn = _db_with_fit(tmp_path, fit_fingerprint='fp-old')
    ing = _fake_ing({'CD_M1'})
    rep = state_store.verify_state(conn, ing, csv_fingerprint='fp-new',
                                   csv_match_ids={'CD_M1'})
    assert rep['ok'] is False
    assert rep['provenance_ok'] is False
    assert any('PROVENANCE' in w for w in rep['warnings'])
    with pytest.raises(ValueError):
        state_store.verify_state(conn, ing, csv_fingerprint='fp-new',
                                 csv_match_ids={'CD_M1'}, strict=True)


def test_dropped_data_is_flagged(tmp_path):
    """Today's finals bug: the CSVs contain matches the state never ingested."""
    conn = _db_with_fit(tmp_path, fit_fingerprint='fp')
    ing = _fake_ing({'CD_M1'})          # state lost CD_M2 / CD_M3
    rep = state_store.verify_state(conn, ing, csv_fingerprint='fp',
                                   csv_match_ids={'CD_M1', 'CD_M2', 'CD_M3'})
    assert rep['coverage_ok'] is False
    assert rep['missing'] == ['CD_M2', 'CD_M3']
    with pytest.raises(ValueError):
        state_store.verify_state(conn, ing, csv_fingerprint='fp',
                                 csv_match_ids={'CD_M1', 'CD_M2', 'CD_M3'},
                                 strict=True)


def test_fallback_source_is_flagged(tmp_path):
    conn = _db_with_fit(tmp_path, fit_fingerprint='fp', source='fallback')
    ing = _fake_ing({'CD_M1'}, source='fallback')
    rep = state_store.verify_state(conn, ing, csv_fingerprint='fp',
                                   csv_match_ids={'CD_M1'})
    assert rep['source'] == 'fallback'
    assert any('fallback' in w.lower() for w in rep['warnings'])


def test_migration_adds_columns_to_old_db(tmp_path):
    """An older DB without the provenance columns must migrate additively."""
    p = str(tmp_path / 'old.db')
    c = sqlite3.connect(p)
    c.execute('CREATE TABLE calibration (id INTEGER PRIMARY KEY CHECK (id=1),'
              ' decay REAL, margin_b1 REAL, margin_b2 REAL, total_mean REAL,'
              ' divisor REAL, window TEXT, n_matches INTEGER, tier_cutoffs TEXT,'
              ' fitted_at TEXT)')
    c.execute('INSERT INTO calibration VALUES (1,0.5,110,3.5,165,0.27,"roll2",10,"[]","x")')
    c.commit()
    c.close()
    conn = state_store.connect(p)          # runs the additive migration
    cols = {r[1] for r in conn.execute('PRAGMA table_info(calibration)')}
    assert {'fit_fingerprint', 'fit_n_matches', 'source'} <= cols
    row = conn.execute('SELECT margin_b1, fit_fingerprint, source FROM calibration').fetchone()
    assert row[0] == 110                   # existing values untouched
    assert row[1] == '' and row[2] == 'fitted'
