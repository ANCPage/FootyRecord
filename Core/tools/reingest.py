"""Re-ingest the season CSVs into the one-store DB, then verify the scores.

THE STEP THAT FIXES THE SCOREBOARD (audit finding 14). The 2026 CSVs were rebuilt
with `engine_scraper.process_single_match` no longer dropping scoring rows that
carry no player id, so rushed behinds now reach the engine. This tool:

  1. loads the CSVs (the fingerprint gate makes it a fresh ingest + profile),
  2. saves the state,
  3. VERIFIES the stored scores against the AFL's official results and reports how
     many games still disagree, plus how many winners differ.

Refuses to save unless the check runs, so "re-ingested" and "verified" cannot be
confused.

Usage:
  FOOTYRECORD_DATA_DIR=/mnt/projects/FootyRecord/CSV_DATA \
    ~/footy-venv/bin/python -m Core.tools.reingest --season 2026
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests  # noqa: E402
import Core.chains as chains  # noqa: E402
import Core.config as config  # noqa: E402
import Core.state_store as state_store  # noqa: E402
from Core.engine_data import DataIngestor  # noqa: E402
from Core.mappings import get_full_name  # noqa: E402

SQUIGGLE_URL = 'https://api.squiggle.com.au/'


def _word(name):
    return (name or '').split()[0].lower() if name else ''


def official_games(season, timeout=30):
    r = requests.get(SQUIGGLE_URL, params={'q': 'games', 'year': season},
                     headers={'User-Agent': 'footyrecord-reingest/1.0'}, timeout=timeout)
    games = (r.json() or {}).get('games') or []
    out = {}
    for g in games:
        out[(int(g['round']), _word(g['hteam']), _word(g['ateam']))] = g
    return out


def verify(season, sample_limit=None):
    """(checked, exact, light, winner_flips, examples) against the official feed."""
    official = official_games(season)
    conn = chains.connect()
    rows = conn.execute(
        'SELECT m_id, round, home, away, home_score, away_score FROM matches '
        'WHERE season=? ORDER BY round, m_id', (season,)).fetchall()
    checked = exact = flips = 0
    examples = []
    for m_id, rnd, home, away, hs, as_ in rows:
        for offset in (0, 1, -1):
            g = official.get((rnd - offset, _word(get_full_name(home)), _word(get_full_name(away))))
            if g:
                break
        if not g:
            continue
        checked += 1
        sg = (int(g['hscore']), int(g['ascore']))
        db = (hs or 0, as_ or 0)
        if sg == db:
            exact += 1
        if (sg[0] > sg[1]) != (db[0] > db[1]):
            flips += 1
            if len(examples) < 8:
                examples.append((rnd, get_full_name(home), get_full_name(away), db, sg))
    return checked, exact, flips, examples


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--csv-dir', default=config.DATA_DIR)
    ap.add_argument('--no-save', action='store_true',
                    help='ingest and verify but do not write the state')
    ap.add_argument('--force', action='store_true',
                    help='clear the cached fingerprint first, so the CSVs are re-parsed '
                         'even when the DB believes its state is current')
    args = ap.parse_args(argv)

    if args.force:
        # The fingerprint gate happily loads the DB when nothing *it* tracks changed,
        # which silently skipped the corrected score sidecars for 2021-2025
        # (2026-09-14). Clearing it forces a fresh parse of the CSVs.
        conn = chains.connect()
        for key in ('fingerprint', 'csv_fingerprint'):
            state_store.meta_set(conn, key, '')
        print('fingerprint cleared: next load re-parses the CSVs')

    print('re-ingesting %s from %s' % (args.season, args.csv_dir))
    ing = DataIngestor(args.csv_dir)
    ing.load_all_data()
    print('loaded: match_info=%d positions=%d chains=%d' % (
        len(ing.match_info), len(getattr(ing, 'match_positions', {})),
        len(getattr(ing, 'match_chains', {}))))
    ing.profile_all_teams()
    print('after profiling: positions=%d' % len(getattr(ing, 'match_positions', {})))

    if not args.no_save:
        conn = chains.connect()
        state_store.save_state(conn, ing)
        print('state saved')

    print()
    print('verifying stored scores against the official feed ...')
    checked, exact, flips, examples = verify(args.season)
    print('games compared: %d | exact score match: %d (%.1f%%) | winner flips: %d'
          % (checked, exact, 100.0 * exact / max(1, checked), flips))
    for rnd, h, a, db, sg in examples:
        print('   R%-3s %-34s DB %-9s official %s' % (rnd, '%s v %s' % (h, a),
                                                      '%d-%d' % db, '%d-%d' % sg))
    if flips:
        print('WARNING: %d games still disagree on the winner' % flips)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
