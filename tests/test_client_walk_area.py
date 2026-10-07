"""walk_area.py: pure floor/bounds/step math (SKILL §20)."""

from __future__ import annotations

from client.walk_area import floor_y, step, walk_bounds


def test_floor_y_rests_feet_on_bottom():
    assert floor_y(work_area_top=0, work_area_bottom=1040, char_height=220) == 820


def test_floor_y_clamped_when_char_taller_than_area():
    assert floor_y(work_area_top=100, work_area_bottom=150, char_height=220) == 100


def test_walk_bounds_within_work_area():
    min_x, max_x = walk_bounds(work_area_left=0, work_area_right=1920, char_width=160)
    assert min_x == 0
    assert max_x == 1760


def test_walk_bounds_clamped_when_char_wider_than_area():
    min_x, max_x = walk_bounds(work_area_left=0, work_area_right=100, char_width=160)
    assert min_x == 0 and max_x == 0


def test_step_moves_right_when_facing_right():
    x, facing = step(100.0, True, 5.0, min_x=0, max_x=500)
    assert x == 105.0 and facing is True


def test_step_moves_left_when_facing_left():
    x, facing = step(100.0, False, 5.0, min_x=0, max_x=500)
    assert x == 95.0 and facing is False


def test_step_bounces_at_right_edge():
    x, facing = step(498.0, True, 5.0, min_x=0, max_x=500)
    assert x == 500.0 and facing is False


def test_step_bounces_at_left_edge():
    x, facing = step(2.0, False, 5.0, min_x=0, max_x=500)
    assert x == 0.0 and facing is True
