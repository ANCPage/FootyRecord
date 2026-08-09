"""Regression tests for the LFP->FB rendering fix (audit, Aug 2026).

Before the fix, away-owned edges in home-frame panels had their zone nodes
rotated a second time, mirroring every away arrow across the field. The
most visible symptom: Norf's RBP->SCORE (a short kick at the left end) was
drawn starting from the home LFP zone position, spanning the pitch — the
'impossible LFP->FB ball movement'.
"""
from engine_core import Graph, physical_placement


def test_away_scoring_edge_stays_at_own_zone():
    # FB->SCORE (away, home frame): the arrow must sit at the FB zone aiming
    # at the away goal. Old code mirrored it to FF->AWAY_G.
    assert physical_placement('A2', 'SCORE', is_away_edge=True, frame='home') \
        == ('A2', 'AWAY_G')


def test_phantom_lfp_arrow_regression():
    # The exact reported case: RBP->SCORE (away) used to be drawn LFP->AWAY_G.
    start, end = physical_placement('A3', 'SCORE', is_away_edge=True, frame='home')
    assert (start, end) == ('A3', 'AWAY_G')
    assert start != 'E1'  # must NOT start at the LFP zone position


def test_home_scoring_edge_unchanged():
    assert physical_placement('E2', 'SCORE', is_away_edge=False, frame='home') \
        == ('E2', 'SCORE')


def test_away_zone_edge_not_mirrored():
    # C->CHB (away) must stay at C->CHB; old code drew it C->CHF (pointing
    # the wrong way up the field).
    assert physical_placement('C2', 'B2', is_away_edge=True, frame='home') \
        == ('C2', 'B2')


def test_team_frame_own_move_rotated_with_goal_swap():
    # Away-team profile panel, own scoring edge: E2->SCORE (their FF->goal)
    # lands at A2->AWAY_G on the home-oriented field.
    assert physical_placement('E2', 'SCORE', is_away_edge=False, frame='team') \
        == ('A2', 'AWAY_G')


def test_team_frame_opponent_contribution_no_swap():
    # Away-team profile panel, opponent (home-team) contribution: A2->SCORE
    # (home FF->goal in away frame) lands at E2->SCORE — no goal swap.
    assert physical_placement('A2', 'SCORE', is_away_edge=True, frame='team') \
        == ('E2', 'SCORE')


def test_rotation_is_involutive():
    g = Graph("util")
    names = [f"{c}{r}" for c in "ABCDE" for r in "123"]
    for name in names:
        assert g.rotate_node(g.rotate_node(name)) == name
    assert g.rotate_node('SCORE') == 'SCORE'
