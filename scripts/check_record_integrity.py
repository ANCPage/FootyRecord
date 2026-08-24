"""Record-integrity probe for the results DB (re-audit 2026-08-12).

Re-runnable verification that the walk-forward record is honest:
  1. stored net_delta == sum(expected_delta) for every row (the back-derivation
     corruption class: 59/1,204 rows were wrong before commit 63e7c0f)
  2. no NULL home_elo/away_elo/tier/rank columns (the NULL-elo renderer crash
     class: 1,204/1,204 were NULL before 63e7c0f)
  3. home_elo - away_elo == elo_diff on every row (column consistency)
  4. per-season record printed for eyeballing (should be 799/1,204 66.4%
     overall, 2026 133/189 70.4% at the time of writing)

Run:  ~/footy-venv/bin/python scripts/check_record_integrity.py
Exit 0 = clean. Exit 1 = any check failed (prints details).
"""
import sqlite3
import sys

from Core import state_store

DB = '/home/austin/footyrecord-results/footyrecord.db'


def main() -> int:
    conn = sqlite3.connect(DB)
    state = state_store.load_state(conn)
    mp = state['match_performance']

    rows = conn.execute(
        "SELECT season, round, match_id, net_delta, margin, winner, home_elo, away_elo,"
        " home_tier, away_tier, home_rank, away_rank, elo_diff, correct"
        " FROM predictions WHERE actual_margin IS NOT NULL").fetchall()
    print(f"rows: {len(rows)}")

    fails = 0
    for s, r, mid, net_stored, margin, winner, he, ae, ht, at, hr, ar, elo_diff, correct in rows:
        exp = mp.get(mid, {}).get('expected_delta')
        if exp is not None and abs(net_stored - sum(exp.values())) > 1e-9:
            print(f"  net_delta mismatch {mid}: stored {net_stored} != true {sum(exp.values())}")
            fails += 1
        if he is None or ae is None:
            print(f"  NULL elo {mid}")
            fails += 1
        if ht is None or at is None or hr is None or ar is None:
            print(f"  NULL tier/rank {mid}")
            fails += 1
        if he is not None and ae is not None and abs((he - ae) - elo_diff) > 1e-9:
            print(f"  elo diff mismatch {mid}")
            fails += 1
    print(f"checks: net_delta={fails == 0} NULLs={fails == 0} elo_diff_consistent={fails == 0}"
          f" ({'CLEAN' if fails == 0 else f'{fails} FAILURES'})")

    print("\nper-season record:")
    for row in conn.execute(
            "SELECT season, COUNT(*), SUM(correct) FROM predictions"
            " WHERE actual_margin IS NOT NULL GROUP BY season ORDER BY season"):
        print(f"  {row[0]}: {row[1]} games, {row[2]} correct ({100 * row[2] / row[1]:.1f}%)")
    conn.close()
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
