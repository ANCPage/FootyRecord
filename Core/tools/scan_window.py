"""Fit the trailing-total window by MEASUREMENT instead of taste.

Context (2026-09-14): the magic-numbers pass deleted a 60-match trailing window and
replaced it with a season-derived rule. Measured afterwards, the replacement was
worse: mean absolute totals bias 1.76 against 1.27. Deleting a number that works, in
favour of a derivation that works less well, is the wrong trade — the fix is to FIT
the window length, not to remove it.

This script scores candidate window lengths on the metric that matters (per-season
totals bias from a full walk-forward rebuild) and prints the winner. It writes only to
a probe table and drops it.

Usage:
  FOOTYRECORD_DATA_DIR=/mnt/projects/FootyRecord/CSV_DATA \
    ~/footy-venv/bin/python /tmp/scan_window.py
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, '/home/austin/footyrecord-local')
os.chdir('/home/austin/footyrecord-local')

import Core.calibration as calibration  # noqa: E402
import Core.config as config  # noqa: E402
from Core.engine_data import DataIngestor  # noqa: E402
from Core.tools import rerecord  # noqa: E402

DB = os.path.expanduser('~/footyrecord-results/footyrecord.db')
CANDIDATES = [None, 30, 60, 90, 120]     # None = the season-derived rule in the code


def totals_bias(conn, table):
    """Per-season mean (projected total - actual total) and mean |bias|."""
    out = {}
    # `total` is the PROJECTED total; home_score/away_score hold the stored ACTUALS
    # (audit finding 16). So the projected total is p.total, never p.home_score+p.away_score.
    q = ('SELECT p.season, AVG(p.total'
         ' - (m.home_score + m.away_score)) '
         'FROM %s p JOIN matches m ON m.m_id = p.match_id '
         'WHERE m.home_score IS NOT NULL GROUP BY p.season ORDER BY p.season' % table)
    try:
        out = dict(conn.execute(q).fetchall())
    except sqlite3.OperationalError as e:
        print('  ! query failed: %s' % e)
    return out


def main():
    ing = DataIngestor(config.DATA_DIR)
    ing.load_all_data()
    conn = sqlite3.connect(DB)
    results = {}
    for w in CANDIDATES:
        t0 = time.time()
        calibration.TRAILING_WINDOW_FIT = w          # read by _trailing_total
        table = 'predictions_wprobe'
        rerecord.rebuild(ing, conn, table=table, verbose=False)
        bias = totals_bias(conn, table)
        mad = sum(abs(v) for v in bias.values()) / len(bias) if bias else float('nan')
        label = 'season-derived' if w is None else '%d matches' % w
        print('window %-15s mean|bias| %.3f   per season %s   (%.0fs)'
              % (label, mad, ' '.join('%d:%+.2f' % kv for kv in sorted(bias.items())),
                 time.time() - t0), flush=True)
        results[w] = (mad, bias)
        conn.execute('DROP TABLE IF EXISTS %s' % table)
        conn.commit()

    best = min(results, key=lambda k: results[k][0])
    print('\nBEST by mean absolute totals bias: %s (%.3f)'
          % ('season-derived' if best is None else '%d matches' % best, results[best][0]))
    print('the shipped rule would be: %s' % ('season-derived' if best is None else '%d' % best))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
