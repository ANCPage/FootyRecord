"""Player-goals backtest: allocation test, gate table, leverage diagnostic.

THE QUESTION (see the plan): holding a team's goal total fixed, does the model's
structural allocation of goals to players predict scoring better than the
player's own historical share of team goals — and does any advantage grow with
matchup leverage (the opponent leaking the routes that player uses)?

Three allocations, one volume:
  m = model: the delta-weighted share of the team's ->SCORE edges
  h = history: the player's share of his team's goals over prior games
  u = equal shares (do-nothing reference)

Volume settings: actual team score (isolates allocation), the team's prior
average score, the model's projected score.

Walk-forward, deterministic (identical output regardless of PYTHONHASHSEED).

Usage:
  FOOTYRECORD_DATA_DIR=/mnt/projects/FootyRecord/CSV_DATA ~/footy-venv/bin/python \
    -m Core.tools.props_backtest --gate --leverage
"""
import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import Core.chains as chains  # noqa: E402
from Core.cards import mirror_delta, parse_delta  # noqa: E402
from Core import player_attribution as pa  # noqa: E402
from Core.player_props import dmap, logloss, poisson_ge  # noqa: E402  (single source of maths)

PPG = 6.71          # points per goal, 2021-2026 league average
N_SMOOTH = 0.5      # pseudo-count pulling a thin history toward equal shares
DEFAULT_GOALS = os.path.expanduser('~/.cache/footy-props/goals.json')
BOOTSTRAP = 1000
BOOTSTRAP_SEED = 20260914


def spearman(est, act):
    """Deterministic Spearman over player ids (ties broken by id)."""
    ids = sorted(est)
    n = len(ids)
    if n < 5:
        return None
    oe = sorted(ids, key=lambda p: (-est[p], p))
    oa = sorted(ids, key=lambda p: (-act[p], p))
    re_ = {p: i for i, p in enumerate(oe)}
    ra = {p: i for i, p in enumerate(oa)}
    mx = my = (n - 1) / 2
    num = sum((re_[p] - mx) * (ra[p] - my) for p in ids)
    dx = sum((re_[p] - mx) ** 2 for p in ids) ** 0.5
    dy = sum((ra[p] - my) ** 2 for p in ids) ** 0.5
    if not dx or not dy:
        return None
    return num / (dx * dy)


def build_rows(conn, goals, seasons=None, lineup_filter=False, limit_rounds=None):
    """Walk-forward rows: one per team-game, with the three allocations."""
    from Core import player_names  # only needed for the lineup filter

    matches = conn.execute(
        'SELECT m_id, season, round, home, away, home_score, away_score FROM matches '
        'ORDER BY season, round, m_id').fetchall()
    by_key = {(s, rnd, frozenset((h, a))): (m_id, h, a, hs, as_)
              for m_id, s, rnd, h, a, hs, as_ in matches}
    matches_by_round = defaultdict(list)
    for m_id, s, rnd, h, a, hs, as_ in matches:
        matches_by_round[(s, rnd)].append((m_id, h, a, hs, as_))

    p2t = {}
    for m_id, team, player in conn.execute('SELECT m_id, team, player FROM player_history'):
        if player and player not in ('', '0'):
            p2t[(m_id, player)] = team

    side_goals = defaultdict(lambda: {'g': 0, 'b': 0})
    for m_id, per_player in goals.items():
        for pid, rec in per_player.items():
            t = p2t.get((m_id, pid))
            if t:
                side_goals[(m_id, t)]['g'] += rec['g']
                side_goals[(m_id, t)]['b'] += rec['b']

    team_games, team_goals, team_points = defaultdict(int), defaultdict(int), defaultdict(int)
    player_goals = defaultdict(int)

    share_cache = {}
    def model_shares(team, season, rnd):
        key = (team, season, rnd)
        if key not in share_cache:
            share_cache[key] = pa.edge_shares(pa.window_player_edges(conn, team, season, rnd))
        return share_cache[key]

    preds = defaultdict(list)
    for season, rnd, home, away, hs, as_, dj in conn.execute(
            'SELECT season, round, home, away, home_score, away_score, delta FROM predictions '
            'ORDER BY season, round'):
        if dj:
            preds[(season, rnd)].append((home, away, hs, as_, dj))

    rows = []
    lineup_hits = lineup_misses = 0
    for key in sorted(preds):
        season, rnd = key
        if seasons and season not in seasons:
            continue
        if limit_rounds and rnd > limit_rounds:
            continue
        for home, away, hs, as_, dj in sorted(preds[key]):
            entry = by_key.get((season, rnd, frozenset((home, away))))
            if not entry:
                continue
            m_id = entry[0]
            pars = parse_delta(dj)
            for team, proj, delta in ((home, hs, dmap(pars)),
                                      (away, as_, dmap(mirror_delta(pars)))):
                if team_games[team] < 3:
                    continue
                played = sorted({p for (p,) in conn.execute(
                    'SELECT DISTINCT player FROM player_history WHERE team=? AND m_id=?',
                    (team, m_id)).fetchall() if p and p not in ('', '0')})
                if lineup_filter:
                    side = set(player_names.lineup_ids(m_id))
                    if side:
                        kept = [p for p in played if p in side]
                        if len(kept) >= 6:
                            lineup_hits += len(played) - len(kept)
                            played = kept
                        else:
                            lineup_misses += 1
                if len(played) < 6:
                    continue
                n = len(played)
                plain, weight = defaultdict(float), defaultdict(float)
                for (player, edge), share in sorted(model_shares(team, season, rnd).items()):
                    if edge.endswith('->SCORE'):
                        plain[player] += share
                        weight[player] += share * max(0.0, delta.get(edge, 0.0))
                tot_p = sum(plain[p] for p in played)
                tot_w = sum(weight[p] for p in played)
                if tot_p <= 0 or tot_w <= 0:
                    continue
                tg = team_goals[team]
                recs = {}
                for p in played:
                    pn = plain[p] / tot_p
                    wt = weight[p] / tot_w
                    lev = math.log(wt / pn) if (pn > 0 and wt > 0) else None
                    recs[p] = {
                        'm': wt, 'h': (player_goals[(p, team)] + N_SMOOTH) / (tg + N_SMOOTH * n),
                        'u': 1.0 / n, 'plain': pn, 'weight': wt, 'leverage': lev,
                        'act': goals.get(m_id, {}).get(p, {}).get('g', 0),
                    }
                rows.append({
                    'season': season, 'round': rnd, 'team': team, 'm_id': m_id,
                    'opp': away if team == home else home,
                    'vol_actual': 6 * side_goals[(m_id, team)]['g'] + side_goals[(m_id, team)]['b'],
                    'vol_prior': team_points[team] / team_games[team],
                    'vol_model': proj or 0,
                    'players': recs,
                })
        for m2, h2, a2, hs2, as2 in matches_by_round.get((season, rnd), []):
            for t2 in (h2, a2):
                team_games[t2] += 1
                g2 = side_goals[(m2, t2)]['g']
                team_goals[t2] += g2
                team_points[t2] += 6 * g2 + side_goals[(m2, t2)]['b']
                for pid, rec in sorted(goals.get(m2, {}).items()):
                    if p2t.get((m2, pid)) == t2:
                        player_goals[(pid, t2)] += rec['g']
    if lineup_filter:
        print('lineup filter: %d players excluded as not selected, %d games kept unfiltered '
              '(roster unavailable)' % (lineup_hits, lineup_misses))
    return rows


VOLUMES = (('vol_actual', 'ACTUAL team score (isolates allocation)'),
           ('vol_prior', 'team prior average score'),
           ('vol_model', "model's projected score"))


def gate_table(rows, volumes=VOLUMES):
    out = []
    out.append('team-games: %d | player-games: %d | seasons %s' % (
        len(rows), sum(len(r['players']) for r in rows),
        sorted({r['season'] for r in rows})))
    for vol_key, vlabel in volumes:
        flat = [(r[vol_key] / PPG, rec) for r in rows for _p, rec in sorted(r['players'].items())]
        if not flat:
            continue
        out.append('--- volume = %s' % vlabel)
        for alloc, alabel in (('m', 'model allocation'), ('h', 'history allocation'),
                              ('u', 'equal shares')):
            est = [tg * rec[alloc] for tg, rec in flat]
            act = [rec['act'] for tg, rec in flat]
            mae = sum(abs(e - a) for e, a in zip(est, act)) / len(est)
            b = [sum((poisson_ge(k, e) - (1 if a >= k else 0)) ** 2
                     for e, a in zip(est, act)) / len(est) for k in (1, 2, 3, 4)]
            out.append('    %-19s miss %.2f goals | odds error 1+ %.4f 2+ %.4f 3+ %.4f 4+ %.4f '
                       '| mean est %.2f vs actual %.2f' % (
                           alabel, mae, b[0], b[1], b[2], b[3],
                           sum(est) / len(est), sum(act) / len(act)))
    out.append('--- relative markets (allocation only)')
    for alloc, alabel in (('m', 'model'), ('h', 'history'), ('u', 'equal')):
        sp, tops, pairs, hits = [], 0, 0, 0
        for r in rows:
            ps = sorted(r['players'].items())
            vg = r['vol_actual'] / PPG
            est = {p: vg * rec[alloc] for p, rec in ps}
            act = {p: rec['act'] for p, rec in ps}
            spv = spearman(est, act)
            if spv is not None:
                sp.append(spv)
            best_est = max(sorted(est), key=lambda p: (est[p], p))
            best_act = max(sorted(act), key=lambda p: (act[p], p))
            tops += 1 if est[best_est] == est[max(sorted(act), key=lambda p: (est[p], p))] and \
                est[best_est] == est[best_act] else 0
            for i in range(len(ps)):
                for j in range(i + 1, len(ps)):
                    a, ra = ps[i]
                    b_, rb = ps[j]
                    if ra['act'] == rb['act']:
                        continue
                    pairs += 1
                    if (est[a] - est[b_]) * (ra['act'] - rb['act']) > 0:
                        hits += 1
        out.append('  %-8s within-team ranking r=%.3f | top scorer #1 %.1f%% (%d/%d) | '
                   'head-to-head %.1f%% (%d/%d)' % (
                       alabel, (sum(sp) / len(sp)) if sp else float('nan'),
                       100 * tops / max(1, len(rows)), tops, len(rows),
                       100 * hits / max(1, pairs), hits, pairs))
    return '\n'.join(out)


def leverage_analysis(rows, fit_max=2024, test_seasons=(2025, 2026), market=1):
    """Does the model's log-loss advantage grow with matchup leverage?

    y = logloss(history) - logloss(model) (positive = model better), x = leverage.
    Slope fitted on seasons <= fit_max, then re-estimated per test season with a
    bootstrap CI, plus leverage-quartile means.
    """
    data = []
    for r in rows:
        vg = r['vol_actual'] / PPG
        for p, rec in sorted(r['players'].items()):
            if rec['leverage'] is None or rec['m'] <= 0 or rec['h'] <= 0:
                continue
            y = (1 if rec['act'] >= market else 0)
            data.append((r['season'], rec['leverage'],
                         logloss(rec['h'] * vg, y) - logloss(rec['m'] * vg, y)))

    def slope(pts):
        if len(pts) < 50:
            return None, None
        n = len(pts)
        mx = sum(p[0] for p in pts) / n
        my = sum(p[1] for p in pts) / n
        num = sum((p[0] - mx) * (p[1] - my) for p in pts)
        den = sum((p[0] - mx) ** 2 for p in pts)
        if den == 0:
            return None, None
        b = num / den
        return b, my - b * mx

    out = []
    fit = [(x, y) for s, x, y in data if s <= fit_max]
    b_fit, a_fit = slope(fit)
    out.append('leverage diagnostic (%d+ goals) | player-games: fit %d, test %d' % (
        market, len(fit), len(data) - len(fit)))
    if b_fit is None:
        out.append('  fit sample too small')
        return '\n'.join(out)
    out.append('  fitted on <=%d: advantage slope %+.4f per unit leverage (intercept %+.4f)'
               % (fit_max, b_fit, a_fit))
    rng = random.Random(BOOTSTRAP_SEED)
    for s in test_seasons:
        pts = [(x, y) for ss, x, y in data if ss == s]
        if len(pts) < 50:
            continue
        b, _a = slope(pts)
        boots = []
        for _ in range(BOOTSTRAP):
            samp = [pts[rng.randrange(len(pts))] for _ in range(len(pts))]
            bb, _ = slope(samp)
            if bb is not None:
                boots.append(bb)
        boots.sort()
        lo = boots[int(0.025 * len(boots))]
        hi = boots[int(0.975 * len(boots))]
        mean_adv = sum(y for _x, y in pts) / len(pts)
        out.append('  %d: slope %+.4f  95%%CI [%+.4f, %+.4f]  mean advantage %+.5f  (n=%d)'
                   % (s, b, lo, hi, mean_adv, len(pts)))
    # quartile means across the test seasons
    test = sorted((x, y) for s, x, y in data if s > fit_max)
    if test:
        q = len(test) // 4
        out.append('  mean advantage by leverage quartile (test seasons): ' + ' | '.join(
            'Q%d %+.5f' % (i + 1, sum(y for _x, y in test[i * q:(i + 1) * q]) / max(1, len(test[i * q:(i + 1) * q])))
            for i in range(4)))
    return '\n'.join(out)


def _selftest(seed=7):
    """Synthetic rows -> gate table. No DB, no data files: used by the
    determinism test (output must be identical under any PYTHONHASHSEED)."""
    rng = random.Random(seed)
    rows = []
    for g in range(120):
        season, rnd = 2025 + g % 2, 1 + g % 24
        players = {}
        for i in range(8):
            pid = 'P%02d' % i
            m = rng.random() ** 2
            players[pid] = {'m': m, 'h': rng.random() ** 2, 'u': 0.125,
                            'plain': m, 'weight': m,
                            'leverage': rng.uniform(-1, 1),
                            'act': rng.choice([0, 0, 0, 1, 1, 2, 3])}
        rows.append({'season': season, 'round': rnd, 'team': 'T%d' % (g % 4),
                     'm_id': 'M%d' % g, 'opp': 'O%d' % (g % 4),
                     'vol_actual': 60 + 6 * (g % 12), 'vol_prior': 78, 'vol_model': 84,
                     'players': players})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--goals', default=DEFAULT_GOALS, help='goals JSON from goals_extract')
    ap.add_argument('--out', default=os.path.expanduser('~/.cache/footy-props/rows.json'))
    ap.add_argument('--seasons', type=int, nargs='*', default=None)
    ap.add_argument('--limit-rounds', type=int, default=None)
    ap.add_argument('--lineup-filter', action='store_true')
    ap.add_argument('--gate', action='store_true')
    ap.add_argument('--leverage', action='store_true')
    ap.add_argument('--test-seasons', type=int, nargs='*', default=[2025, 2026])
    ap.add_argument('--fit-max', type=int, default=2024)
    ap.add_argument('--selftest', action='store_true',
                    help='run on synthetic rows (determinism check, no DB)')
    args = ap.parse_args(argv)

    if args.selftest:
        rows = _selftest()
    else:
        if not os.path.exists(args.goals):
            raise SystemExit('goals file missing: %s (run Core.tools.goals_extract first)' % args.goals)
        with open(args.goals) as fh:
            goals = json.load(fh)
        rows = build_rows(chains.connect(), goals, seasons=args.seasons,
                          lineup_filter=args.lineup_filter, limit_rounds=args.limit_rounds)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        tmp = args.out + '.tmp'
        with open(tmp, 'w') as fh:
            json.dump(rows, fh, sort_keys=True)
        os.replace(tmp, args.out)
        print('rows written: %s' % args.out)

    if args.selftest or args.gate:
        gate_rows = [r for r in rows if r['season'] in args.test_seasons]
        print(gate_table(gate_rows or rows))
    if args.leverage:
        for market in (1, 2):
            print(leverage_analysis(rows, fit_max=args.fit_max,
                                    test_seasons=tuple(args.test_seasons), market=market))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
