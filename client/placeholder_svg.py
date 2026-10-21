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
PAW_TIP = (193.0, 33.0)  # where the pressing hand touches (press pose)
_CYCLE = ANIMATION_CYCLE

# expression/pose tweaks: (left_brow_dy, right_brow_dy, mouth_path, arm_key)
_BROW_FLAT = (0, 0)
_BROW_RAISED = (-4, -4)
_BROW_ANGRY = (3, 3)
_BROW_SAD = (5, 5)

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
_ARMS_DANCE = "dance"
_ARMS_UP = "up"
_ARMS_DOWN = "down"
_ARMS_REACH = "reach"   # paw stretched up-right toward a button
_ARMS_PRESS = "press"   # paw pushing the button (tip at PAW_TIP)

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
    # speech-driven body animations (backend/router/emotes.py)
    "dance":     (_BROW_RAISED, _MOUTH_BIG_SMILE, _ARMS_DANCE),
    "jump":      (_BROW_RAISED, _MOUTH_O, _ARMS_UP),
    "spin":      (_BROW_RAISED, _MOUTH_BIG_SMILE, _ARMS_UP),
    "laugh":     (_BROW_RAISED, _MOUTH_BIG_SMILE, _ARMS_SIDES),
    "sad":       (_BROW_SAD, _MOUTH_FROWN, _ARMS_DOWN),
    "love":      (_BROW_RAISED, _MOUTH_BIG_SMILE, _ARMS_SIDES),
    "nod":       (_BROW_FLAT, _MOUTH_SMILE, _ARMS_SIDES),
    "shake":     (_BROW_ANGRY, _MOUTH_FLAT, _ARMS_SIDES),
    "run":       (_BROW_FLAT, _MOUTH_BIG_SMILE, _ARMS_SIDES),
    # walking to a window button and pressing it (client "character_act")
    "reach":     (_BROW_RAISED, _MOUTH_CLOSED, _ARMS_REACH),
    "press":     (_BROW_ANGRY, _MOUTH_CLOSED, _ARMS_PRESS),
}

# per-pose body motion over one cycle: (bounce_px, swing_px, extra) where
# extra picks a special move handled in _body_motion
_MOTION = {
    "walk": (8.0, 12.0, None), "run": (12.0, 18.0, None),
    "jump": (28.0, 0.0, None), "dance": (6.0, 10.0, "sway"),
    "spin": (6.0, 0.0, "spin"), "laugh": (5.0, 3.0, "fast"),
    "nod": (0.0, 2.0, "nod"), "shake": (0.0, 2.0, "shake"),
    "sad": (0.0, 1.0, "sag"), "love": (4.0, 4.0, None),
    "reach": (0.0, 0.0, None), "press": (0.0, 0.0, None),  # still: the paw does the work
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
    if key in (_ARMS_REACH, _ARMS_PRESS):  # droplet: right arm up to the corner
        tip = (186, 40) if key == _ARMS_PRESS else (176, 58)
        return (
            f'<path d="M 55,198 L 40,230" stroke="{DROP_BLUE_DARK}" stroke-width="10" '
            f'stroke-linecap="round"/>'
            f'<path d="M 145,195 L {tip[0]},{tip[1]}" stroke="{DROP_BLUE_DARK}" '
            f'stroke-width="10" stroke-linecap="round"/>'
            f'<circle cx="{tip[0]}" cy="{tip[1]}" r="10" fill="{DROP_BLUE}"/>'
        )
    if key in (_ARMS_DANCE, _ARMS_UP):
        # both hands up; dance alternates which one is higher
        lift = swing if key == _ARMS_DANCE else 0.0
        return (
            f'<path d="M 55,195 L 30,{150 + lift:.1f}" stroke="{DROP_BLUE_DARK}" '
            f'stroke-width="10" stroke-linecap="round"/>'
            f'<circle cx="28" cy="{143 + lift:.1f}" r="10" fill="{DROP_BLUE}"/>'
            f'<path d="M 145,195 L 170,{150 - lift:.1f}" stroke="{DROP_BLUE_DARK}" '
            f'stroke-width="10" stroke-linecap="round"/>'
            f'<circle cx="172" cy="{143 - lift:.1f}" r="10" fill="{DROP_BLUE}"/>'
        )
    if key == _ARMS_DOWN:
        return (
            f'<path d="M 58,200 L 52,240" stroke="{DROP_BLUE_DARK}" stroke-width="10" '
            f'stroke-linecap="round"/>'
            f'<path d="M 142,200 L 148,240" stroke="{DROP_BLUE_DARK}" stroke-width="10" '
            f'stroke-linecap="round"/>'
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
    phase = (frame % _CYCLE) / _CYCLE * 2 * math.pi
    transform, swing = _body_motion(pose, phase)
    eye = _eyes(pose)
    if pose == "sad":  # a tear under the left eye
        eye += '<path d="M 86,210 q -4,8 0,12 q 4,-4 0,-12 Z" fill="#ffffff" stroke="#1f4a85" stroke-width="1.5"/>'
    arms = _arms(arm_key, swing)
    return f'''<svg viewBox="0 0 200 300" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="100" cy="286" rx="45" ry="8" fill="#000000" opacity="0.08"/>
  <g transform="{transform}">
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


def _body_motion(pose: str, phase: float) -> tuple[str, float]:
    """SVG transform for the body at `phase`, plus the arm swing."""
    bounce_px, swing_px, extra = _MOTION.get(pose, (3.0, 5.0, None))
    swing = math.sin(phase) * swing_px
    if extra == "fast":  # laugh: quick double-time giggle
        bounce = abs(math.sin(phase * 2)) * bounce_px
    else:
        bounce = abs(math.sin(phase)) * bounce_px
    if extra == "sway":  # dance: side to side + tilt around the feet
        dx, angle = math.sin(phase) * 10, math.sin(phase) * 12
        return f"translate({dx:.1f},{-bounce:.1f}) rotate({angle:.1f} 100 290)", swing
    if extra == "spin":  # turn around: squash horizontally through a full turn
        sx = math.cos(phase)
        sx = math.copysign(max(abs(sx), 0.08), sx)
        return (f"translate(100,{-bounce:.1f}) scale({sx:.2f},1) translate(-100,0)",
                swing)
    if extra == "nod":
        return f"translate(0,{abs(math.sin(phase * 2)) * 6:.1f})", swing
    if extra == "shake":
        return f"translate({math.sin(phase * 2) * 8:.1f},0)", swing
    if extra == "sag":
        return "translate(0,6) scale(1,0.98)", swing
    return f"translate(0,{-bounce:.1f})", swing


def _eyes(pose: str) -> str:
    if pose == "sleep":
        return ('<line x1="84" y1="198" x2="94" y2="198" stroke="#1f4a85" stroke-width="3"/>'
                '<line x1="106" y1="198" x2="116" y2="198" stroke="#1f4a85" stroke-width="3"/>')
    if pose == "laugh":  # happy squint ^ ^
        return ('<path d="M 82,200 L 89,191 L 96,200" stroke="#1f4a85" stroke-width="3" fill="none"/>'
                '<path d="M 104,200 L 111,191 L 118,200" stroke="#1f4a85" stroke-width="3" fill="none"/>')
    if pose == "love":  # heart eyes
        heart = ('<path d="M {x},202 l -8,-8 a 4.5,4.5 0 0,1 8,-5 a 4.5,4.5 0 0,1 8,5 Z" '
                 'fill="#e8436b"/>')
        return heart.format(x=89) + heart.format(x=111)
    return ('<ellipse cx="89" cy="195" rx="9" ry="11" fill="#ffffff"/>'
            '<ellipse cx="111" cy="195" rx="9" ry="11" fill="#ffffff"/>'
            '<circle cx="89" cy="198" r="5" fill="#1f4a85"/>'
            '<circle cx="111" cy="198" r="5" fill="#1f4a85"/>')
