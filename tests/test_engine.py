"""Unit tests for the graph engine: edge scoring and delta math (audit #20)."""
from engine_core import Graph, MatchupEngine
from models import TransitionEdge


def test_home_edge_not_rotated():
    g = Graph('H')
    g.add_edge_score('E2', 'SCORE', 1.0, 'H')
    m = g.get_edge_matrix()
    assert m[TransitionEdge('E2', 'SCORE')] == 1.0


def test_opponent_edge_rotated_and_negated():
    g = Graph('H')
    g.add_edge_score('E2', 'SCORE', 1.0, 'A')  # opponent's FF->goal
    m = g.get_edge_matrix()
    # rotate(E2)=A2, rotate(SCORE)=SCORE, and the score is negated
    assert m[TransitionEdge('A2', 'SCORE')] == -1.0


def test_delta_empty_matrices():
    assert MatchupEngine.calculate_delta({}, {}) == {}


def test_delta_union_includes_rotated_keys():
    # union = A's raw keys + B's rotated keys
    m_a = {TransitionEdge('E2', 'SCORE'): 0.5}
    m_b = {TransitionEdge('E2', 'SCORE'): 0.5}
    d = MatchupEngine.calculate_delta(m_a, m_b)
    assert TransitionEdge('E2', 'SCORE') in d
    assert TransitionEdge('A2', 'SCORE') in d  # rotated counterpart of m_b's key


def test_delta_antisymmetry():
    m_a = {TransitionEdge('E2', 'SCORE'): 0.8,
           TransitionEdge('C2', 'D2'): 0.5}
    m_b = {TransitionEdge('E2', 'SCORE'): 0.3,
           TransitionEdge('C2', 'D2'): 0.9}
    d_ab = MatchupEngine.calculate_delta(m_a, m_b)
    d_ba = MatchupEngine.calculate_delta(m_b, m_a)
    g = Graph('util')
    for key, val in d_ab.items():
        rotated = TransitionEdge(g.rotate_node(key.source), g.rotate_node(key.target))
        assert abs(d_ba[rotated] + val) < 1e-9, f"antisymmetry failed at {key}"


def test_delta_value_math():
    e = TransitionEdge('E2', 'SCORE')
    m_a = {e: 0.8}
    m_b = {e: 0.3}
    d = MatchupEngine.calculate_delta(m_a, m_b)
    # delta[E2->SCORE] = val_a(E2->SCORE) - val_b(rotate(E2->SCORE)=A2->SCORE)
    assert abs(d[e] - 0.8) < 1e-9
    # and the rotated key: delta[A2->SCORE] = val_a(A2->SCORE=0) - val_b(E2->SCORE)
    assert abs(d[TransitionEdge('A2', 'SCORE')] + 0.3) < 1e-9
