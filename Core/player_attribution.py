"""Player attribution — an ADDED LAYER over the model's edge predictions.

2026-09-13 (Austin, approach 1): the model predicts movement at the level of
zone-to-zone EDGES; this module answers "which PLAYERS does that edge run
through?" without touching the model.

How it works, in three steps, none of which alter the prediction:

  1. WINDOW   — take the team's player involvement over the SAME memory the
     model uses (matches strictly before the slot, last `window` games, the
     queries.average_matrix semantics).
  2. SHARES   — per edge, normalise each player's historical credit into a
     share of that edge's activity (shares sum to <= 1; edges with no player
     data are skipped).
  3. ATTRIBUTE— hand each edge's delta to its players in proportion to their
     share. A player's score is therefore "how much of the model's net edge
     runs through them": positive = the model's advantage runs through them,
     negative = the routes they are exposed on.

Authorship of a route belongs to the attacking side: the engine's player
credits are OWN-team players on that team's OWN chains (the display
decomposition, C4). An opponent's chains carry the OPPONENT's players —
nobody records which defender conceded a route. So:

  * a team's FAVOURED edges attribute to its own players ("the model's
    advantage runs through these players"), and
  * that team's EXPOSURE is the OPPONENT's favoured list — the same edges
    seen from the other side of the delta, with the opponent's players on
    them. `matchup_attribution` returns both sides together.

Conservation is the invariant that keeps it honest: the attributed scores sum
back to the delta they came from — nothing is invented, nothing is lost.

Read-only by construction: no writes, and the delta dict passed in is never
mutated (asserted in tests).
"""
import json
from collections import defaultdict

import Core.state_store as state_store
import Core.chains as chains


def window_player_edges(conn, team, season, up_to_round, window=None):
    """{player: {edge: weight}} over the model's memory window.

    Mirrors queries.average_matrix: matches strictly before (season,
    up_to_round), the last `window` of them, cross-season.
    """
    window = window or 30
    hist = state_store.team_match_history(conn, team, season, up_to_round)
    mids = [m_id for (m_id, _s, _r) in hist[:window]]
    out = defaultdict(lambda: defaultdict(float))
    if not mids:
        return out
    marks = ','.join('?' * len(mids))
    rows = conn.execute(
        'SELECT player, edges FROM player_history WHERE team=? '
        'AND m_id IN (' + marks + ')', (team,) + tuple(mids)).fetchall()
    for player, edges_json in rows:
        if not edges_json:
            continue
        for edge, w in json.loads(edges_json).items():
            out[player][edge] += float(w)
    return out


def edge_shares(player_edges):
    """{(player, edge): share} — each player's share of that edge's activity.

    Shares for one edge sum to <= 1 (1.0 when player data covers the edge).
    """
    totals = defaultdict(float)
    for player, edges in player_edges.items():
        for edge, w in edges.items():
            totals[edge] += w
    shares = {}
    for player, edges in player_edges.items():
        for edge, w in edges.items():
            tot = totals[edge]
            if tot > 0:
                shares[(player, edge)] = w / tot
    return shares


def attribute_edges(delta, shares, top_n=8, min_score=0.0):
    """Distribute each edge's delta across its players.

    delta  = {(source, target): value} — THE MODEL'S OUTPUT, read only
    shares = {(player, edge_str): share} from edge_shares()

    Returns {'favoured': [...], 'exposed': [...], 'conservation': float}
    where each entry is {player, score, edges: [(edge, delta, share)]}.
    """
    # normalise the delta's edge keys to the 'A->B' string form shares use
    def key(e):
        return '%s->%s' % (e.source, e.target) if hasattr(e, 'source') \
            else '%s->%s' % (e[0], e[1])

    by_edge = defaultdict(list)
    for (player, edge), share in shares.items():
        by_edge[edge].append((player, share))

    per_player = defaultdict(lambda: defaultdict(float))
    total_in = 0.0
    attributable = 0.0           # only positive edges carry own-player credits
    for e, val in delta.items():
        k = key(e)
        total_in += float(val)
        if val > 0:
            attributable += float(val) * sum(s for _p, s in by_edge.get(k, ()))
        for player, share in by_edge.get(k, ()):
            per_player[player][k] += float(val) * share

    entries = []
    for player, edges in per_player.items():
        score = sum(edges.values())
        if abs(score) < min_score:
            continue
        top = sorted(edges.items(), key=lambda kv: -abs(kv[1]))[:4]
        entries.append({'player': player, 'score': score,
                        'edges': [(e, round(v, 5), round(shares[(player, e)], 3))
                                  for e, v in top]})
    favoured = sorted([x for x in entries if x['score'] > 0],
                      key=lambda x: -x['score'])[:top_n]
    exposed = sorted([x for x in entries if x['score'] < 0],
                     key=lambda x: x['score'])[:top_n]
    return {'favoured': favoured, 'exposed': exposed,
            'conservation': sum(x['score'] for x in entries),
            'delta_total': total_in,
            'attributable': attributable}


def attribute_matchup(conn, team, season, up_to_round, delta, window=None,
                      top_n=8):
    """Convenience: the whole layer for one team's side of a matchup."""
    pe = window_player_edges(conn, team, season, up_to_round, window=window)
    return attribute_edges(delta, edge_shares(pe), top_n=top_n)


def matchup_attribution(conn, team_a, team_b, season, up_to_round,
                        delta_a, delta_b, window=None, top_n=8):
    """Both sides of a matchup in one call.

    delta_a = the model's delta in team_a's frame; delta_b = the same net read
    in team_b's frame (Core.cards.mirror_delta gives that from the stored
    delta). Each team's FAVOURED list names the players its advantage runs
    through; team_a's exposure is team_b's favoured list.
    """
    return {
        'top': dict(attribute_matchup(conn, team_a, season, up_to_round,
                                      delta_a, window=window, top_n=top_n),
                    team=team_a),
        'bottom': dict(attribute_matchup(conn, team_b, season, up_to_round,
                                         delta_b, window=window, top_n=top_n),
                       team=team_b),
    }
