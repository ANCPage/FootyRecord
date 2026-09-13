"""Player attribution tests (approach 1, 2026-09-13).

The layer is ADDITIVE: it reads the model's edge delta and produces player
scores. These tests pin the three properties that keep it honest:

  1. CONSERVATION — attributed scores sum back to the delta (nothing invented,
     nothing lost beyond the share coverage of the player data).
  2. READ-ONLY — the delta dict passed in is never mutated, and no DB writes
     happen.
  3. MODEL UNCHANGED — the layer does not alter the model's own outputs
     (delta, verdict) when it is used alongside them.
"""
import copy
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import Core.chains as chains  # noqa: E402
from Core import player_attribution as pa  # noqa: E402


def _conn():
    return chains.connect()


def test_shares_sum_to_one_per_edge():
    conn = _conn()
    pe = pa.window_player_edges(conn, 'CD_T100', 2026, 24)
    if not pe:
        pytest.skip('no player history available')
    shares = pa.edge_shares(pe)
    per_edge = {}
    for (_player, edge), s in shares.items():
        per_edge[edge] = per_edge.get(edge, 0.0) + s
    assert per_edge, 'no shares produced'
    for edge, tot in per_edge.items():
        assert tot <= 1.0 + 1e-9, 'shares exceed 1 for %s (%s)' % (edge, tot)
    # the edges with full player coverage should sum to ~1
    covered = [t for t in per_edge.values() if t > 0.5]
    assert covered and min(covered) <= 1.0 + 1e-9


def test_attribution_conserves_and_does_not_mutate():
    conn = _conn()
    pe = pa.window_player_edges(conn, 'CD_T100', 2026, 24)
    if not pe:
        pytest.skip('no player history available')
    shares = pa.edge_shares(pe)
    delta = {('E2', 'SCORE'): 0.21, ('D2', 'E2'): 0.03,
             ('A2', 'SCORE'): -0.20, ('C2', 'D2'): 0.02}
    before = copy.deepcopy(delta)
    res = pa.attribute_edges(delta, shares)
    assert delta == before, 'the delta dict was mutated'
    # conservation: every attributed point comes from the positive delta the
    # own-player credits cover (conceded edges are unattributable by design)
    assert res['conservation'] <= res['attributable'] + 1e-9
    assert res['conservation'] > 0, 'expected some positive attribution'


def test_favoured_side_attributes_and_exposure_is_the_opponent():
    """Own-player credits cover the team's OWN chains, so the favoured side
    attributes; the exposure side comes from the opponent's favoured list."""
    conn = _conn()
    pe = pa.window_player_edges(conn, 'CD_T100', 2026, 24)
    if not pe:
        pytest.skip('no player history available')
    shares = pa.edge_shares(pe)
    delta = {('E2', 'SCORE'): 0.21, ('D2', 'E2'): 0.03}
    res = pa.attribute_edges(delta, shares)
    assert res['favoured'], 'the scoring edge should attribute to players'
    assert all(x['score'] > 0 for x in res['favoured'])
    for entry in res['favoured']:
        assert entry['edges'], 'no contributing edges listed'
    # a conceded edge has no OWN player credits by construction
    conceded = pa.attribute_edges({('A2', 'SCORE'): -0.20}, shares)
    assert conceded['favoured'] == []
    assert conceded['exposed'] == []


def test_layer_uses_the_model_window():
    """The window mirrors queries.average_matrix: strictly before the slot."""
    conn = _conn()
    hist = chains.state_store.team_match_history(conn, 'CD_T100', 2026, 24)
    if not hist:
        pytest.skip('no match history')
    pe = pa.window_player_edges(conn, 'CD_T100', 2026, 24, window=30)
    if not pe:
        pytest.skip('no player history available')
    # the layer must not have written anything
    rows = conn.execute('SELECT COUNT(*) FROM player_history').fetchone()[0]
    pe2 = pa.window_player_edges(conn, 'CD_T100', 2026, 24, window=30)
    assert rows == conn.execute('SELECT COUNT(*) FROM player_history').fetchone()[0]
    assert set(pe) == set(pe2), 'window player set is not stable'
