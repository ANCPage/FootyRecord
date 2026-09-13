"""Player-goals estimator: allocation from the model, volume from outside it.

The model's structure knows WHERE a team will go (which edges, against which
opponent). It does not know HOW MANY goals the team kicks — margins, totals and
edge magnitudes are all shrunk, measured. So this module refuses to invent the
volume: the team's goal total is an input (the market's number, or a
walk-forward prior if none is supplied), and the model only decides the split.

Read-only by construction: it queries the DB and never writes to it.

    from Core.player_props import prop_estimates
    est = prop_estimates(conn, 'CD_T160', 2026, 24, team_goal_total=12.0)
    est['CD_I290284']['expected_goals'], est['CD_I290284']['p_2plus']

Interface:
    prop_estimates(conn, team, season, round_num, team_goal_total=None,
                   points_per_goal=PPG, lineup=None, players=None)
        -> {player_id: {'expected_goals', 'share', 'p_1plus'..'p_4plus'}}
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Core.state_store as state_store  # noqa: E402
from Core.cards import mirror_delta, parse_delta  # noqa: E402
from Core import player_attribution as pa  # noqa: E402

PPG = 6.71              # points per goal, 2021-2026 league average
WINDOW = 30             # games for the volume fallback
MIN_GAMES = 3           # below this, fall back to the league-ish default total


def dmap(delta):
    """Stored delta (TransitionEdge keys) -> {'A2->B2': value}."""
    out = {}
    for k, v in delta.items():
        kk = '%s->%s' % (k.source, k.target) if hasattr(k, 'source') else '%s->%s' % (k[0], k[1])
        out[kk] = float(v)
    return out


def poisson_ge(k, lam):
    """P(X >= k) for a Poisson mean, computed iteratively (no scipy)."""
    if lam <= 0:
        return 0.0
    cdf, term = 0.0, math.exp(-lam)
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, min(1.0, 1 - cdf))


def logloss(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(math.log(p) if y else math.log(1 - p))


def prior_average_score(conn, team, season, round_num, window=WINDOW):
    """The team's mean score over its games BEFORE this round (walk-forward).
    Returns None when there is not enough history."""
    rows = conn.execute(
        'SELECT season, round, home, away, home_score, away_score FROM matches '
        'WHERE (season < ? OR (season = ? AND round < ?)) AND (home = ? OR away = ?) '
        'ORDER BY season DESC, round DESC LIMIT ?',
        (season, season, round_num, team, team, window)).fetchall()
    scores = []
    for _s, _r, home, away, hs, as_ in rows:
        if home == team and hs is not None:
            scores.append(hs)
        elif away == team and as_ is not None:
            scores.append(as_)
    if len(scores) < MIN_GAMES:
        return None
    return sum(scores) / len(scores)


def _matchup_delta(conn, team, season, round_num):
    """The model's stored delta on the team's own frame for this fixture."""
    match = conn.execute(
        'SELECT m_id, home, away FROM matches WHERE season=? AND round=? AND (home=? OR away=?)',
        (season, round_num, team, team)).fetchone()
    if not match:
        return None, None
    m_id, home, away = match
    row = conn.execute(
        'SELECT delta FROM predictions WHERE season=? AND round=? AND home=? AND away=?',
        (season, round_num, home, away)).fetchone()
    if not row or not row[0]:
        return m_id, None
    parsed = parse_delta(row[0])
    return m_id, (dmap(parsed) if team == home else dmap(mirror_delta(parsed)))


def prop_estimates(conn, team, season, round_num, team_goal_total=None,
                   points_per_goal=PPG, lineup=None, players=None):
    """Per-player expected goals and threshold probabilities for one team's game.

    team_goal_total : the team's goals (NOT points). Supplied = used as-is.
                      None -> the team's prior average score / points_per_goal.
    lineup          : iterable of player ids actually selected; others are dropped
                      and the shares renormalise over the survivors.
    players         : optional restriction to a set of player ids.
    """
    m_id, delta = _matchup_delta(conn, team, season, round_num)
    shares = pa.edge_shares(pa.window_player_edges(conn, team, season, round_num))
    if not shares:
        return {}

    terminal = {e: s for e, s in shares.items() if e[1].endswith('->SCORE')}
    scored = sorted({p for (p, _e) in terminal})
    if players is not None:
        keep = set(players)
        scored = [p for p in scored if p in keep]
    if lineup is not None:
        keep = set(lineup)
        scored = [p for p in scored if p in keep]
    if not scored:
        return {}

    weight = {}
    for p in scored:
        total = 0.0
        for (_p, edge), share in sorted(terminal.items()):
            if _p != p:
                continue
            if delta is None:
                total += share
            else:
                total += share * max(0.0, delta.get(edge, 0.0))
        weight[p] = total
    tot = sum(weight.values())
    if tot <= 0:
        # no usable matchup signal -> plain route shares over the same players
        weight = {p: sum(s for (_p, _e), s in sorted(terminal.items()) if _p == p)
                  for p in scored}
        tot = sum(weight.values())
        if tot <= 0:
            return {}

    if team_goal_total is None:
        prior = prior_average_score(conn, team, season, round_num)
        team_goal_total = (prior / points_per_goal) if prior else 160.0 / points_per_goal

    out = {}
    for p in scored:
        share = weight[p] / tot
        lam = team_goal_total * share
        out[p] = {
            'expected_goals': lam,
            'share': share,
            'm_id': m_id,
            'team_goal_total': team_goal_total,
            'p_1plus': poisson_ge(1, lam),
            'p_2plus': poisson_ge(2, lam),
            'p_3plus': poisson_ge(3, lam),
            'p_4plus': poisson_ge(4, lam),
        }
    return out


def team_goal_total_from_market(conn, team, season, round_num, market_total=None):
    """Helper: prefer a supplied market total, else the walk-forward prior."""
    if market_total is not None:
        return market_total
    prior = prior_average_score(conn, team, season, round_num)
    return (prior / PPG) if prior else 160.0 / PPG
