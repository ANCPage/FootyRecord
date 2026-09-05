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


def _own_frame(grids, team, home):
    """Rotate a chain into its team's own (top-attacking) frame if the team
    was the away side in its game (DB stores chains in the home frame)."""
    if home != team:
        return [rotate_node(g) for g in grids]
    return grids


def game_chains(conn, season, round_num, team_a, team_b):
    """{team_a: [seq,...], team_b: [seq,...]} — the ONE game's scoring
    chains, collapsed, both teams normalised to team_a's top-attacking frame.

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
        per.setdefault(team, {}).setdefault(cidx, []).append((grid, team, home))
    out = {team_a: [], team_b: []}
    for tid in (team_a, team_b):
        for cidx in sorted(per.get(tid, {})):
            cells = per[tid][cidx]
            zs = collapse(_own_frame([g for g, _t, _h in cells], tid, cells[0][2]))
            if len(zs) >= 2:
                out[tid].append(zs)
    return out, home


def window_counter(conn, season, up_to_round, team, decay=DECAY):
    """Counter of the team's distinct scoring paths through the window.

    path = collapsed zone tuple in the team's own frame; weight = decayed
    occurrence count (decay ** (up_to_round - game_round)). Used by the
    prediction card's top80 route selection.
    """
    from collections import defaultdict
    c = defaultdict(float)
    rows = state_store.window_scoring_rows(conn, season, up_to_round, [team])
    per = {}
    for mid, cidx, _seq, team_r, grid, home, rnd in rows:
        if grid in (None, ''):
            continue
        per.setdefault((mid, cidx), []).append((grid, home, rnd))
    for key in sorted(per):
        cells = per[key]
        zs = collapse(_own_frame([g for g, _h, _r in cells], team, cells[0][1]))
        if len(zs) < 2:
            continue
        w = decay ** max(up_to_round - cells[0][2], 0)
        c[tuple(zs)] += w
    return c


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


def weight_chains(paths, delta, mx):
    """Turn (path, raw_weight) selections into card chains with the model's
    route weights: w2/s2/mS from the delta, globally scaled by `mx`."""
    out = []
    for path, _w in paths:
        n = chain_net(path, delta) / mx if mx else 0.0
        out.append({'seq': list(path),
                    'w': 1.0,
                    'w2': round(max(0.06, n), 4),
                    's2': round(max(0.15, n), 3),
                    'mS': round(n, 4),
                    'kind': 'own'})
    return out
