"""Canonical scoring-chain extraction + route weighting for card media.

ONE-SYSTEM rule (2026-09-05): all SQL lives in Core.state_store; all model
numbers come from Core.prediction.compute_matchup. This module is pure python
over those — the only way recap/net/pred cards obtain chains and weights.
Every chain is normalised to the TOP-attacking frame (team A's frame); the
bottom end materialises the same zones flipped (presentation, liquid/geom).

Canonical chain semantic = the model's own: consecutive same-zone events are
collapsed (Core.engine_core.collapse_chain), so a chain's edges here ARE the
matrix edges the model rates.
"""
from collections import defaultdict

import Core.config as config
import Core.state_store as state_store
from Core.geometry import rotate_node

DECAY = 0.3


def connect():
    """Read-only connection to the results DB (config-owned path)."""
    return state_store.connect(config.RESULTS_DB)


def collapse(zs):
    out = []
    for z in zs:
        if not out or out[-1] != z:
            out.append(z)
    return out


def game_chains(conn, season, round_num, team_a, team_b):
    """{team_a: [seq,...], team_b: [seq,...]} — the ONE game's scoring
    chains, collapsed. Chains are stored in EACH team's own attacking-up
    frame already (raw chains ascend A->E toward the shot for home AND away
    teams; the engine's profiler also takes own chains as-is) — NO rotation
    here. The card's ends map them: top team -> pos, bottom team -> flip.

    Returns ({}, None) when the matchup has no row in `matches`.
    """
    row = state_store.match_row(conn, season, round_num, team_a, team_b)
    if not row:
        return {}, None
    mid, home = row[0], row[1]
    per = {}
    for cidx, _seq, team, grid in state_store.game_chain_rows(conn, mid):
        if grid in (None, ''):
            continue
        per.setdefault(team, {}).setdefault(cidx, []).append(grid)
    out = {team_a: [], team_b: []}
    for tid in (team_a, team_b):
        for cidx in sorted(per.get(tid, {})):
            zs = collapse(per[tid][cidx])
            if zs:  # single-zone chains are real scoring chains (direct shots)
                out[tid].append(zs)
    return out, home


def window_counter(conn, season, up_to_round, team, window=None):
    """Counter of the team's distinct scoring paths over the MODEL's memory.

    Aligned to queries.average_matrix (2026-09-07, Austin: "align it
    properly"): the team's scoring chains come ONLY from its last `window`
    (30) matches strictly before the slot, cross-season — flat counts, NO
    per-round decay (the engine flat-averages its window; re-weighting by
    round age was an approximation and is gone). path = collapsed zone tuple
    in the team's own frame. Used by the prediction card's top80 selection.
    """
    from collections import defaultdict
    window = window or config.config.window_size
    hist = state_store.team_match_history(conn, team, season, up_to_round)
    mids = {m_id for (m_id, _s, _r) in hist[:window]}
    if not mids:
        return defaultdict(float)
    rows = state_store.chains_for_matches(conn, mids, team)
    per = defaultdict(list)
    for mid, cidx, grid in rows:
        if grid in (None, ''):
            continue
        per[(mid, cidx)].append(grid)
    c = defaultdict(float)
    for key in sorted(per):
        zs = collapse(per[key])          # own-frame already, no rotation
        if zs:
            c[tuple(zs)] += 1.0
    return c


def window_edges(conn, season, up_to_round, team, window=None):
    """The team's EDGE histogram over the model's memory window — collapse-
    counted transitions incl. the shot edge, flat over the last `window`
    matches before the slot. This is the unsigned shape of the matrix the
    model aggregates (its unit is the edge, never the whole path)."""
    from collections import defaultdict
    window = window or config.config.window_size
    hist = state_store.team_match_history(conn, team, season, up_to_round)
    mids = {m_id for (m_id, _s, _r) in hist[:window]}
    if not mids:
        return defaultdict(float)
    rows = state_store.chains_for_matches(conn, mids, team)
    per = defaultdict(list)
    for mid, cidx, grid in rows:
        if grid in (None, ''):
            continue
        per[(mid, cidx)].append(grid)
    e = defaultdict(float)
    for key in per:
        zs = collapse(per[key])          # own-frame already, no rotation
        for u, v in zip(zs, zs[1:] + ['SCORE']):
            e[(u, v)] += 1.0
    return e


def edge_scored_routes(paths, edge_hist, cap=60):
    """Routes by EDGE recurrence — the model's unit. A chain's score = mean
    frequency of its edges in the window, so a diverse deep-origin chain that
    uses the common corridor edges ranks beside the recurring shots (whole-
    path recurrence alone would keep only square shots and hide the field).
    `paths` = the window's distinct collapsed chains with their counts;
    returns the top `cap` by edge score, count as a tie-break."""
    scored = []
    for path, cnt in paths:
        zs = list(path)
        edges = [(zs[i], zs[i + 1]) for i in range(len(zs) - 1)]
        edges.append((zs[-1], 'SCORE'))
        if not edges:
            continue
        score = sum(edge_hist.get(e, 0) for e in edges) / len(edges)
        scored.append((score, cnt, path))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return [(t[2], t[1]) for t in scored[:cap]]


def recurring_routes(counter, min_count=4, cap=60):
    """Routes the model has actually SEEN in its window: distinct paths
    occurring >= min_count times over the team's last-30 matches, heaviest
    first, capped at `cap` (visual budget). The flat window's mass is a long
    tail (no route dominates — top90 covers ~56%), so an 80%-mass cut would
    return hundreds of once-off routes; recurrence is the honest selector.
    The prediction card weights each returned route by the delta regardless.
    """
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(path, w) for path, w in items if w >= min_count][:cap]


def top80(counter, frac=0.80, floor=12):
    """Paths covering `frac` of the counter's total weight (>= floor items),
    heaviest first — the prediction card's route selection (recorded logic)."""
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    tot = sum(counter.values()) or 1
    out, acc = [], 0.0
    for path, w in items:
        out.append((path, w))
        acc += w
        if acc / tot >= frac and len(out) >= floor:
            break
    return out


def chain_net(path, delta):
    """mean max(0, signed net) over the chain's edges incl. the shot edge.

    delta = the model's per-edge signed net dict (compute_matchup delta in
    the relevant frame), keyed (source, target) tuples.
    """
    zs = list(path)
    vals = [delta.get((zs[i], zs[i + 1]), 0) for i in range(len(zs) - 1)]
    vals.append(delta.get((zs[-1], 'SCORE'), 0))
    return sum(max(0.0, v) for v in vals) / max(1, len(vals))
