"""Golden-record guard (Phase 0 of the architecture-debt closure, 2026-08-26).

The walk-forward record is the project's single source of truth. Every
refactor in the closure plan must leave it byte-identical — this test is the
tripwire. If a refactor changes a prediction, this fails loudly.

Values verified against the DB on 2026-08-26 (v8 cache, post POST_-purge):
    all seasons : 813 / 1222  (66.5%)
    2026        : 147 /  207  (71.0%)

If the record legitimately changes (new rounds ingested, or Austin signs off
on a hyperparameter refit), update GOLDEN in the same commit and say why.
"""
import pytest

from Core import results_db

GOLDEN_ALL = (813, 1222)
GOLDEN_2026 = (147, 207)

PLAYED = "correct IS NOT NULL"


def _record(conn, where_extra: str = "") -> tuple:
    sql = f"SELECT COALESCE(SUM(correct), 0), COUNT(*) FROM predictions WHERE {PLAYED}{where_extra}"
    row = conn.execute(sql).fetchone()
    return (row[0], row[1])


@pytest.fixture()
def conn():
    if not results_db.db_exists():
        pytest.skip("results DB not present on this host")
    c = results_db.connect()
    yield c
    c.close()


def test_all_seasons_record_unchanged(conn):
    assert _record(conn) == GOLDEN_ALL


def test_2026_record_unchanged(conn):
    assert _record(conn, " AND season=2026") == GOLDEN_2026


def test_season_summary_matches_golden(conn):
    """The summary helper (single source of truth) must agree with the golden values."""
    s_c, s_t = results_db.cumulative_record(conn, 2026, 24)
    assert (s_c, s_t) == GOLDEN_2026


def test_no_duplicate_predictions(conn):
    """(season, round, match_id) is the PK — a duplicate would silently inflate the record."""
    dupes = conn.execute(
        "SELECT season, round, match_id, COUNT(*) c FROM predictions "
        "GROUP BY season, round, match_id HAVING c > 1"
    ).fetchall()
    assert dupes == [], f"duplicate prediction rows: {dupes[:5]}"


def test_correct_flag_consistent_with_margins(conn):
    """correct must equal (predicted winner side == actual winner side) for played games.

    Guards the decision rule itself: margin and actual_margin must share a sign
    when correct=1, and differ when correct=0 (draws excluded — they count as misses).
    """
    bad = conn.execute(
        "SELECT season, round, match_id, margin, actual_margin, correct "
        "FROM predictions WHERE correct IS NOT NULL AND actual_margin != 0 "
        "AND ((margin > 0) = (actual_margin > 0)) != (correct = 1)"
    ).fetchall()
    assert bad == [], f"correct flag disagrees with margin signs: {bad[:5]}"
