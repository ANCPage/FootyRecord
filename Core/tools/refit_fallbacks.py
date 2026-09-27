"""Re-derive the bootstrap fallback constants from the corrected data.

WHY (calibration audit 2026-09-14, findings 1-2): `FALLBACK_MARGIN` and
`FALLBACK_TOTAL` in Core/calibration.py were fitted on 2026-08-09/10, BEFORE the
scoreboard was corrected. Every fitted value moved when the scores changed; the
constants could not, so the bootstrap path was serving numbers ~37% low on margin
scaling and ~15 points light on totals.

This re-fits them the same way they were originally derived — least squares on the
margin features over a two-season window, and the mean actual total — and prints a
ready-to-paste block plus the values as JSON for the record.

Usage:
  FOOTYRECORD_DATA_DIR=/mnt/projects/FootyRecord/CSV_DATA \
    ~/footy-venv/bin/python -m Core.tools.refit_fallbacks --seasons 2024 2025
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

import Core.config as config  # noqa: E402
import Core.calibration as cal  # noqa: E402
from Core.engine_data import DataIngestor  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--seasons', type=int, nargs='*', default=[2024, 2025])
    ap.add_argument('--json-out', default=os.path.expanduser(
        '~/.cache/footy-props/fallback_constants.json'))
    args = ap.parse_args(argv)

    ing = DataIngestor(config.DATA_DIR)
    ing.load_all_data(light=True)
    rows = ing._build_fit_rows()
    sel = [r for r in rows if r[0] in args.seasons]
    if len(sel) < cal.MIN_FIT_MATCHES:
        raise SystemExit('only %d rows for seasons %s — need %d'
                         % (len(sel), args.seasons, cal.MIN_FIT_MATCHES))

    nets = np.asarray([r[2] for r in sel], float)
    elos = np.asarray([r[3] for r in sel], float) / 100.0
    margins = np.asarray([r[4] for r in sel], float)
    totals = np.asarray([r[5] for r in sel], float)
    X = np.column_stack([nets, elos])
    b, *_ = np.linalg.lstsq(X, margins, rcond=None)
    pred = X @ b
    ss_res = float(((margins - pred) ** 2).sum())
    ss_tot = float(((margins - margins.mean()) ** 2).sum())
    r = float(np.corrcoef(pred, margins)[0, 1])

    print('fit rows: %d (seasons %s)' % (len(sel), args.seasons))
    print('   margin_b1 %.4f  (was 70.9755)' % b[0])
    print('   margin_b2 %.4f  (was 4.8817)' % b[1])
    print('   total_mean %.4f (was 159.26)' % totals.mean())
    print('   fit quality: r=%.4f  R2=%.4f' % (r, 1 - ss_res / ss_tot if ss_tot else 0))
    print()
    print('paste into Core/calibration.py:')
    print('FALLBACK_MARGIN = (%.4f, %.4f)       # b1(net), b2(elo/100)' % (b[0], b[1]))
    print('FALLBACK_TOTAL = %.4f' % totals.mean())

    os.makedirs(os.path.dirname(args.json_out), exist_ok=True)
    with open(args.json_out, 'w') as fh:
        json.dump({'margin_b1': float(b[0]), 'margin_b2': float(b[1]),
                   'total_mean': float(totals.mean()), 'seasons': args.seasons,
                   'n_rows': len(sel), 'r': r,
                   'fitted_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                   'data': 'score-corrected (official scores)'}, fh, indent=1)
    print('\nnote: %s' % args.json_out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
