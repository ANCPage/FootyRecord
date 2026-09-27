"""Promote the re-recorded projections over the stored ones.

WHY: the stored `predictions` were built while the stored scores were light (audit
finding 14) — scorelines ~9 points light, eight winners wrong, ratings updated from
those results. The rebuilt set is the same model, the same walk-forward convention
and the same fitted-at-ingest calibration, but on corrected inputs.

Both sets share the project's documented semantics ("calibration fitted at ingest on
a rolling window, applied to every round"), so promoting the corrected one does not
change what a prediction MEANS — only whether its inputs were right.

The old set is ARCHIVED, never dropped: it is the evidence of what was published at
the time, and the audit references it.

Usage:
  ~/footy-venv/bin/python -m Core.tools.promote_rebuilt --archive predictions_pre_rescore_20260914
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import Core.chains as chains  # noqa: E402
import Core.results_db as results_db  # noqa: E402

DEFAULT_SOURCE = 'predictions_rebuilt'


def promote(conn, source=DEFAULT_SOURCE, archive='predictions_pre_rescore_20260914',
            dry_run=False):
    cols = [d[1] for d in conn.execute('PRAGMA table_info(%s)' % source)]
    if not cols:
        raise SystemExit('no source table %r — run Core.tools.rerecord first' % source)
    stored = conn.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]
    rebuilt = conn.execute('SELECT COUNT(*) FROM %s' % source).fetchone()[0]
    if not rebuilt:
        raise SystemExit('source table %r is empty' % source)
    print('stored   : %d rows' % stored)
    print('rebuilt  : %d rows' % rebuilt)
    if dry_run:
        print('dry run — nothing written')
        return {'stored': stored, 'rebuilt': rebuilt, 'promoted': False}

    conn.execute('DROP TABLE IF EXISTS %s' % archive)
    conn.execute('CREATE TABLE %s AS SELECT * FROM predictions' % archive)
    conn.execute('DELETE FROM predictions')
    conn.execute('INSERT INTO predictions (%s) SELECT %s FROM %s'
                 % (', '.join(cols), ', '.join(cols), source))
    conn.commit()
    after = conn.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]
    are = conn.execute('SELECT COUNT(*) FROM %s' % archive).fetchone()[0]
    print('promoted: predictions now holds %d rows (%s) | archived %d rows as %s'
          % (after, source, are, archive))
    return {'stored': stored, 'rebuilt': rebuilt, 'promoted': after, 'archived': are,
            'archive': archive}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--source', default=DEFAULT_SOURCE)
    ap.add_argument('--archive', default='predictions_pre_rescore_20260914')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args(argv)
    promote(chains.connect(), args.source, args.archive, args.dry_run)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
