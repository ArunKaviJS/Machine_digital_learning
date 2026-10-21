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


MOTION_STEP_PX = 300   # "go left/right" distance
ROAM_STOPS = 3         # "walk around": this many random stops


def motion_targets(
    motion: str, x: float, y: float, bounds: tuple[int, int, int, int],
    cursor: tuple[int, int], home: tuple[float, float],
    char_width: int, char_height: int,
) -> list[tuple[float, float]]:
    """Waypoints for a spoken motion command (backend/router/emotes.py),
    clamped to the roam bounds. Unknown motion -> []."""
    min_x, min_y, max_x, max_y = bounds

    def clamp(px: float, py: float) -> tuple[float, float]:
        return (float(min(max(px, min_x), max_x)), float(min(max(py, min_y), max_y)))

    if motion == "left":
        return [clamp(x - MOTION_STEP_PX, y)]
    if motion == "right":
        return [clamp(x + MOTION_STEP_PX, y)]
    if motion == "to_cursor":  # stand just beside the mouse pointer
        return [clamp(cursor[0] - char_width // 2, cursor[1] - char_height // 2)]
    if motion == "home":
        return [clamp(*home)]
    if motion == "roam":
        return [random_target(min_x, min_y, max_x, max_y) for _ in range(ROAM_STOPS)] \
            + [clamp(x, y)]
    return []


def physical_to_logical(x: float, y: float,
                        screens: list[tuple[int, int, int, int, float]]) -> tuple[float, float]:
    """Windows reports button positions in physical pixels; Qt places
    windows in logical ones. `screens` = (left, top, width, height, dpr) in
    Qt units; Qt keeps each screen's top-left at its native position and
    scales from there (125 %: physical 1888 -> logical 1510.4)."""
    for left, top, width, height, dpr in screens:
        if left <= x < left + width * dpr and top <= y < top + height * dpr:
            return left + (x - left) / dpr, top + (y - top) / dpr
    if screens:  # off every screen: use the first (primary) one's scale
        left, top, _w, _h, dpr = screens[0]
        return left + (x - left) / dpr, top + (y - top) / dpr
    return float(x), float(y)


def paw_window_target(button: tuple[float, float], paw_offset: tuple[float, float]
                      ) -> tuple[float, float]:
    """Top-left for the character window so its paw tip lands on `button`."""
    return button[0] - paw_offset[0], button[1] - paw_offset[1]
