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

import _guards

pytestmark = pytest.mark.needs_data

from Core import results_db

# RE-BASELINED 2026-09-14: the scoreboard was corrected to the official feed (audit
# finding 14) and the season projections were re-recorded, then promoted over the
# stored set. The counts below are the RE-RECORDED record; the pre-correction set is
# archived in `predictions_pre_rescore_20260914` (813/1222) if you need to compare.
GOLDEN_ALL = (822, 1232)
GOLDEN_2026 = (150, 217)            # all rounds, incl. the played finals
GOLDEN_2026_SUMMARY = (145, 207)    # cumulative_record(2026, 24) = home-and-away only

PLAYED = "correct IS NOT NULL"


def _record(conn, where_extra: str = "") -> tuple:
    sql = f"SELECT COALESCE(SUM(correct), 0), COUNT(*) FROM predictions WHERE {PLAYED}{where_extra}"
    row = conn.execute(sql).fetchone()
    return (row[0], row[1])


@pytest.fixture()
def conn():
    _guards.require(results_db.db_exists(), 'results DB not present on this host')
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
    assert (s_c, s_t) == GOLDEN_2026_SUMMARY


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

    Dead-even projections are handled separately (added 2026-09-14, after the
    re-record): when the model's net delta is exactly even the margin is 0 and the
    winner is decided by the documented Elo tie-break, so the margin sign cannot
    carry the verdict there. The pre-correction record contained no such rows, which
    is why the original rule did not allow for them.
    """
    bad = conn.execute(
        "SELECT season, round, match_id, margin, actual_margin, correct "
        "FROM predictions WHERE correct IS NOT NULL AND actual_margin != 0 AND margin != 0 "
        "AND ((margin > 0) = (actual_margin > 0)) != (correct = 1)"
    ).fetchall()
    assert bad == [], f"correct flag disagrees with margin signs: {bad[:5]}"

    bad_even = conn.execute(
        "SELECT season, round, match_id, winner, home, away, actual_margin, correct "
        "FROM predictions WHERE correct IS NOT NULL AND actual_margin != 0 AND margin = 0 "
        "AND (correct = 1) != ((winner = home AND actual_margin > 0) "
        "                      OR (winner = away AND actual_margin < 0))"
    ).fetchall()
    assert bad_even == [], (
        f"dead-even rows where the winner/graded flag disagree: {bad_even[:5]}")
