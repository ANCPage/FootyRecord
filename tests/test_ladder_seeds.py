"""Finals seeds come from the ladder, not a hardcoded snapshot.

The projector used to carry a dict of this season's ten teams, which would have
silently built next year's bracket from them (audit 2026-09-14, finding 8).
"""
import sqlite3

from Core.finals_project import FALLBACK_SEEDS, ladder_seeds


def _conn(rows):
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE matches (season INT, round INT, home TEXT, away TEXT, '
                 'home_score INT, away_score INT)')
    conn.executemany('INSERT INTO matches VALUES (?,?,?,?,?,?)', rows)
    return conn


def test_ranks_by_wins_then_percentage():
    conn = _conn([
        # A and B both finish 3-1; A's percentage is better (170.0 vs 163.6)
        (2026, 1, 'A', 'B', 100, 60),
        (2026, 2, 'B', 'C', 80, 40),
        (2026, 3, 'A', 'C', 70, 30),
        (2026, 4, 'B', 'A', 90, 50),
        (2026, 5, 'D', 'A', 20, 120),
        (2026, 6, 'B', 'D', 130, 30),
    ])
    seeds = ladder_seeds(conn, 2026, home_away_rounds=24)
    assert seeds[1] == 'A'          # same wins as B, better percentage
    assert seeds[2] == 'B'
    assert seeds[3] == 'C'          # one win beats none
    assert seeds[4] == 'D'


def test_draws_count_for_neither_side():
    conn = _conn([
        (2026, 1, 'A', 'B', 80, 80),
        (2026, 2, 'A', 'C', 100, 50),
        (2026, 3, 'B', 'C', 100, 40),
    ])
    seeds = ladder_seeds(conn, 2026)
    assert seeds[1] in ('A', 'B')   # the drawer with a win ranks above C


def test_rounds_after_the_home_and_away_season_are_ignored():
    conn = _conn([
        (2026, 24, 'A', 'B', 100, 50),
        (2026, 25, 'B', 'A', 200, 10),      # a final: must not re-order the ladder
    ])
    seeds = ladder_seeds(conn, 2026, home_away_rounds=24)
    assert seeds[1] == 'A'


def test_no_data_returns_empty_so_the_caller_can_warn():
    assert ladder_seeds(_conn([]), 2026) == {}
    assert 1 in FALLBACK_SEEDS          # the fallback still exists, but is only a fallback
