"""Profiling math extracted from DataIngestor (Phase 3, 2026-08-26).

Pure functions over state dicts — no I/O, no DataIngestor dependency.
engine_data.DataIngestor delegates here; contract tests in tests/test_profiler.py
lock the exact semantics (they were written FIRST).

Everything here is DECAY-INDEPENDENT accumulation + fit logic. The rule of
thumb: if it touches `self` only to read a data structure, it belongs here.
"""

from collections import defaultdict
from typing import Any, Dict, List

from Core.models import TransitionEdge

# Distance buckets for per-position storage (Option B): chain edges are
# bucketed by distance-from-end 0..POSITIONS-1; longer chains lump the tail
# into the last bucket. At decay 0.3 the tail contributes <0.01% of weight.
POSITIONS = 12


def _player_factory():
    """Picklable nested-defaultdict factory for per-distance player credits."""
    return defaultdict(float)


def accumulate_match_positions(chains: List[dict], h_team: str, a_team: str):
    """Per-match, per-distance raw edge weights (decay-independent).

    Mirrors the original Graph accumulation exactly: own chains +1 as-is,
    opponent chains -1 rotated 180deg; player credits per distance, OWN-team
    players only (C4: the player layer is a display decomposition).
    Returns (h_pos, a_pos, h_player, a_player).
    """
    from Core.engine_core import Graph, collapse_chain

    h_pos = [defaultdict(float) for _ in range(POSITIONS)]
    a_pos = [defaultdict(float) for _ in range(POSITIONS)]
    h_player = [defaultdict(_player_factory) for _ in range(POSITIONS)]
    a_player = [defaultdict(_player_factory) for _ in range(POSITIONS)]
    g = Graph('util')

    for chain in chains:
        if chain.get('outcome') != 'SCORE':
            continue
        edges, collapsed_players = collapse_chain(chain)
        if edges is None:
            continue
        n = len(edges)
        cteam = chain['team']
        for i, (start, end) in enumerate(edges, 1):
            d = n - i
            if d >= POSITIONS:
                d = POSITIONS - 1
            if cteam == h_team:
                s, e, sign = start, end, 1.0
            else:
                s, e, sign = g.rotate_node(start), g.rotate_node(end), -1.0
            if s in g.nodes:
                h_pos[d][TransitionEdge(s, e)] += sign
            if cteam == a_team:
                s2, e2, sign2 = start, end, 1.0
            else:
                s2, e2, sign2 = g.rotate_node(start), g.rotate_node(end), -1.0
            if s2 in g.nodes:
                a_pos[d][TransitionEdge(s2, e2)] += sign2
            inv = list(collapsed_players[i - 1]) if i - 1 < len(collapsed_players) else []
            for p in inv:
                if cteam == h_team:
                    h_player[d][p][(start, end)] += 1.0
                else:
                    a_player[d][p][(start, end)] += 1.0
    return h_pos, a_pos, h_player, a_player


def recombine(pos_list: List[dict], decay: float) -> Dict[Any, float]:
    """Recombine per-position weights at a decay and apply E2 normalization."""

    mat = defaultdict(float)
    for d, pos in enumerate(pos_list):
        if not pos:
            continue
        w = decay ** d
        if w == 0.0:
            continue
        for e, v in pos.items():
            mat[e] += w * v
    total = sum(abs(v) for v in mat.values())
    if total <= 0:
        return {}
    return {e: v / total for e, v in mat.items()}


def bake_players(player_pos: List[dict], decay: float) -> Dict[str, Dict[Any, float]]:
    """Bake distance-bucketed player credits at a decay (old schema)."""
    from Core.models import TransitionEdge

    baked = {}
    for d, pid_map in enumerate(player_pos):
        w = decay ** d
        if w == 0.0:
            continue
        for pid, edges in pid_map.items():
            dct = baked.setdefault(pid, {})
            for (s, e), v in edges.items():
                dct[(s, e)] = dct.get((s, e), 0.0) + w * v
    return {k: {TransitionEdge(*edge): score for edge, score in v.items()}
            for k, v in baked.items()}


def fit_decay(match_positions, match_info, actual_winners,
              candidates=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.9, 1.0)):
    """Fit decay on net-delta sign agreement with actual results.

    Elo-free (no circularity) and fast: recombination only, no profiling.
    Returns (best_decay, best_accuracy).
    """
    from Core.engine_core import MatchupEngine

    best, best_acc = None, -1.0
    for cand in candidates:
        correct = total = 0
        for m_id, (h_pos, a_pos) in match_positions.items():
            info = match_info.get(m_id)
            if info is None or m_id.startswith('POST_'):
                continue
            actual = actual_winners.get(m_id)
            if actual not in (info.home, info.away):
                continue
            h_mat = recombine(h_pos, cand)
            a_mat = recombine(a_pos, cand)
            if not h_mat or not a_mat:
                continue
            net = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())
            if (net > 0) == (actual == info.home):
                correct += 1
            total += 1
        acc = correct / total if total else 0.0
        if acc > best_acc:
            best, best_acc = cand, acc
    return best, best_acc


def build_fit_rows(match_info, team_elo_history, match_performance) -> List[tuple]:
    """Rows for calibration fitting: (season, round, expected net_delta,
    elo diff, actual margin, actual total, actual delta) — all pre-match
    expectations and post-match outcomes, no-lookahead by construction
    (expected deltas were computed before the match was appended).
    """
    elo_at = defaultdict(dict)
    for team, hist in team_elo_history.items():
        for m_id, elo in hist:
            if m_id.startswith('POST_'):
                continue
            elo_at[m_id][team] = elo
    rows = []
    for m_id, info in match_info.items():
        if m_id.startswith('POST_'):
            continue
        if info.home_score == 0 and info.away_score == 0:
            continue
        # draws INCLUDED (policy B, 2026-08-11): a draw is a margin-0
        # outcome — valid training point, and a guaranteed miss for the
        # winner-only model (a draw can't be tipped)
        perf = match_performance.get(m_id, {})
        exp = perf.get('expected')
        if exp is None:
            continue
        eh = elo_at.get(m_id, {}).get(info.home)
        ea = elo_at.get(m_id, {}).get(info.away)
        if eh is None or ea is None:
            continue
        rows.append((info.season, info.round, exp, eh - ea,
                     info.home_score - info.away_score,
                     info.home_score + info.away_score,
                     perf.get('actual', exp),
                     m_id, info.home, info.away))
    return rows


def fit_calibration(rows: List[tuple], team_elo_history, window_seasons=None):
    """Fit dynamic calibration on the given rows plus distribution-relative
    tier cutoffs from the live Elo field."""
    import Core.calibration as cal

    if not rows:
        return cal.Calibration.fallback()
    cur_season = max(r[0] for r in rows)
    sel = cal.select_window(rows, cur_season, window_seasons)
    label = f'roll{window_seasons}' if window_seasons else 'expanding'
    c = cal.fit_or_fallback(sel, label)
    # Tier cutoffs: top-4/next-4/next-5 from the CURRENT Elo distribution
    # (tiers read as relative strength — E1 watch item, midpoint cutoffs).
    latest = {}
    for team, hist in team_elo_history.items():
        if hist:
            latest[team] = hist[-1][1]
    c.tier_cutoffs = cal.compute_tier_cutoffs(list(latest.values()))
    return c
