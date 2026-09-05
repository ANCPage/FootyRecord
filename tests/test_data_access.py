"""Phase 2 guards: data access lives in the repositories, paths come from config.

Two rules this locks in:
  1. No script outside Core/ opens its own sqlite connection or inlines SQL —
     analysis and rendering go through Core.results_db / Core.state_store.
  2. No script hardcodes 'CSV_DATA' or 'ROUND_IMAGES_UPDATE' — paths come from
     Core.config, so the tree can move (or be overridden by env) in one place.
"""
import glob
import os
import sqlite3

import Core.config as config
from Core import results_db, state_store

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Scripts allowed to touch SQL directly: the store modules themselves live in
# Core/; evaluate.py owns the record write path (maintenance DDL/DML).
SQL_ALLOWED = {'evaluate.py'}

PATH_LITERALS = ("DataIngestor('CSV_DATA')", '"ROUND_IMAGES_UPDATE"', "'ROUND_IMAGES_UPDATE'")


def _scripts():
    # top-level scripts + the liquid media module: the same data-access rules
    # apply everywhere outside Core/ (liquid imports Core; never touches SQL)
    paths = sorted(glob.glob(os.path.join(REPO, '*.py'))
                   + glob.glob(os.path.join(REPO, 'liquid', '*.py')))
    for path in paths:
        name = os.path.basename(path)
        if name.startswith('test_'):
            continue
        yield name, path


def test_no_script_opens_its_own_sqlite_connection():
    offenders = []
    for name, path in _scripts():
        if name in SQL_ALLOWED:
            continue
        src = open(path).read()
        if 'sqlite3.connect' in src:
            offenders.append(name)
    assert offenders == [], f"scripts opening raw sqlite connections: {offenders}"


def test_no_script_inlines_select_sql():
    offenders = []
    for name, path in _scripts():
        if name in SQL_ALLOWED:
            continue
        src = open(path).read().upper()
        if 'SELECT ' in src and ' FROM ' in src:
            offenders.append(name)
    assert offenders == [], f"scripts with inline SELECT SQL: {offenders}"


def test_no_script_hardcodes_paths():
    offenders = []
    for name, path in _scripts():
        src = open(path).read()
        for lit in PATH_LITERALS:
            if lit in src:
                offenders.append((name, lit))
    assert offenders == [], f"hardcoded paths (use Core.config): {offenders}"


def test_config_exposes_the_three_paths():
    assert os.path.isabs(config.DATA_DIR)
    assert os.path.isabs(config.OUTPUT_DIR)
    assert os.path.isabs(config.RESULTS_DB)
    assert config.RESULTS_DB.endswith('.db')


def test_results_db_path_comes_from_config():
    """One source of truth for the DB location (was duplicated in results_db)."""
    assert results_db.DB_PATH == config.RESULTS_DB


def test_db_path_env_override_documented():
    """FOOTYRECORD_DB is the documented override hook."""
    src = open(os.path.join(REPO, 'Core', 'config.py')).read()
    assert 'FOOTYRECORD_DB' in src


def _seed(conn):
    conn.executescript(results_db.SCHEMA)
    conn.executescript(state_store.SCHEMA)
    conn.execute(
        "INSERT INTO predictions (season, round, match_id, home, away, margin,"
        " actual_margin, correct, grade) VALUES"
        " (2026, 1, 'M1', 'CD_T10', 'CD_T20', 12.0, 20.0, 1, 'B')")
    conn.execute(
        "INSERT INTO predictions (season, round, match_id, home, away, margin,"
        " actual_margin, correct, grade) VALUES"
        " (2026, 1, 'M2', 'CD_T30', 'CD_T40', -5.0, NULL, NULL, 'F')")
    conn.executemany(
        "INSERT INTO chains (m_id, chain_idx, seq, team, outcome, grid, player)"
        " VALUES (?,?,?,?,?,?,?)",
        [('M1', 0, 0, 'CD_T10', 'SCORE', 'C2', 'P1'),
         ('M1', 0, 1, 'CD_T10', 'SCORE', 'D2', 'P2'),
         ('M1', 1, 0, 'CD_T20', 'TURNOVER', 'B1', 'P3')])
    conn.commit()


def test_season_home_teams_returns_played_only():
    conn = sqlite3.connect(':memory:')
    _seed(conn)
    homes = results_db.season_home_teams(conn, 2026)
    assert homes == {'M1': 'CD_T10'}, homes
    conn.close()


def test_season_prediction_rows_shape_and_filter():
    conn = sqlite3.connect(':memory:')
    _seed(conn)
    rows = results_db.season_prediction_rows(conn, 2026)
    assert len(rows) == 1
    rnd, home, away, margin, actual, correct, mid, grade = rows[0]
    assert (rnd, home, away, mid, correct) == (1, 'CD_T10', 'CD_T20', 'M1', 1)
    conn.close()


def test_scoring_chains_groups_and_filters_by_outcome():
    conn = sqlite3.connect(':memory:')
    _seed(conn)
    chains = state_store.scoring_chains(conn)
    assert set(chains.keys()) == {('M1', 0)}, "only SCORE chains, grouped by (m_id, idx)"
    assert chains[('M1', 0)] == [(0, 'CD_T10', 'C2'), (1, 'CD_T10', 'D2')]
    conn.close()
