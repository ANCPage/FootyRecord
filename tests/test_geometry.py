"""Unit tests for Core/geometry.py — grid mapping and rotation (audit #20)."""
from geometry import xy_to_grid, rotate_node


def test_center_is_c2():
    assert xy_to_grid(0, 0, 170, 130) == 'C2'


def test_forward_goal_square_is_e_column():
    # Home team attacks +x; the goal square sits in the E column.
    assert xy_to_grid(70, 0, 170, 130) == 'E2'


def test_defensive_end_is_a_column():
    assert xy_to_grid(-70, 0, 170, 130) == 'A2'


def test_boundary_clamp_to_corner():
    # Way outside the oval clamps to a boundary corner zone, never errors.
    assert xy_to_grid(5000, 5000, 170, 130) == 'E3'
    assert xy_to_grid(-5000, 5000, 170, 130) == 'A3'


def test_invalid_inputs_return_empty():
    assert xy_to_grid('', '5', 170, 130) == ''
    assert xy_to_grid(None, None, 170, 130) == ''
    assert xy_to_grid(10, 10, None, None) == ''
    assert xy_to_grid('abc', 'def', 170, 130) == ''


def test_rotation_involutive():
    for c in 'ABCDE':
        for r in '123':
            assert rotate_node(rotate_node(f'{c}{r}')) == f'{c}{r}'


def test_rotation_mapping():
    assert rotate_node('A1') == 'E3'
    assert rotate_node('E2') == 'A2'
    assert rotate_node('C2') == 'C2'
    assert rotate_node('SCORE') == 'SCORE'
