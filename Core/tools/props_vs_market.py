"""GATE C: price the estimator against a real bookmaker price.

Reads a price file (The Odds API event-odds JSON, or the normalised schema below)
and reports, for every matched player-market:

  - the model's probability (Core.player_props)
  - the market's de-overrounded probability (two-way normalisation on over/under)
  - log loss for each, and calibration by probability bucket
  - the expected return of the PRE-DECLARED rule: back when the model's
    probability exceeds the market's by >= 5 points, at the quoted price

The rule, the threshold and the metrics are fixed in the plan
(~/.hermes/plans/20260914_013112-player-scoring-markets.md) — do not tune them
after seeing the result.

Normalised schema (list of records), if not using the Odds API shape:
  [{"m_id": "CD_M...", "team": "CD_T160", "season": 2026, "round": 24,
    "player_name": "Charlie Curnow", "line": 1.5, "over_price": 1.85,
    "under_price": 1.95}]

Usage:
  ~/footy-venv/bin/python -m Core.tools.props_vs_market --prices prices.json
"""
import argparse
import json
import math
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import Core.chains as chains  # noqa: E402
from Core.player_props import logloss, poisson_ge, prop_estimates  # noqa: E402

EDGE_THRESHOLD = 0.05          # pre-declared: back only at >= 5 points of edge
BOOTSTRAP = 2000
BOOTSTRAP_SEED = 20260914


def two_way_prob(over_price, under_price):
    """Market probability of the over, margin removed (both sides priced)."""
    if not over_price or not under_price or over_price <= 1 or under_price <= 1:
        return None
    a, b = 1.0 / over_price, 1.0 / under_price
    return a / (a + b)


def parse_odds_api(payload, season=2026, round_num=None, team_of=None):
    """The Odds API event-odds JSON -> normalised records.

    team_of(market_key, player_name) -> team id, or None if unknown.
    """
    out = []
    for ev in payload if isinstance(payload, list) else [payload]:
        m_id = ev.get('id') or ev.get('event_id')
        for bk in ev.get('bookmakers', []):
            for mk in bk.get('markets', []):
                key = mk.get('key', '')
                if 'goal' not in key:
                    continue
                by_player = {}
                for oc in mk.get('outcomes', []):
                    name = oc.get('description') or oc.get('name')
                    side = (oc.get('name') or '').lower()
                    line = float(oc.get('point') or 0.5)
                    slot = by_player.setdefault((name, line), {})
                    if side.startswith('over'):
                        slot['over_price'] = oc.get('price')
                    elif side.startswith('under'):
                        slot['under_price'] = oc.get('price')
                for (name, line), prices in by_player.items():
                    out.append({
                        'm_id': m_id, 'bookmaker': bk.get('key'), 'market': key,
                        'player_name': name, 'line': line, 'season': season,
                        'round': round_num,
                        'team': (team_of or (lambda k, n: None))(key, name),
                        'over_price': prices.get('over_price'),
                        'under_price': prices.get('under_price'),
                    })
    return out


def _name_to_id():
    """Invert the cached id -> name map from Core.player_names."""
    from Core import player_names
    cache = player_names.load_cache()
    out = {}
    for pid, nm in cache.items():
        if nm:
            out[nm.lower()] = pid
    return out


def evaluate(records, conn, name_to_id=None, prob_fn=None, stake=1.0):
    """Market vs model on matched records. Returns (rows, summary).

    prob_fn(conn, team, season, round_num, player_id, line_total) -> probability
    of kicking MORE than `line_total` goals. Pluggable so the comparison is
    testable without the model or a DB.
    """
    if prob_fn is None:
        def prob_fn(conn_, team, season, round_num, pid, line_total):
            team_total = None
            est = prop_estimates(conn_, team, season, round_num,
                                 team_goal_total=team_total, players=[pid])
            rec = est.get(pid)
            if not rec:
                return None
            k = int(math.floor(line_total)) + 1        # "over 1.5" == 2+
            return poisson_ge(k, rec['expected_goals'])

    resolved = name_to_id if name_to_id is not None else _name_to_id()
    rows = []
    for r in records:
        if r.get('team') is None or r.get('over_price') is None:
            continue
        pid = resolved.get((r.get('player_name') or '').lower())
        if not pid:
            continue
        market_p = two_way_prob(r['over_price'], r.get('under_price'))
        if market_p is None:
            continue
        model_p = prob_fn(conn, r['team'], r['season'], r['round'], pid, r['line'])
        if model_p is None:
            continue
        rows.append({**r, 'player_id': pid, 'market_p': market_p, 'model_p': model_p})

    if not rows:
        return rows, {'n': 0}

    graded = [r for r in rows if r.get('actual_over') is not None]
    ll_model = (sum(logloss(r['model_p'], 1 if r['actual_over'] else 0) for r in graded)
                / len(graded)) if graded else None
    ll_market = (sum(logloss(r['market_p'], 1 if r['actual_over'] else 0) for r in graded)
                 / len(graded)) if graded else None
    bets = [r for r in rows if (r['model_p'] - r['market_p']) >= EDGE_THRESHOLD]
    ret = sum((r['over_price'] - 1) if r.get('actual_over') else -1 for r in bets) * stake
    summary = {
        'n': len(rows),
        'n_with_result': len(graded),
        'mean_market_p': sum(r['market_p'] for r in rows) / len(rows),
        'mean_model_p': sum(r['model_p'] for r in rows) / len(rows),
        'logloss_model': ll_model,
        'logloss_market': ll_market,
        'bets': len(bets),
        'staked': len(bets) * stake,
        'return': ret,
        'roi': (ret / (len(bets) * stake)) if bets else None,
        'buckets': _buckets(rows),
    }
    return rows, summary


def summary_n(rows):
    return any(r.get('actual_over') is not None for r in rows)


def _buckets(rows):
    out = {}
    for lo in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        sel = [r for r in rows if lo <= r['model_p'] < lo + 0.1 and r.get('actual_over') is not None]
        if sel:
            out['%.1f' % lo] = {'n': len(sel),
                                'mean_model_p': sum(r['model_p'] for r in sel) / len(sel),
                                'actual_rate': sum(1 for r in sel if r['actual_over']) / len(sel)}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--prices', required=True, help='odds JSON (Odds API or normalised)')
    ap.add_argument('--format', choices=['oddsapi', 'normalised'], default='normalised')
    ap.add_argument('--season', type=int, default=2026)
    ap.add_argument('--round', type=int, default=None)
    ap.add_argument('--json-out', default=None)
    args = ap.parse_args(argv)

    with open(args.prices) as fh:
        payload = json.load(fh)
    records = (parse_odds_api(payload, args.season, args.round) if args.format == 'oddsapi'
               else payload)
    rows, summary = evaluate(records, chains.connect())
    print(json.dumps({k: v for k, v in summary.items() if k != 'buckets'}, indent=1))
    if summary.get('n'):
        print('buckets (model probability -> actual rate):')
        for k in sorted(summary['buckets']):
            b = summary['buckets'][k]
            print('  %s: n=%d model %.3f actual %.3f' % (k, b['n'], b['mean_model_p'],
                                                         b['actual_rate']))
    if args.json_out:
        with open(args.json_out, 'w') as fh:
            json.dump({'summary': {k: v for k, v in summary.items()}, 'rows': rows}, fh,
                      indent=1, sort_keys=True)
        print('written: %s' % args.json_out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
