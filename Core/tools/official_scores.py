"""Official match scores per season, as a sidecar the engine ingests.

WHY (audit finding 14): the AFL's chain feed (`matchPlays`) does not contain every
scoring event — a rushed behind has no player, and some matches are short whole
goals — so scores derived from chains are light (98.4% of 2026 games, mean ~9
points) and the winner was wrong in 8 of 207. The official score lives in a
different endpoint (`matchItem` -> score.homeTeamScore.matchScore.totalScore).

So: chains stay the spatial truth, and SCORES come from here.

Output (written into the data dir, next to the season CSVs):
  official_scores_<season>.json  {"<matchId>": {"home": pts, "away": pts}}

Usage:
  FOOTYRECORD_DATA_DIR=/mnt/projects/FootyRecord/CSV_DATA \
    ~/footy-venv/bin/python -m Core.tools.official_scores --season 2026
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests  # noqa: E402
import Core.chains as chains  # noqa: E402
import Core.config as config  # noqa: E402

MATCH_ITEM_URL = 'https://api.afl.com.au/cfs/afl/matchItem/{}'


def sidecar_path(season, data_dir=None):
    return os.path.join(data_dir or config.DATA_DIR, 'official_scores_%d.json' % season)


def _token():
    r = requests.post(config.AFL_AUTH_URL, json={}, headers={'User-Agent': 'Mozilla/5.0'},
                      timeout=15)
    r.raise_for_status()
    return r.json()['token']


def fetch_scores(match_ids, headers, verbose=False):
    """{m_id: {'home': pts, 'away': pts}} from the official score block."""
    out = {}
    for i, m_id in enumerate(sorted(match_ids), 1):
        try:
            r = requests.get(MATCH_ITEM_URL.format(m_id), headers=headers, timeout=25)
            sc = (r.json() or {}).get('score') or {} if r.status_code == 200 else {}
        except Exception:
            sc = {}

        def total(side):
            return ((sc.get(side) or {}).get('matchScore') or {}).get('totalScore')

        h, a = total('homeTeamScore'), total('awayTeamScore')
        if h is not None and a is not None:
            out[m_id] = {'home': int(h), 'away': int(a)}
        if verbose and i % 50 == 0:
            print('  fetched %d/%d' % (i, len(match_ids)))
    return out


def load_sidecar(season, data_dir=None):
    """Scores for a season, or {} when the sidecar has not been fetched."""
    path = sidecar_path(season, data_dir)
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return {}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--data-dir', default=config.DATA_DIR)
    ap.add_argument('--out', default=None)
    args = ap.parse_args(argv)

    conn = chains.connect()
    ids = [r[0] for r in conn.execute(
        'SELECT m_id FROM matches WHERE season=? ORDER BY round, m_id', (args.season,)).fetchall()]
    if not ids:
        raise SystemExit('no matches for season %d in the DB' % args.season)

    print('fetching official scores for %d matches (%d) ...' % (len(ids), args.season))
    headers = dict(config.AFL_HEADERS, **{'x-media-mis-token': _token()})
    scores = fetch_scores(ids, headers, verbose=True)

    path = args.out or sidecar_path(args.season, args.data_dir)
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(scores, fh, indent=0, sort_keys=True)
    os.replace(tmp, path)
    print('official scores for %d of %d matches -> %s' % (len(scores), len(ids), path))
    if len(scores) < len(ids):
        print('WARNING: %d matches have no official score (the engine will fall back to '
              'chain-derived scores for those)' % (len(ids) - len(scores)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
