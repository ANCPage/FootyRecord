#!/usr/bin/env python3
"""render_card — the ONE entry point for liquid card JSON (one-system CLI).

Everything numeric comes from Core (state_store rows / compute_matchup /
Core.cards); liquid only turns the payload into template JSON (liquid.geom).

Usage (run from the repo root; a full engine state is only needed when a
prediction card has NO stored row, i.e. finals/futures):
  python liquid/render_card.py --mode recap  --a CD_T100 --b CD_T160 \\
      --home CD_T160 --season 2026 --round 24 --label 'ROUND 24'
  python liquid/render_card.py --mode pred --a CD_T10 --b CD_T140 \\
      --home CD_T10 --season 2026 --up-to 24 --label 'FINALS WEEK 1'
Writes the template-ready JSON to --out (/tmp/liquid_data.json).
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import Core.cards as cards          # noqa: E402  (payload assembly — one system)
import Core.chains as chains        # noqa: E402
import Core.state_store as state_store  # noqa: E402
from liquid import schema           # noqa: E402  (payload contract guard)
from liquid.geom import materialise  # noqa: E402  (presentation only)


def main():
    ap = argparse.ArgumentParser(description='Liquid card JSON (one-system)')
    ap.add_argument('--mode', required=True, choices=['pred', 'recap', 'net'])
    ap.add_argument('--a', required=True, help='team attacking the TOP goal')
    ap.add_argument('--b', required=True, help='team attacking the BOTTOM goal')
    ap.add_argument('--home', required=True, help='fixture home team')
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--round', type=int, default=None, help='recap/net game round')
    ap.add_argument('--up-to', type=int, default=None, help='pred data window')
    ap.add_argument('--label', default=None, help='round label prefix')
    ap.add_argument('--out', default='/tmp/liquid_data.json')
    ap.add_argument('--summary-only', action='store_true')
    args = ap.parse_args()

    conn = chains.connect()
    ing = None
    payload = stats = None
    if args.mode == 'pred':
        if args.up_to is None:
            ap.error('--mode pred requires --up-to (data window)')
        # engine state only when the fixture has no stored prediction
        slot = args.up_to + 1
        away = args.b if args.a == args.home else args.a
        ov = None
        if state_store.prediction_row(conn, args.season, slot, args.home, away) is None:
            from Core.config import DATA_DIR
            from Core.engine_data import DataIngestor
            ing = DataIngestor(DATA_DIR)
            ing.load_all_data(light=True)
            ov = {t: (state_store.latest_elo(conn, t) or 1500.0)
                  for t in (args.a, args.b)}
        payload, stats = cards.pred_payload(
            ing, conn, args.a, args.b, args.home, args.season, args.up_to,
            label=args.label, elo_overrides=ov)
    elif args.mode == 'recap':
        payload, stats = cards.recap_payload(
            conn, args.season, args.round, args.a, args.b, args.home,
            label=args.label)
    else:
        payload, stats = cards.net_payload(
            conn, args.season, args.round, args.a, args.b, args.home,
            label=args.label)

    if args.summary_only:
        print('%s %s v %s | %s | ends %s' % (
            payload['round_label'],
            payload['teams']['top']['name'], payload['teams']['bottom']['name'],
            payload['verdict'], stats))
        return 0
    out = materialise(payload)
    schema.validate_payload(out)      # contract guard before anything consumes it
    json.dump(out, open(args.out, 'w'))
    v = payload['verdict']
    print('%s: %s by %d (ends %s) -> %s' % (
        payload['round_label'], v.get('winner'), v.get('margin', 0), stats,
        args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
