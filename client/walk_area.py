"""Pure walking/roaming math (SKILL §20): bounds + step/bounce + 2D wander.

No Qt imports here so this is trivially unit-testable; character_window.py
feeds it a QScreen's availableGeometry() as plain ints.
"""

from __future__ import annotations

import random


def floor_y(work_area_top: int, work_area_bottom: int, char_height: int) -> int:
    """Y of the character's top-left so its feet rest on the work-area floor."""
    return max(work_area_top, work_area_bottom - char_height)


def walk_bounds(work_area_left: int, work_area_right: int, char_width: int) -> tuple[int, int]:
    """Min/max x for the character's left edge within the work area."""
    min_x = work_area_left
    max_x = max(work_area_left, work_area_right - char_width)
    return min_x, max_x


def step(x: float, facing_right: bool, speed: float, min_x: int, max_x: int) -> tuple[float, bool]:
    """Advance x by one tick; bounce (and flip facing) at either edge."""
    new_x = x + (speed if facing_right else -speed)
    if new_x >= max_x:
        return float(max_x), False
    if new_x <= min_x:
        return float(min_x), True
    return new_x, facing_right


def roam_bounds(
    work_area_left: int, work_area_top: int, work_area_right: int, work_area_bottom: int,
    char_width: int, char_height: int,
) -> tuple[int, int, int, int]:
    """Min/max x/y for the character's top-left anywhere in the work area."""
    min_x = work_area_left
    max_x = max(work_area_left, work_area_right - char_width)
    min_y = work_area_top
    max_y = max(work_area_top, work_area_bottom - char_height)
    return min_x, min_y, max_x, max_y


def random_target(min_x: int, min_y: int, max_x: int, max_y: int) -> tuple[float, float]:
    """A random point anywhere within the roam bounds (desktop-wide wander)."""
    return float(random.randint(min_x, max_x)), float(random.randint(min_y, max_y))


def step_toward(
    x: float, y: float, target_x: float, target_y: float, speed: float,
) -> tuple[float, float, bool, bool]:
    """Advance one tick toward (target_x, target_y). Returns (x, y, facing_right, arrived).

    `arrived` is True once within `speed` of the target on both axes, so the
    caller can pick a fresh random target and keep roaming.
    """
    dx = target_x - x
    dy = target_y - y
    dist = (dx * dx + dy * dy) ** 0.5
    if dist <= speed:
        return target_x, target_y, (dx >= 0), True
    new_x = x + speed * dx / dist
    new_y = y + speed * dy / dist
    return new_x, new_y, (dx >= 0), False
