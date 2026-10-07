"""placeholder_svg.py: pure SVG string generation, no Qt needed."""

from __future__ import annotations

from client.placeholder_svg import _POSES, character_svg


def test_returns_valid_svg_wrapper():
    svg = character_svg("idle")
    assert svg.strip().startswith("<svg")
    assert svg.strip().endswith("</svg>")


def test_every_known_pose_produces_distinct_or_valid_svg():
    for pose in _POSES:
        svg = character_svg(pose)
        assert "<svg" in svg and "viewBox" in svg


def test_unknown_pose_falls_back_to_idle_expression():
    assert character_svg("totally-made-up-pose") == character_svg("idle")


def test_sleep_pose_draws_closed_eyes_not_open_circles():
    sleep_svg = character_svg("sleep")
    idle_svg = character_svg("idle")
    assert "circle cx=\"89\"" in idle_svg  # open eye pupil
    assert "circle cx=\"89\"" not in sleep_svg  # closed eye uses a line instead


def test_angry_and_happy_produce_different_mouths():
    assert character_svg("angry") != character_svg("happy")
