"""Procedural SVG placeholder character: the "Bro" water-droplet mascot
(bro-desktop-companion-guide.pdf, need-to-do.md §E / CONTEXT.md D17).

A simple stylized blue teardrop with a face and two thin arms, matching the
guide's reference character, so the desktop companion reads as Bro before
real Kling-generated artwork is imported. Pure string generation -> trivially
testable without Qt; rendered via QSvgRenderer.
"""

from __future__ import annotations

import math

ANIMATION_CYCLE = 8  # frames per animation loop (bounce / arm-swing)
_CYCLE = ANIMATION_CYCLE

# expression/pose tweaks: (left_brow_dy, right_brow_dy, mouth_path, arm_key)
_BROW_FLAT = (0, 0)
_BROW_RAISED = (-4, -4)
_BROW_ANGRY = (3, 3)

_MOUTH_SMILE = "M 80,224 Q 100,236 120,224"
_MOUTH_BIG_SMILE = "M 76,222 Q 100,244 124,222"
_MOUTH_FLAT = "M 82,228 L 118,228"
_MOUTH_FROWN = "M 80,232 Q 100,220 120,232"
_MOUTH_O = "M 92,220 a 8,8 0 1,0 16,0 a 8,8 0 1,0 -16,0"
_MOUTH_CLOSED = "M 84,226 Q 100,230 116,226"

_ARMS_SIDES = "sides"
_ARMS_WAVE = "wave"
_ARMS_CROSSED = "crossed"
_ARMS_THINKING = "thinking"

_POSES = {
    "idle":      (_BROW_FLAT, _MOUTH_SMILE, _ARMS_SIDES),
    "walk":      (_BROW_FLAT, _MOUTH_SMILE, _ARMS_SIDES),
    "greeting":  (_BROW_RAISED, _MOUTH_BIG_SMILE, _ARMS_WAVE),
    "wave":      (_BROW_RAISED, _MOUTH_BIG_SMILE, _ARMS_WAVE),
    "smile":     (_BROW_FLAT, _MOUTH_SMILE, _ARMS_SIDES),
    "happy":     (_BROW_RAISED, _MOUTH_BIG_SMILE, _ARMS_WAVE),
    "success":   (_BROW_RAISED, _MOUTH_BIG_SMILE, _ARMS_WAVE),
    "water":     (_BROW_FLAT, _MOUTH_SMILE, _ARMS_THINKING),
    "warn":      (_BROW_ANGRY, _MOUTH_FLAT, _ARMS_CROSSED),
    "angry":     (_BROW_ANGRY, _MOUTH_FROWN, _ARMS_CROSSED),
    "thinking":  (_BROW_RAISED, _MOUTH_CLOSED, _ARMS_THINKING),
    "working":   (_BROW_FLAT, _MOUTH_CLOSED, _ARMS_THINKING),
    "answering": (_BROW_FLAT, _MOUTH_SMILE, _ARMS_SIDES),
    "confused":  (_BROW_RAISED, _MOUTH_O, _ARMS_SIDES),
    "sleep":     (_BROW_FLAT, _MOUTH_FLAT, _ARMS_SIDES),
}

DROP_BLUE = "#4a90e2"
DROP_BLUE_DARK = "#2f6fc9"
DROP_HIGHLIGHT = "#bfe0ff"
CHEEK = "#ff9db3"
OUTLINE = "#1f4a85"


def _arms(key: str, swing: float) -> str:
    """Two thin arm strokes with a round hand, positioned by `key`/`swing`."""
    if key == _ARMS_WAVE:
        return (
            f'<path d="M 55,195 L 38,225" stroke="{DROP_BLUE_DARK}" stroke-width="10" '
            f'stroke-linecap="round"/>'
            f'<path d="M 145,195 L {170 - swing:.1f},{150 + swing * 0.3:.1f}" '
            f'stroke="{DROP_BLUE_DARK}" stroke-width="10" stroke-linecap="round"/>'
            f'<circle cx="{172 - swing:.1f}" cy="{143 + swing * 0.3:.1f}" r="10" fill="{DROP_BLUE}"/>'
        )
    if key == _ARMS_CROSSED:
        return (
            f'<path d="M 55,198 L 130,220" stroke="{DROP_BLUE_DARK}" stroke-width="10" '
            f'stroke-linecap="round"/>'
            f'<path d="M 145,198 L 70,220" stroke="{DROP_BLUE_DARK}" stroke-width="10" '
            f'stroke-linecap="round"/>'
        )
    if key == _ARMS_THINKING:
        return (
            f'<path d="M 55,198 L 40,230" stroke="{DROP_BLUE_DARK}" stroke-width="10" '
            f'stroke-linecap="round"/>'
            f'<path d="M 145,198 L 118,170" stroke="{DROP_BLUE_DARK}" stroke-width="10" '
            f'stroke-linecap="round"/>'
        )
    # sides / walk: both arms swing gently opposite each other
    return (
        f'<path d="M {55 + swing:.1f},198 L {40 + swing:.1f},232" '
        f'stroke="{DROP_BLUE_DARK}" stroke-width="10" stroke-linecap="round"/>'
        f'<path d="M {145 - swing:.1f},198 L {160 - swing:.1f},232" '
        f'stroke="{DROP_BLUE_DARK}" stroke-width="10" stroke-linecap="round"/>'
    )


def character_svg(pose: str, frame: int = 0) -> str:
    """Full-body water-droplet mascot for `pose` at animation `frame` (any
    pose string; unknown poses fall back to idle's expression). A looping
    bounce/arm-swing cycle driven by `frame` keeps the placeholder animated
    instead of a still image."""
    (ldy, rdy), mouth, arm_key = _POSES.get(pose, _POSES["idle"])
    is_walking = pose == "walk"
    phase = (frame % _CYCLE) / _CYCLE * 2 * math.pi
    bounce = abs(math.sin(phase)) * (8.0 if is_walking else 3.0)
    swing = math.sin(phase) * (12.0 if is_walking else 5.0)

    eyes_closed = pose == "sleep"
    eye = (
        '<line x1="84" y1="198" x2="94" y2="198" stroke="#1f4a85" stroke-width="3"/>'
        '<line x1="106" y1="198" x2="116" y2="198" stroke="#1f4a85" stroke-width="3"/>'
        if eyes_closed else
        '<ellipse cx="89" cy="195" rx="9" ry="11" fill="#ffffff"/>'
        '<ellipse cx="111" cy="195" rx="9" ry="11" fill="#ffffff"/>'
        '<circle cx="89" cy="198" r="5" fill="#1f4a85"/>'
        '<circle cx="111" cy="198" r="5" fill="#1f4a85"/>'
    )
    arms = _arms(arm_key, swing)
    return f'''<svg viewBox="0 0 200 300" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="100" cy="286" rx="45" ry="8" fill="#000000" opacity="0.08"/>
  <g transform="translate(0,{-bounce:.1f})">
  <path d="M 100,30 C 60,115 38,168 38,208 C 38,256 64,292 100,292 C 136,292 162,256 162,208
           C 162,168 140,115 100,30 Z" fill="{DROP_BLUE}" stroke="{OUTLINE}" stroke-width="3"/>
  <path d="M 62,120 C 50,155 44,180 46,205" fill="none" stroke="{DROP_HIGHLIGHT}"
        stroke-width="10" stroke-linecap="round" opacity="0.7"/>
  {arms}
  <path d="M 70,{166 + ldy} l 16,-4" stroke="{OUTLINE}" stroke-width="4" stroke-linecap="round"/>
  <path d="M 130,{166 + rdy} l -16,-4" stroke="{OUTLINE}" stroke-width="4" stroke-linecap="round"/>
  {eye}
  <ellipse cx="68" cy="218" rx="11" ry="7" fill="{CHEEK}" opacity="0.8"/>
  <ellipse cx="132" cy="218" rx="11" ry="7" fill="{CHEEK}" opacity="0.8"/>
  <path d="{mouth}" stroke="{OUTLINE}" stroke-width="3" fill="none" stroke-linecap="round"/>
  </g>
</svg>'''
