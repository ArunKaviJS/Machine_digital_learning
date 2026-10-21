"""Speech-driven animation: emote commands, moods, SVG motion, motion paths."""

from __future__ import annotations

import pytest

from backend.config import VALID_ANIMATIONS
from backend.router.emotes import EMOTES, VALID_MOTIONS, apply_mood, match_emote
from client.animation import VALID_ANIMATIONS as CLIENT_ANIMATIONS
from client.placeholder_svg import _POSES, character_svg
from client.walk_area import motion_targets


@pytest.mark.parametrize("text, anim, motion", [
    ("dance", "dance", None),
    ("Bro can you do a little dance for me?", "dance", None),
    ("show me your dance moves", "dance", None),
    ("jump!", "jump", None),
    ("do a spin", "spin", None),
    ("turn around", "spin", None),
    ("make me laugh", None, None),  # not a pure body command
    ("come here bro", "run", "to_cursor"),
    ("go left", "walk", "left"),
    ("walk right please", "walk", "right"),
    ("walk around", "run", "roam"),
    ("go home", "walk", "home"),
    ("take a nap", "sleep", None),
])
def test_match_emote(text, anim, motion):
    got = match_emote(text)
    if anim is None:
        assert got is None
    else:
        assert got["animation"] == anim and got["motion"] == motion and got["text"]


@pytest.mark.parametrize("text", [
    "open notepad and write how to dance", "how much youtube today",
    "close chrome", "jump to settings and turn on night light",
])
def test_real_commands_are_not_emotes(text):
    assert match_emote(text) is None


def test_moods_only_replace_neutral_poses():
    assert apply_mood("tell me a joke", "answering") == "laugh"
    assert apply_mood("thank you bro", "smile") == "happy"
    assert apply_mood("I'm so tired today", "answering") == "sad"
    assert apply_mood("love you bro", "idle") == "love"
    assert apply_mood("tell me a joke", "warn") == "warn"
    assert apply_mood("what time is it", "answering") == "answering"


def test_every_emote_animation_is_known_and_drawn():
    for _, anim, motion, _ in EMOTES:
        assert anim in VALID_ANIMATIONS and anim in CLIENT_ANIMATIONS and anim in _POSES
        assert motion is None or motion in VALID_MOTIONS
    assert set(VALID_ANIMATIONS) == set(CLIENT_ANIMATIONS)


@pytest.mark.parametrize("pose", ["dance", "jump", "spin", "laugh", "nod", "shake", "run"])
def test_body_poses_actually_move(pose):
    frames = {character_svg(pose, f) for f in range(8)}
    assert len(frames) > 2


def test_motion_targets_clamped():
    bounds = (0, 0, 1000, 600)
    assert motion_targets("left", 100, 300, bounds, (0, 0), (900, 600), 160, 220) == [(0, 300)]
    assert motion_targets("right", 900, 300, bounds, (0, 0), (900, 600), 160, 220) == [(1000, 300)]
    assert motion_targets("to_cursor", 0, 0, bounds, (500, 400), (900, 600), 160, 220) \
        == [(420, 290)]
    roam = motion_targets("roam", 10, 20, bounds, (0, 0), (900, 600), 160, 220)
    assert len(roam) == 4 and roam[-1] == (10, 20)
    assert motion_targets("bogus", 0, 0, bounds, (0, 0), (0, 0), 1, 1) == []


def test_ask_endpoint_returns_emote_and_motion(client):
    r = client.post("/ask", json={"text": "come here"}).json()
    assert r["animation"] == "run" and r["data"]["motion"] == "to_cursor"
