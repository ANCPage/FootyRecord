"""SQLite results store (compute/render separation, 2026-08-11).

Path A (compute_round.py) writes predictions + calibration provenance here.
Path B (render_round.py / generate_round_images.py) reads decisions from here.
Analysis reads the same file: `SELECT ... WHERE correct = 0 AND margin > 30`.

One DB, all seasons. Stdlib sqlite3 only.
"""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    season INTEGER, round INTEGER, match_id TEXT,
    home TEXT, away TEXT,
    net_delta REAL, elo_diff REAL, margin REAL, winner TEXT,
    home_elo REAL, away_elo REAL,
    home_tier TEXT, away_tier TEXT, home_rank INTEGER, away_rank INTEGER,
    total REAL, home_score INTEGER, away_score INTEGER, grade TEXT,
    actual_margin REAL, correct INTEGER,
    PRIMARY KEY (season, round, match_id)
);
CREATE TABLE IF NOT EXISTS calibration_log (
    season INTEGER, round INTEGER,
    decay REAL, margin_b1 REAL, margin_b2 REAL, total_mean REAL,
    divisor REAL, window_seasons INTEGER,
    fitted_at TEXT,
    PRIMARY KEY (season, round)
);
"""

DB_PATH = os.path.expanduser('~/footyrecord-results/footyrecord.db')
# LOCAL on purpose: SQLite needs byte-range locks, which the SMB mount
# (NAS) can't provide (tested 2026-08-11: fresh file -> "database is locked").
# The DB is analysis data, not a repo artifact — the Pi is where it's used.


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def upsert_round(conn, season: int, round_num: int, games: list, calibration: dict) -> int:
    """Insert/replace one round's predictions + calibration snapshot.
    games: list of dicts with the keys of the predictions table.
    Returns the number of games written."""
    conn.executemany(
        "INSERT OR REPLACE INTO predictions (season, round, match_id, home, away,"
        " net_delta, elo_diff, margin, winner, home_elo, away_elo, home_tier, away_tier,"
        " home_rank, away_rank, total, home_score, away_score, grade, actual_margin, correct)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(g['season'], g['round'], g['match_id'], g['home'], g['away'], g['net_delta'],
          g['elo_diff'], g['margin'], g['winner'], g['home_elo'], g['away_elo'],
          g['home_tier'], g['away_tier'], g['home_rank'], g['away_rank'], g['total'],
          g['home_score'], g['away_score'], g['grade'], g['actual_margin'], g['correct'])
         for g in games],
    )
    conn.execute(
        "INSERT OR REPLACE INTO calibration_log (season, round, decay, margin_b1, margin_b2,"
        " total_mean, divisor, window_seasons, fitted_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (season, round_num, calibration['decay'], calibration['margin_b1'],
         calibration['margin_b2'], calibration['total_mean'], calibration['divisor'],
         calibration['window_seasons'], calibration['fitted_at']),
    )
    conn.commit()
    return len(games)


def load_round(conn, season: int, round_num: int) -> list:
    cur = conn.execute(
        "SELECT season, round, match_id, home, away, net_delta, elo_diff, margin, winner,"
        " home_elo, away_elo, home_tier, away_tier, home_rank, away_rank, total,"
        " home_score, away_score, grade, actual_margin, correct"
        " FROM predictions WHERE season = ? AND round = ? ORDER BY match_id",
        (season, round_num))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def cumulative_record(conn, season: int, through_round: int) -> tuple:
    """(correct, total) for all predictions through the given round."""
    row = conn.execute(
        "SELECT COALESCE(SUM(correct), 0), COUNT(*) FROM predictions"
        " WHERE season = ? AND round <= ?",
        (season, through_round)).fetchone()
    return (int(row[0]), int(row[1]))


def team_records(conn, season: int, through_round: int) -> dict:
    """Per-team (wins, losses) from prediction outcomes through the round."""
    rows = conn.execute(
        "SELECT home, away, winner FROM predictions"
        " WHERE season = ? AND round <= ? AND correct IS NOT NULL",
        (season, through_round)).fetchall()
    rec = {}
    for home, away, winner in rows:
        for team in (home, away):
            rec.setdefault(team, [0, 0])
        rec[winner][0] += 1
        loser = away if winner == home else home
        rec[loser][1] += 1
    return rec
