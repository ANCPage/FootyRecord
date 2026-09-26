"""Does the DB hold the feed's real scores? (finding 13, first half)

The DB's 2026 home-and-away results do not reproduce the seeding the played finals
imply. This re-fetches a sample of matches from the AFL API, rebuilds their scores
from the raw stat rows with the ENGINE'S OWN dedup rule, and compares them with
the DB. It also probes for a per-match score summary and a ladder endpoint, so we
can tell "the stored scores are wrong" apart from "the seeding isn't ladder order".

Usage: ~/footy-venv/bin/python -m Core.tools.score_provenance [--rounds 3 9 16 22 24 26]
"""
import argparse
import os
import sys
from collections import defaultdict  # noqa: F401

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests  # noqa: E402
import Core.chains as chains  # noqa: E402
from Core import config  # noqa: E402
from Core.mappings import get_full_name  # noqa: E402

SQUIGGLE_URL = 'https://api.squiggle.com.au/'
MATCH_ITEM_URL = 'https://api.afl.com.au/cfs/afl/matchItem/{}'
PROBE_URLS = (
    'https://api.afl.com.au/cfs/afl/matchItem/{}',
    'https://api.afl.com.au/cfs/afl/matchSummary/{}',
    'https://api.afl.com.au/cfs/afl/ladder/2026',
)


def scores_from_payload(data):
    """(home_points, away_points, goals, behinds) rebuilt with the engine's dedup."""
    home, away = data.get('homeTeamId'), data.get('awayTeamId')
    seen = set()
    goals, behinds = defaultdict(int), defaultdict(int)
    for chain in data.get('matchChains', []) or []:
        period = chain.get('period')
        for stat in chain.get('stats', []) or []:
            desc = stat.get('description')
            if desc not in ('Goal', 'Behind'):
                continue
            pid = stat.get('playerId') or ''
            key = (period, stat.get('periodSeconds'), stat.get('x'), stat.get('y'), pid, desc)
            if key in seen:
                continue
            seen.add(key)
            team = stat.get('teamId') or chain.get('teamId')
            (goals if desc == 'Goal' else behinds)[team] += 1
    return (6 * goals.get(home, 0) + behinds.get(home, 0),
            6 * goals.get(away, 0) + behinds.get(away, 0), goals, behinds)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--rounds', type=int, nargs='*', default=[3, 9, 16, 22, 24, 26])
    ap.add_argument('--limit', type=int, default=14)
    ap.add_argument('--squiggle', action='store_true',
                    help='compare the DB with the official scores via the Squiggle API')
    ap.add_argument('--ladder', action='store_true',
                    help='rebuild the 2026 ladder from official scores and test the seeding')
    args = ap.parse_args(argv)

    if args.squiggle:
        return cmd_squiggle(args)
    if args.ladder:
        return cmd_ladder(args)

    token = requests.post(config.AFL_AUTH_URL, json={}, headers={'User-Agent': 'Mozilla/5.0'},
                          timeout=15).json()['token']
    headers = dict(config.AFL_HEADERS, **{'x-media-mis-token': token})

    print('=== does an official score/ladder endpoint exist? ===')
    for url in PROBE_URLS:
        test = url.format('CD_M20260142403') if '{}' in url else url
        try:
            r = requests.get(test, headers=headers, timeout=15)
            print('  %-4s %s' % (r.status_code, url))
            if r.status_code == 200:
                keys = list(r.json().keys())[:12] if isinstance(r.json(), dict) else type(r.json())
                print('       keys: %s' % keys)
        except Exception as exc:
            print('  ERR  %s (%s)' % (url, exc))
    print()

    conn = chains.connect()
    marks = ','.join('?' * len(args.rounds))
    rows = conn.execute(
        'SELECT m_id, round, home, away, home_score, away_score FROM matches '
        'WHERE season=2026 AND round IN (%s) ORDER BY round, m_id' % marks,
        tuple(args.rounds)).fetchall()

    print('=== DB score vs the feed, rebuilt from the raw stat rows ===')
    print('%-22s %-4s %-34s %-9s %-9s %s' % ('match', 'rnd', 'fixture', 'DB pts', 'feed pts', 'delta'))
    agree = mismatch = failed = 0
    deltas = []
    for m_id, rnd, home, away, hs, as_ in rows[:args.limit]:
        try:
            r = requests.get(config.AFL_MATCH_PLAYS_URL.format(m_id), headers=headers, timeout=20)
            data = r.json() if r.status_code == 200 else None
        except Exception:
            data = None
        if not data:
            failed += 1
            continue
        fh, fa, _g, _b = scores_from_payload(data)
        db_pts, feed_pts = (hs or 0) + (as_ or 0), fh + fa
        deltas.append(feed_pts - db_pts)
        same = abs(feed_pts - db_pts) <= 2
        agree += same
        mismatch += (not same)
        print('%-22s %-4s %-34s %-9d %-9d %+d%s' % (
            m_id, rnd, '%s v %s' % (get_full_name(home), get_full_name(away)),
            db_pts, feed_pts, feed_pts - db_pts, '' if same else '   <-- MISMATCH'))

    print()
    print('compared %d | agree(<=2 pts) %d | mismatch %d | fetch failed %d' % (
        agree + mismatch, agree, mismatch, failed))
    if deltas:
        print('feed minus DB, in points: min %+d, max %+d, mean %+.1f' % (
            min(deltas), max(deltas), sum(deltas) / len(deltas)))
    return 0



def official_scores(m_id, headers):
    """(home_points, away_points) as the AFL API's own matchScore reports them."""
    try:
        r = requests.get(MATCH_ITEM_URL.format(m_id), headers=headers, timeout=20)
        if r.status_code != 200:
            return None
        sc = (r.json() or {}).get('score') or {}
    except Exception:
        return None

    def total(side):
        return (((sc.get(side) or {}).get('matchScore') or {}).get('totalScore'))

    h, a = total('homeTeamScore'), total('awayTeamScore')
    return (h, a) if h is not None and a is not None else None


LADDER_URL = 'https://api.afl.com.au/cfs/afl/matchItem/'


def cmd_ladder(args):
    """Rebuild the 2026 ladder from OFFICIAL scores and test it against the
    seeding the played finals imply (finding 13)."""
    token = requests.post(config.AFL_AUTH_URL, json={}, headers={'User-Agent': 'Mozilla/5.0'},
                          timeout=15).json()['token']
    headers = dict(config.AFL_HEADERS, **{'x-media-mis-token': token})
    conn = chains.connect()
    rows = conn.execute(
        'SELECT m_id, round, home, away, home_score, away_score FROM matches '
        'WHERE season=2026 AND round<=24 ORDER BY round, m_id').fetchall()
    print('H&A matches to re-score from the official feed: %d' % len(rows))

    wins_db, wins_off, pf_off, pa_off = (defaultdict(int) for _ in range(4))
    flipped = 0
    missing = 0
    disagreements = []
    for m_id, rnd, home, away, hs, as_ in rows:
        off = official_scores(m_id, headers)
        if not off:
            missing += 1
            continue
        h_off, a_off = off
        if (hs or 0) > (as_ or 0):
            wins_db[home] += 1
        elif (hs or 0) < (as_ or 0):
            wins_db[away] += 1
        if h_off > a_off:
            wins_off[home] += 1
        elif h_off < a_off:
            wins_off[away] += 1
        else:
            pass
        if ((hs or 0) > (as_ or 0)) != (h_off > a_off):
            flipped += 1
            disagreements.append((m_id, rnd, home, away, (hs or 0, as_ or 0), (h_off, a_off)))
        pf_off[home] += h_off
        pa_off[home] += a_off
        pf_off[away] += a_off
        pa_off[away] += h_off

    print('games where the DB and the official feed disagree on the WINNER: %d (missing %d)'
          % (flipped, missing))
    print()
    print('--- the disagreements (DB result vs the feed\'s own score) ---')
    for rec in disagreements:
        m_id, rnd, home, away, db_s, off_s = rec
        db_w = get_full_name(home if db_s[0] > db_s[1] else away)
        off_w = get_full_name(home if off_s[0] > off_s[1] else away)
        print('  R%-2s %-34s DB %s %d-%d  ->  %s  | feed %d-%d  ->  %s' % (
            rnd, '%s v %s' % (get_full_name(home), get_full_name(away)), db_w,
            db_s[0], db_s[1], db_w, off_s[0], off_s[1], off_w))
    teams = sorted(set(wins_off) | set(wins_db))
    def pct(t):
        return 100.0 * pf_off[t] / pa_off[t] if pa_off.get(t) else 0.0
    order_off = sorted(teams, key=lambda t: (-wins_off[t], -pct(t), t))
    order_db = sorted(teams, key=lambda t: (-wins_db[t], t))
    print()
    print('%-4s %-18s %-14s %-16s' % ('pos', 'team', 'OFFICIAL (W)', 'DB (W)'))
    for i in range(min(12, len(order_off))):
        t_off = order_off[i]
        pos_db = order_db.index(t_off) + 1
        flag = '' if pos_db == i + 1 else '   <-- DB ladder puts it %d' % pos_db
        print('%-4d %-18s %-14s %-16s%s' % (i + 1, get_full_name(t_off),
                                            '%dW %.1f%%' % (wins_off[t_off], pct(t_off)),
                                            '%dW' % wins_db[t_off], flag))
    seeds = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    print()
    print('expectation from the played finals: 1 Fremantle, 2 Sydney, 3 Brisbane, 4 Hawthorn,'
          ' 5 Geelong, 6 Adelaide, 7 Melbourne, 8 Bulldogs, 9 Collingwood, 10 Carlton')
    print('official-score ladder top 10: ' + ', '.join(
        '%d:%s' % (i + 1, get_full_name(order_off[i])) for i in range(min(10, len(order_off)))))
    return 0



def _word(name):
    return (name or '').split()[0].lower() if name else ''


def cmd_squiggle(args):
    """Third-party check: Squiggle's public API carries official scores for every
    game. Compare them with the DB and with our chain-derived scores. This decides
    which AFL endpoint is authoritative (findings 13/14)."""
    r = requests.get(SQUIGGLE_URL, params={'q': 'games', 'year': 2026},
                     headers={'User-Agent': 'footyrecord-audit/1.0'}, timeout=30)
    games = (r.json() or {}).get('games') or []
    print('squiggle games for 2026: %d' % len(games))

    by_round_teams = {}
    for g in games:
        by_round_teams[(int(g['round']), _word(g['hteam']), _word(g['ateam']))] = g

    conn = chains.connect()
    rows = conn.execute(
        'SELECT m_id, round, home, away, home_score, away_score FROM matches '
        'WHERE season=2026 AND round<=24 ORDER BY round, m_id').fetchall()

    # Squiggle numbers rounds from 0 (Opening Round); find the offset that fits.
    best_offset, best_hits = None, -1
    for offset in (0, 1, -1):
        hits = 0
        for _m, rnd, home, away, _hs, _as in rows:
            key = (rnd - offset, _word(get_full_name(home)), _word(get_full_name(away)))
            if key in by_round_teams:
                hits += 1
        if hits > best_hits:
            best_offset, best_hits = offset, hits
    print('round offset that matches best: %d (%d/%d fixtures matched)' % (
        best_offset, best_hits, len(rows)))
    print()

    same = diff = 0
    winner_flips = []
    deltas = []
    offender = []
    for m_id, rnd, home, away, hs, as_ in rows:
        key = (rnd - best_offset, _word(get_full_name(home)), _word(get_full_name(away)))
        g = by_round_teams.get(key)
        if not g:
            continue
        sg = (int(g['hscore']), int(g['ascore']))
        db = (hs or 0, as_ or 0)
        if (sg[0] > sg[1]) != (db[0] > db[1]):
            winner_flips.append((rnd, get_full_name(home), get_full_name(away), db, sg))
        if sg == db:
            same += 1
        else:
            diff += 1
            deltas.append(sum(sg) - sum(db))
            offender.append((rnd, get_full_name(home), get_full_name(away), db, sg,
                             int(g['hgoals']), int(g['hbehinds']), int(g['agoals']), int(g['abehinds'])))
    print('DB vs squiggle (official): identical %d | different %d' % (same, diff))
    print('  -> in %.1f%% of home-and-away games the stored score is not the official one'
          % (100.0 * diff / max(1, same + diff)))
    print('games where the DB and the OFFICIAL result disagree on the winner: %d of %d (%.1f%%)'
          % (len(winner_flips), same + diff, 100.0 * len(winner_flips) / max(1, same + diff)))
    for rnd, h, a, db, sg in winner_flips:
        print('   R%-3s %-34s DB %-9s official %s' % (rnd, '%s v %s' % (h, a),
                                                      '%d-%d' % db, '%d-%d' % sg))
    if deltas:
        print()
        print('%-4s %-34s %-12s %-12s %s' % ('rnd', 'fixture', 'DB', 'official', 'official line'))
        for rnd, h, a, db, sg, hg, hb, ag, ab in sorted(offender, key=lambda x: x[0])[:8]:
            print('%-4s %-34s %-12s %-12s %dg %db - %dg %db' % (
                rnd, '%s v %s' % (h, a), '%d-%d' % db, '%d-%d' % sg, hg, hb, ag, ab))

    # ladder from the official scores, tested against the finals seeding
    wins, pf, pa = (defaultdict(int) for _ in range(3))
    for g in games:
        rnd = int(g['round'])
        if rnd - best_offset > 24 or rnd - best_offset < 1:
            continue
        if not g.get('complete'):
            continue
        h, a = _word(g['hteam']), _word(g['ateam'])
        hs, as_ = int(g['hscore']), int(g['ascore'])
        pf[h] += hs
        pa[h] += as_
        pf[a] += as_
        pa[a] += hs
        if hs > as_:
            wins[h] += 1
        elif as_ > hs:
            wins[a] += 1
    def pct(t):
        return 100.0 * pf[t] / pa[t] if pa.get(t) else 0.0
    order = sorted(wins, key=lambda t: (-wins[t], -pct(t), t))
    print()
    print('official ladder (squiggle, top 10): ' + ', '.join(
        '%d:%s %dW' % (i + 1, order[i], wins[order[i]]) for i in range(min(10, len(order)))))
    print('seeding the played finals imply:   1:Fremantle, 2:Sydney, 3:Brisbane, 4:Hawthorn, '
          '5:Geelong, 6:Adelaide, 7:Melbourne, 8:Bulldogs, 9:Collingwood, 10:Carlton')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
