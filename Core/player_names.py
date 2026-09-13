"""Player id -> name resolver (cache-backed, 2026-09-13).

The chain data carries player IDs only; names live in the AFL roster API
(`/cfs/afl/matchRoster/full/{matchId}`, the endpoint predict_game.py uses).
This resolves IDs by fetching the rosters of the matches those players
appear in, caching the result so repeat lookups cost nothing.

Never touches model state: read-only against the DB, writes only its own
cache file.
"""
import json
import os
import sys
import time

# Repo root FIRST: the venv carries an editable install that maps Core to the
# SMB share's copy, so without this bootstrap `import Core` can silently load
# stale code off the mount (2026-09-13).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import Core.chains as chains
import Core.state_store as state_store

CACHE_PATH = os.path.expanduser('~/.cache/footyrecord_players.json')
_TOKEN_URL = 'https://api.afl.com.au/cfs/afl/WMCTok'
_ROSTER_URL = 'https://api.afl.com.au/cfs/afl/matchRoster/full/%s'


def load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(cache, f, indent=0, sort_keys=True)
    os.replace(tmp, CACHE_PATH)


def _token():
    r = requests.post(_TOKEN_URL, json={}, headers={'User-Agent': 'Mozilla/5.0'},
                      timeout=15)
    r.raise_for_status()
    return r.json().get('token')


def roster_names(m_id, token):
    """{player_id: 'Given Surname'} for one match, or {}."""
    try:
        r = requests.get(_ROSTER_URL % m_id,
                         headers={'x-media-mis-token': token}, timeout=15)
        if r.status_code != 200:
            return {}
        roster = r.json().get('matchRoster') or {}
    except Exception:
        return {}
    out = {}
    for side in ('homeTeam', 'awayTeam'):
        for pos in (roster.get(side) or {}).get('positions', []):
            p = pos.get('player') or {}
            pid = p.get('playerId')
            nm = p.get('playerName') or {}
            if pid and nm:
                out[pid] = ('%s %s' % (nm.get('givenName', ''), nm.get('surname', ''))).strip()
    return out


def resolve(conn, player_ids, season=2026, team=None, max_fetches=80):
    """Resolve as many of `player_ids` as possible, cheapest matches first.

    `team` (optional) limits the matches fetched to that team's games — the
    players we care about come from those. Resolved names are cached.
    """
    cache = load_cache()
    missing = [p for p in player_ids if p not in cache]
    if not missing:
        return {p: cache[p] for p in player_ids if p in cache}

    if team:
        rows = state_store.team_match_history(conn, team, season, 30)
        mids = [m_id for (m_id, _s, _r) in rows]
    else:
        mids = [r[0] for r in conn.execute(
            'SELECT m_id FROM matches WHERE season=? ORDER BY m_id DESC',
            (season,)).fetchall()]
    if not mids:
        return {}
    token = _token()
    fetched = 0
    for m_id in mids:
        if fetched >= max_fetches or not missing:
            break
        names = roster_names(m_id, token)
        fetched += 1
        for pid, nm in names.items():
            if pid not in cache and nm:
                cache[pid] = nm
        missing = [p for p in player_ids if p not in cache]
        time.sleep(0.15)          # be polite to the API
    save_cache(cache)
    return {p: cache[p] for p in player_ids if p in cache}


if __name__ == '__main__':
    import sys
    conn = chains.connect()
    tids = sys.argv[1:] or ['CD_T100']
    for t in tids:
        pe = state_store.team_match_history(conn, t, 2026, 24)[:30]
        ids = set()
        marks = ','.join('?' * len(pe))
        for (pid,) in conn.execute(
                'SELECT DISTINCT player FROM player_history WHERE team=? AND m_id IN ('
                + marks + ')', (t,) + tuple(m[0] for m in pe)).fetchall():
            ids.add(pid)
        named = resolve(conn, sorted(ids), 2026, team=t)
        print('%s: %d players, %d named' % (t, len(ids), len(named)))
