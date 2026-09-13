"""Per-player GOALS (and behinds) per match, extracted from the raw match CSVs.

The engine counts team scores only; per-player scoring is not in the DB, so the
player-markets work needs its own extraction. Dedup mirrors the engine's ingest
exactly (stat_key = chain_period, stat_periodSeconds, x, y, stat_playerId) so
counts match the model's own view of a game.

Output: {match_id: {player_id: {"g": n, "b": n}}}

Usage:
  FOOTYRECORD_DATA_DIR=/mnt/projects/FootyRecord/CSV_DATA \
    ~/footy-venv/bin/python -m Core.tools.goals_extract --out ~/.cache/footy-props/goals.json
"""
import argparse
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core import config  # noqa: E402


def extract(data_dir, seasons=None, verbose=False):
    pattern = os.path.join(data_dir, 'flattened_stats_*.csv')
    files = sorted(f for f in glob.glob(pattern) if 'simple' not in os.path.basename(f))
    if seasons:
        files = [f for f in files
                 if any(str(s) in os.path.basename(f) for s in seasons)]
    if not files:
        raise SystemExit('no flattened_stats_*.csv found under %s' % data_dir)

    all_matches = {}
    for path in files:
        seen_by_match = {}
        shots = 0
        with open(path, newline='', encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                m_id = row.get('matchId')
                desc = row.get('stat_description')
                if not m_id or desc not in ('Goal', 'Behind'):
                    continue
                pid = row.get('stat_playerId')
                if not pid:
                    continue
                key = (row.get('chain_period'), row.get('stat_periodSeconds'),
                       row.get('x'), row.get('y'), pid, desc)
                seen = seen_by_match.setdefault(m_id, set())
                if key in seen:
                    continue
                seen.add(key)
                rec = all_matches.setdefault(m_id, {}).setdefault(pid, {'g': 0, 'b': 0})
                rec['g' if desc == 'Goal' else 'b'] += 1
                shots += 1
        if verbose:
            print('%s: +%d scoring shots' % (os.path.basename(path), shots))
    return all_matches


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--data-dir', default=config.DATA_DIR)
    ap.add_argument('--seasons', type=int, nargs='*', default=None)
    ap.add_argument('--out', default=os.path.expanduser('~/.cache/footy-props/goals.json'))
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args(argv)

    data = extract(args.data_dir, args.seasons, verbose=not args.quiet)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(data, fh, sort_keys=True)
    os.replace(tmp, args.out)
    goals = sum(r['g'] for m in data.values() for r in m.values())
    print('matches: %d | goals: %d -> %s' % (len(data), goals, args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
