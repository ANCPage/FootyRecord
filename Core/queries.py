"""Read-only state accessors extracted from DataIngestor (Phase 3, 2026-08-26).

These are the queries that feed every prediction and every card. They take
the state structures explicitly (team_positions, match_info, calibration,
team_player_history) so nothing here depends on the ingestor — contract tests
in tests/test_queries.py were written FIRST to lock the exact semantics.
"""

from collections import defaultdict
from typing import Any, Dict

import Core.config as config


def average_matrix(team_positions: Dict, match_info: Dict, calibration: Any,
                   team_id: str, window: int = None,
                   up_to_match_id: str = None, up_to_season: int = None,
                   up_to_round: int = None,
                   return_history_info: bool = False) -> Any:
    """Decay-aware average transition matrix over the team's recent window.

    Semantics (locked by tests): filter history to matches strictly before
    up_to_season/up_to_round (or up to up_to_match_id exclusive), take the
    last `window`, recombine each at the ACTIVE decay, average.
    """
    from Core.profiler import recombine

    if window is None:
        window = config.config.window_size
    decay = getattr(calibration, 'decay_factor', None) or config.config.decay_factor
    history = team_positions.get(team_id, [])
    filtered_history = []
    for m_id, pos in history:
        if up_to_match_id and m_id == up_to_match_id:
            break
        if up_to_season is not None and up_to_round is not None:
            info = match_info.get(m_id)
            if info and (info.season > up_to_season or (info.season == up_to_season and info.round >= up_to_round)):
                continue
        filtered_history.append((m_id, pos))

    history = filtered_history[-window:]
    if not history:
        return ({}, []) if return_history_info else {}

    avg_matrix = defaultdict(float)
    used_matches = []
    for m_id, pos in history:
        info = match_info.get(m_id)
        if info:
            used_matches.append(f"R{info.round}_{info.season}")
        else:
            used_matches.append(m_id)
        mat = recombine(pos, decay)
        for edge, score in mat.items():
            avg_matrix[edge] += score / len(history)

    if return_history_info:
        return dict(avg_matrix), used_matches
    return dict(avg_matrix)


def player_matrix(team_player_history: Dict, match_info: Dict,
                  team_id: str, window: int = None,
                  up_to_match_id: str = None, up_to_season: int = None,
                  up_to_round: int = None) -> Dict[str, Dict[Any, float]]:
    """Average per-player transition matrix over the team's recent window
    (same filter semantics as average_matrix)."""
    if window is None:
        window = config.config.window_size
    history = team_player_history.get(team_id, [])
    filtered_history = []
    for m_id, mat in history:
        if up_to_match_id and m_id == up_to_match_id:
            break
        if up_to_season is not None and up_to_round is not None:
            info = match_info.get(m_id)
            if info and (info.season > up_to_season or (info.season == up_to_season and info.round >= up_to_round)):
                continue
        filtered_history.append((m_id, mat))

    history = filtered_history[-window:]
    if not history:
        return {}
    avg_player_matrix = defaultdict(lambda: defaultdict(float))
    for _, p_mat in history:
        for pid, edges in p_mat.items():
            for edge, score in edges.items():
                avg_player_matrix[pid][edge] += score / len(history)
    return dict(avg_player_matrix)
