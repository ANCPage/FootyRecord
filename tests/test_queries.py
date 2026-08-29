"""Phase 3 contract tests: Core.queries (read-only accessors extracted from
DataIngestor). RED first, GREEN after extraction.

Locks the window/decay/filter semantics of get_team_average_matrix and
get_team_player_matrix — the two queries whose outputs feed every
prediction and every card.
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from Core.models import MatchInfo, TransitionEdge
from Core.queries import average_matrix, player_matrix


def _mi(season, round_num):
    mi = MatchInfo(season=season, round=round_num, home='HOME', away='AWAY')
    mi.match_id = f'{season}R{round_num}'
    return mi


def _pos(*edge_pairs):
    """One match's position list: edge -> weight at depth 0.
    Call as _pos(('C2','D2'), 1.0) or _pos(('A','B'), 1.0, ('C','D'), 2.0)."""
    p = [defaultdict(float)]
    it = iter(edge_pairs)
    for edge, v in zip(it, it):
        p[0][TransitionEdge(*edge)] = v
    return p


def test_average_matrix_window_and_round_filter():
    """history[-window:] AFTER dropping matches >= up_to_round; each match is
    E2-normalized (sum|edges| = 1) by recombine BEFORE averaging — so the
    average reflects edge COMPOSITION, not raw magnitudes."""
    team_positions = {
        'HOME': [
            ('S1R1', _pos(('C2', 'D2'), 1.0)),
            ('S1R2', _pos(('C2', 'D2'), 1.0, ('D2', 'E2'), 1.0)),
            ('S1R3', _pos(('D2', 'E2'), 5.0)),
        ],
    }
    match_info = {'S1R1': _mi(2021, 1), 'S1R2': _mi(2021, 2), 'S1R3': _mi(2021, 3)}

    class Cal:
        decay_factor = 1.0

    mat = average_matrix(team_positions, match_info, Cal(),
                         'HOME', window=2, up_to_season=2021, up_to_round=3)
    # window=2 on matches < R3 -> [S1R1, S1R2]; E2 makes each total 1.0:
    # S1R1 {C2D2: 1.0}, S1R2 {C2D2: 0.5, D2E2: 0.5} -> averaged
    assert mat[TransitionEdge('C2', 'D2')] == pytest.approx(0.75)
    assert mat[TransitionEdge('D2', 'E2')] == pytest.approx(0.25)


def test_average_matrix_respects_up_to_match_id():
    team_positions = {
        'HOME': [('M1', _pos(('C2', 'D2'), 2.0)), ('M2', _pos(('D2', 'E2'), 8.0))],
    }
    mat = average_matrix(team_positions, {}, Cal(0.5), 'HOME',
                         window=5, up_to_match_id='M2')
    assert TransitionEdge('C2', 'D2') in mat
    assert TransitionEdge('D2', 'E2') not in mat


def test_average_matrix_empty():
    assert average_matrix({}, {}, Cal(0.5), 'HOME', window=5) == {}


def test_average_matrix_decay_applied():
    """decay < 1 de-weights older buckets via recombine (depth-1 edge at 0.5)."""
    team_positions = {'HOME': [('M1', _pos(('C2', 'D2'), 2.0))]}
    mat = average_matrix(team_positions, {}, Cal(0.5), 'HOME', window=5)
    assert mat[TransitionEdge('C2', 'D2')] == pytest.approx(1.0)  # 2.0 at depth 1 -> 2*0.5


def test_player_matrix_window_average():
    team_player_history = {
        'HOME': [
            ('M1', {'P1': {TransitionEdge('C2', 'D2'): 2.0}}),
            ('M2', {'P1': {TransitionEdge('C2', 'D2'): 4.0}}),
        ],
    }
    pm = player_matrix(team_player_history, {}, 'HOME', window=2)
    assert pm['P1'][TransitionEdge('C2', 'D2')] == pytest.approx(3.0)


def test_player_matrix_empty():
    assert player_matrix({}, {}, 'HOME', window=5) == {}


class Cal:
    def __init__(self, decay):
        self.decay_factor = decay
