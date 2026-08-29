"""Phase 3 contract tests: the profiling math extracted to Core.profiler.

These lock the EXACT accumulation/recombination/fit semantics BEFORE the
DataIngestor split — hand-computed expectations, no ingestor involved.
RED first (modules don't exist yet), GREEN after the extraction.

Grid convention (5x3, A1..E3): row A = defensive end, E = forward line.
rotate_node flips 180deg: E2 <-> A2, C1 <-> C3, etc.
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from Core.models import TransitionEdge
from Core.profiler import (
    accumulate_match_positions,
    bake_players,
    build_fit_rows,
    fit_calibration,
    fit_decay,
    recombine,
)


def _chain(team, grids, outcome='SCORE'):
    return {'team': team, 'outcome': outcome, 'grids': grids,
            'players': ['P1'] * len(grids), 'matchId': 'M1'}


# NOTE (verified against the real DB, 2026-08-26): the chains table NEVER
# stores 'SCORE' as a grid — 0 rows have grid='SCORE'. Scoring chains end at
# the shot cell (E2, D2, ...); collapse_chain appends the (last_cell -> SCORE)
# shot edge. Fixtures below therefore END AT THE SHOT CELL, never at SCORE —
# a fixture with 'SCORE' in the grids produces a phantom (SCORE, SCORE)
# self-loop that production never exhibits.


# ---------------------------------------------------------------- accumulate

def test_accumulate_home_chain_single_edge():
    """Home SCORE chain D2->E2 (shot from E2): home pos gets +1 at depth 0
    (shot edge E2->SCORE) and +1 at depth 1 (entry D2->E2); away pos gets the
    ROTATED + negated version."""
    h_pos, a_pos, h_pl, a_pl = accumulate_match_positions(
        [_chain('HOME', ['D2', 'E2'])], 'HOME', 'AWAY')
    # home: edges as-is
    assert h_pos[0][TransitionEdge('E2', 'SCORE')] == 1.0
    assert h_pos[1][TransitionEdge('D2', 'E2')] == 1.0
    # no phantom SCORE self-loop
    assert TransitionEdge('SCORE', 'SCORE') not in h_pos[0]
    # away (opponent) frame: rotated + negated
    assert a_pos[0][TransitionEdge('A2', 'SCORE')] == -1.0
    assert a_pos[1][TransitionEdge('B2', 'A2')] == -1.0  # D2->E2 rotated
    # player credit: own team only, on the collapsed nodes
    assert h_pl[0]['P1'][('E2', 'SCORE')] == 1.0
    assert h_pl[1]['P1'][('D2', 'E2')] == 1.0
    assert a_pl[0] == {}


def test_accumulate_away_chain_rotated():
    """Away SCORE chain (direct shot from E2) lands in home pos as
    A2->SCORE (rotated) at -1; in away pos as E2->SCORE at +1."""
    h_pos, a_pos, h_pl, a_pl = accumulate_match_positions(
        [_chain('AWAY', ['E2'])], 'HOME', 'AWAY')
    assert h_pos[0][TransitionEdge('A2', 'SCORE')] == -1.0
    assert a_pos[0][TransitionEdge('E2', 'SCORE')] == 1.0
    assert h_pl[0] == {}
    assert a_pl[0]['P1'][('E2', 'SCORE')] == 1.0


def test_accumulate_same_cell_collapses():
    """Consecutive same-cell events collapse: E2,E2 == E2 (single shot edge)."""
    h_pos_a, *_ = accumulate_match_positions(
        [_chain('HOME', ['E2', 'E2'])], 'HOME', 'AWAY')
    h_pos_b, *_ = accumulate_match_positions(
        [_chain('HOME', ['E2'])], 'HOME', 'AWAY')
    assert h_pos_a[0] == h_pos_b[0]
    assert h_pos_a[0][TransitionEdge('E2', 'SCORE')] == 1.0


def test_accumulate_depth_cap():
    """Chains longer than POSITIONS lump the tail into the last bucket."""
    alt = ['C1', 'C2'] * 15   # 30 edges + shot = 31; depths 0..30
    h_pos, *_ = accumulate_match_positions([_chain('HOME', alt)], 'HOME', 'AWAY')
    assert any(v != 0 for v in h_pos[11].values())  # deepest bucket used
    # direct shot: single node -> single edge at depth 0
    h_pos2, *_ = accumulate_match_positions([_chain('HOME', ['E2'])], 'HOME', 'AWAY')
    assert h_pos2[0][TransitionEdge('E2', 'SCORE')] == 1.0
    assert all(len(p) == 0 for p in h_pos2[1:])


def test_accumulate_non_scoring_ignored():
    h_pos, *_ = accumulate_match_positions(
        [_chain('HOME', ['D2', 'E2'], outcome='STOPPAGE')], 'HOME', 'AWAY')
    assert all(len(p) == 0 for p in h_pos)


# ---------------------------------------------------------------- recombine

def test_recombine_decay_weights_and_e2():
    """Recombine: weight d by decay**d, then E2-normalize by sum(|v|)."""
    pos_list = [defaultdict(float), defaultdict(float), defaultdict(float)]
    pos_list[0][TransitionEdge('E2', 'SCORE')] = 2.0
    pos_list[2][TransitionEdge('C2', 'D2')] = 6.0
    mat = recombine(pos_list, decay=0.5)
    raw = {TransitionEdge('E2', 'SCORE'): 2.0 * 0.5 ** 0,
           TransitionEdge('C2', 'D2'): 6.0 * 0.5 ** 2}
    total = sum(abs(v) for v in raw.values())
    assert mat[TransitionEdge('E2', 'SCORE')] == pytest.approx(2.0 / total)
    assert mat[TransitionEdge('C2', 'D2')] == pytest.approx(1.5 / total)


def test_recombine_empty():
    assert recombine([defaultdict(float)], 0.5) == {}


# ---------------------------------------------------------------- bake

def test_bake_players_decay():
    player_pos = [defaultdict(dict), defaultdict(dict)]
    player_pos[0]['P1'][('E2', 'SCORE')] = 2.0
    player_pos[1]['P1'][('D2', 'E2')] = 4.0
    baked = bake_players(player_pos, 0.5)
    assert baked['P1'][TransitionEdge('E2', 'SCORE')] == 2.0
    assert baked['P1'][TransitionEdge('D2', 'E2')] == pytest.approx(2.0)


# ---------------------------------------------------------------- fit_decay

def test_fit_decay_picks_best():
    """Two matches, one positive-edge home, one negative-edge home; decay must
    pick the candidate whose sign agreement is highest."""
    edge = TransitionEdge('E2', 'SCORE')
    # match 1: home won; match 2: away won (home lost)
    match_positions = {
        'M1': ([defaultdict(float), defaultdict(float)], [defaultdict(float), defaultdict(float)]),
        'M2': ([defaultdict(float), defaultdict(float)], [defaultdict(float), defaultdict(float)]),
    }
    match_positions['M1'][0][0][edge] = 1.0
    match_positions['M1'][1][0][edge] = 0.0
    match_positions['M2'][0][0][edge] = -1.0   # away-favouring net delta
    match_positions['M2'][1][0][edge] = 0.5
    info = {'M1': _MI('HOME', 'AWAY'), 'M2': _MI('HOME', 'AWAY')}
    winners = {'M1': 'HOME', 'M2': 'AWAY'}
    best, acc = fit_decay(match_positions, info, winners, candidates=(0.5,))
    assert best == 0.5 and acc == 1.0


def _MI(home, away, season=2021, round_num=1, hs=10, as_=5):
    from Core.models import MatchInfo
    mi = MatchInfo(season=season, round=round_num, home=home, away=away)
    mi.match_id = 'X'
    mi.home_score, mi.away_score = hs, as_
    return mi


# ---------------------------------------------------------------- fit rows

def test_build_fit_rows_shape_and_exclusions():
    match_info = {'M1': _MI('HOME', 'AWAY', hs=90, as_=80),
                  'POST_1': _MI('HOME', 'AWAY')}
    elo_hist = {'HOME': [('M1', 1500.0)], 'AWAY': [('M1', 1500.0)]}
    perf = {'M1': {'expected': 0.3, 'expected_delta': {}, 'actual': 0.2}}
    rows = build_fit_rows(match_info, elo_hist, perf)
    assert len(rows) == 1
    season, rnd, exp, ediff, margin, total, actual, m_id, h, a = rows[0]
    assert (season, rnd, exp, ediff, margin, total, actual, m_id, h, a) == \
        (2021, 1, 0.3, 0.0, 10, 170, 0.2, 'M1', 'HOME', 'AWAY')


def test_build_fit_rows_excludes_unplayed_and_post():
    match_info = {'M1': _MI('HOME', 'AWAY', hs=0, as_=0),   # unplayed
                  'POST_1': _MI('HOME', 'AWAY', hs=90, as_=80)}
    elo_hist = {}
    rows = build_fit_rows(match_info, elo_hist, {})
    assert rows == []


# ---------------------------------------------------------------- calibration

def test_fit_calibration_sets_cutoffs_and_coefficients():
    rows = [(2021, r, 0.2, 0.0, 10, 170, 0.2, f'M{r}', 'HOME', 'AWAY') for r in range(1, 25)]
    # 18 teams so compute_tier_cutoffs returns the full 3 midpoints
    elo_hist = {f'T{i}': [('POST_X', 1300.0 + 20 * i)] for i in range(18)}
    c = fit_calibration(rows, elo_hist, window_seasons=None)
    assert c.margin_b1 > 0 and abs(c.margin_b2) < 100
    assert len(c.tier_cutoffs) == 3
    assert c.tier_cutoffs[0] > c.tier_cutoffs[1] > c.tier_cutoffs[2]


def test_fit_calibration_empty_rows_fallback():
    c = fit_calibration([], {}, window_seasons=None)
    assert c.decay_factor == 0.3  # the SHIPPED fallback (not 0.5 — verified)
