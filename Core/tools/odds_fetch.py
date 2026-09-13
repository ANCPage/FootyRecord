"""Betfair AU: probe AFL markets and snapshot player-goals prices.

GATE C needs real prices for player-goals markets. This tool answers two things
honestly: what AFL markets the AU exchange actually carries (especially player
scoring markets), and — when they exist — a timestamped price snapshot to test
our probabilities against.

Credentials are NOT stored here: paths default to the working config in
~/racing-model (certificate login, the only non-interactive login Betfair AU
offers) and can be overridden by env vars:
  BETFAIR_CREDS, BETFAIR_CERT, BETFAIR_KEY, BETFAIR_APP_KEY

Usage:
  ~/footy-venv/bin/python -m Core.tools.odds_fetch probe
  ~/footy-venv/bin/python -m Core.tools.odds_fetch snapshot --days 14 --out DIR
"""
import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

API = 'https://api.betfair.com/exchange/betting/rest/v1.0/'
SSO = 'https://identitysso-cert.betfair.com/api/certlogin'
CREDS_PATH = os.environ.get('BETFAIR_CREDS', os.path.expanduser('~/racing-model/betfair-creds.txt'))
CERT_PATH = os.environ.get('BETFAIR_CERT',
                           os.path.expanduser('~/racing-model/betfair-certs/client-2048.crt'))
KEY_PATH = os.environ.get('BETFAIR_KEY',
                          os.path.expanduser('~/racing-model/betfair-certs/client-2048.key'))
APP_KEY = None                    # resolved at runtime; never stored in the repo
AFL_EVENT_TYPE = '61420'          # Betfair eventTypeId: Australian Rules
PLAYER_GOAL_TYPES = ('PLAYER_GOALS', 'TO_KICK', 'GOALS', 'PLAYER_SCORE')


def app_key():
    """The Betfair app key, resolved without keeping a secret in this repo:
    env BETFAIR_APP_KEY, else ~/racing-model/betfair-app-key.txt, else the
    KEY_ACTIVE constant already configured in ~/racing-model/betfair_probe.py."""
    global APP_KEY
    if APP_KEY:
        return APP_KEY
    key = os.environ.get('BETFAIR_APP_KEY')
    if not key:
        path = os.path.expanduser('~/racing-model/betfair-app-key.txt')
        if os.path.exists(path):
            key = open(path).read().strip()
    if not key:
        probe = os.path.expanduser('~/racing-model/betfair_probe.py')
        if os.path.exists(probe):
            import re
            m = re.search(r'^KEY_ACTIVE\s*=\s*["\']([^"\']+)["\']', open(probe).read(), re.M)
            if m:
                key = m.group(1)
    if not key:
        raise SystemExit('no Betfair app key: set BETFAIR_APP_KEY')
    APP_KEY = key
    return key


def _creds():
    out = {}
    with open(CREDS_PATH) as fh:
        for line in fh:
            if ':' in line and not line.startswith('#'):
                k, _, v = line.partition(':')
                out[k.strip()] = v.strip()
    return out


def login():
    """-> session token. Mutual TLS: Betfair requires the uploaded client cert."""
    ctx = ssl.create_default_context()
    ctx.load_cert_chain(CERT_PATH, KEY_PATH)
    creds = _creds()
    body = urllib.parse.urlencode({'username': creds['email'],
                                   'password': creds['password']}).encode()
    req = urllib.request.Request(SSO, data=body, headers={
        'X-Application': app_key(), 'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        res = json.loads(r.read())
    if res.get('loginStatus') != 'SUCCESS':
        raise SystemExit('betfair login failed: %s' % res.get('loginStatus'))
    return res['sessionToken']


def _iso(dt):
    """Betfair wants ISO-8601 to the second with an offset (no microseconds)."""
    return dt.replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def api(endpoint, token, payload):
    req = urllib.request.Request(
        API + endpoint, data=json.dumps(payload).encode(),
        headers={'X-Application': app_key(), 'X-Authentication': token,
                 'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')[:400]
        raise SystemExit('betfair %s HTTP %s: %s' % (endpoint, exc.code, body))


def catalogue(token, days=14, market_types=None, max_results=200):
    now = datetime.now(timezone.utc)
    flt = {'eventTypeIds': [AFL_EVENT_TYPE],
           'marketStartTime': {'from': _iso(now),
                               'to': _iso(now + timedelta(days=days))}}
    if market_types:
        flt['marketTypeCodes'] = list(market_types)
    return api('listMarketCatalogue/', token, {
        'filter': flt,
        'marketProjection': ['COMPETITION', 'EVENT', 'MARKET_DESCRIPTION', 'RUNNER_DESCRIPTION'],
        'maxResults': max_results})


def books(token, market_ids, best_offers=True):
    out = {}
    for i in range(0, len(market_ids), 20):          # API caps the batch size
        chunk = market_ids[i:i + 20]
        res = api('listMarketBook/', token, {
            'marketIds': chunk,
            'priceProjection': {'priceData': ['EX_BEST_OFFERS', 'SP_AVAILABLE']}})
        for m in res:
            out[m['marketId']] = m
    return out


def cmd_probe(args):
    token = login()
    print('login: SUCCESS')
    ets = api('listEventTypes/', token, {'filter': {}})
    afl = [e['eventType'] for e in ets if e['eventType']['name'].lower().startswith('austral')]
    print('AFL event types:', [(e['id'], e['name']) for e in afl])
    markets = catalogue(token, days=args.days)
    print('AFL markets in the next %d days: %d' % (args.days, len(markets)))
    types = {}
    for m in markets:
        types.setdefault(m.get('marketType', '?'), []).append(m)
    for t in sorted(types, key=lambda k: -len(types[k])):
        sample = types[t][0]
        ev = (sample.get('event') or {}).get('name', '?')
        print('  %-18s %3d markets   e.g. %s / %s' % (t, len(types[t]), ev,
                                                      sample.get('marketName', '?')))
    scoring = {t: v for t, v in types.items()
               if any(k in t.upper() for k in PLAYER_GOAL_TYPES)}
    print('player-scoring market types present:', sorted(scoring) or 'NONE')
    return markets


def cmd_snapshot(args):
    token = login()
    markets = catalogue(token, days=args.days)
    ids = [m['marketId'] for m in markets]
    book = books(token, ids) if ids else {}
    stamp = datetime.now(timezone.utc).isoformat()
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, 'betfair_afl_%s.json' % stamp.replace(':', ''))
    with open(path, 'w') as fh:
        json.dump({'fetched_at': stamp, 
                   'markets': markets, 'books': book}, fh, sort_keys=True)
    print('snapshot: %d markets, %d books -> %s' % (len(markets), len(book), path))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('probe', help='what AFL markets exist, and which are player scoring')
    p.add_argument('--days', type=int, default=14)
    p.set_defaults(func=cmd_probe)
    s = sub.add_parser('snapshot', help='save catalogue + current prices')
    s.add_argument('--days', type=int, default=14)
    s.add_argument('--out', default=os.path.expanduser('~/.cache/footy-props/odds'))
    s.set_defaults(func=cmd_snapshot)
    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
