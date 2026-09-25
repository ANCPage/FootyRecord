"""Per-player GOALS (and behinds) per match, extracted from the raw match CSVs.

The engine counts team scores only; per-player scoring is not in the DB, so the
player-markets work needs its own extraction. Dedup mirrors the engine's ingest
exactly (stat_key = chain_period, stat_periodSeconds, x, y, stat_playerId) so
counts match the model's own view of a game.

TEAM ATTRIBUTION (fixed 2026-09-14): the side comes from the feed's own
`stat_teamId`, not from any player->club inference. `player_history` carries
5,734 (match, player) pairs under two teams — a player appearing in the
opposition's chains — and inferring the side from it put ~4% of goals on the
wrong team. `stat_teamId` is authoritative.

Rows with no player id (rushed behinds) are counted at TEAM level only, so team
totals are complete even though no individual owns them.

Output schema (version 2):
  {"version": 2,
   "matches": {match_id: {"players": {player_id: {"g": n, "b": n, "team": id}},
                          "teams": {team_id: {"g": n, "b": n}}}}}

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

SCHEMA_VERSION = 2


def extract(data_dir, seasons=None, verbose=False):
    pattern = os.path.join(data_dir, 'flattened_stats_*.csv')
    files = sorted(f for f in glob.glob(pattern) if 'simple' not in os.path.basename(f))
    if seasons:
        files = [f for f in files
                 if any(str(s) in os.path.basename(f) for s in seasons)]
    if not files:
        raise SystemExit('no flattened_stats_*.csv found under %s' % data_dir)

    matches = {}
    for path in files:
        seen_by_match = {}
        shots = 0
        with open(path, newline='', encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                m_id = row.get('matchId')
                desc = row.get('stat_description')
                if not m_id or desc not in ('Goal', 'Behind'):
                    continue
                pid = row.get('stat_playerId') or ''
                team = row.get('stat_teamId') or ''
                key = (row.get('chain_period'), row.get('stat_periodSeconds'),
                       row.get('x'), row.get('y'), pid, desc, team)
                seen = seen_by_match.setdefault(m_id, set())
                if key in seen:
                    continue
                seen.add(key)
                slot = 'g' if desc == 'Goal' else 'b'
                rec = matches.setdefault(m_id, {'players': {}, 'teams': {}})
                if team:
                    rec['teams'].setdefault(team, {'g': 0, 'b': 0})[slot] += 1
                if pid:
                    p = rec['players'].setdefault(pid, {'g': 0, 'b': 0, 'team': team})
                    p[slot] += 1
                    if team:
                        p['team'] = team
                shots += 1
        if verbose:
            print('%s: +%d scoring shots' % (os.path.basename(path), shots))
    return {'version': SCHEMA_VERSION, 'matches': matches}


def load(path):
    """Read a goals cache, refusing an older schema rather than guessing."""
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or data.get('version') != SCHEMA_VERSION:
        raise SystemExit(
            'goals cache %s is schema %r, this tool needs %d — regenerate with '
            'Core.tools.goals_extract' % (path, (data or {}).get('version'), SCHEMA_VERSION))
    return data['matches']


def side_goals(match_rec):
    """{team_id: {'g': n, 'b': n}} for one match, from the feed's own team ids."""
    return match_rec.get('teams', {})


def player_team(match_rec, player_id):
    """The side the feed says this player scored for."""
    return (match_rec.get('players', {}).get(player_id) or {}).get('team')


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
    goals = sum(t['g'] for m in data['matches'].values() for t in m['teams'].values())
    behinds = sum(t['b'] for m in data['matches'].values() for t in m['teams'].values())
    print('matches: %d | goals: %d | behinds: %d -> %s' % (
        len(data['matches']), goals, behinds, args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
