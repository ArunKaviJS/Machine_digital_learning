"""Procedural SVG cat: Bro's character (config `characterStyle: "cat"`).

Same pose names, expressions and body motion as the droplet
(client/placeholder_svg.py) so every animation works for both, drawn as an
orange tabby with ears, whiskers, a swaying tail and front paws used as
hands. `reach` / `press` stretch the right paw up to the top-right corner:
PAW_TIP is where the paw touches in SVG coordinates, so the client can
place the window so the paw lands exactly on a window's close/minimize
button. Pure string generation (testable without Qt).
"""

from __future__ import annotations

import math

from client.placeholder_svg import (_ARMS_CROSSED, _ARMS_DANCE, _ARMS_DOWN, _ARMS_PRESS,
                                    _ARMS_REACH, _ARMS_THINKING, _ARMS_UP, _ARMS_WAVE,
                                    _CYCLE, _MOUTH_BIG_SMILE, _MOUTH_CLOSED, _MOUTH_FLAT,
                                    _MOUTH_FROWN, _MOUTH_O, _POSES, _body_motion)

VIEW_W, VIEW_H = 200, 300
PAW_TIP = (196.0, 36.0)  # the pressing paw's touch point (press pose)

FUR = "#f2a65a"
FUR_DARK = "#d9822b"
BELLY = "#fff1dc"
OUTLINE = "#6b3e17"
INNER_EAR = "#f7b6c2"
EYE = "#4caf50"
NOSE = "#e8798f"
CHEEK = "#ff9db3"

_CAT_MOUTH = {
    _MOUTH_BIG_SMILE: ('<path d="M 88,168 Q 100,188 112,168 Z" fill="#8a2b3a" '
                       f'stroke="{OUTLINE}" stroke-width="2"/>'),
    _MOUTH_FLAT: f'<path d="M 90,172 L 110,172" stroke="{OUTLINE}" stroke-width="2.5"/>',
    _MOUTH_FROWN: (f'<path d="M 90,177 Q 100,168 110,177" fill="none" stroke="{OUTLINE}" '
                   'stroke-width="2.5"/>'),
    _MOUTH_O: f'<circle cx="100" cy="174" r="5" fill="#8a2b3a" stroke="{OUTLINE}" stroke-width="2"/>',
    _MOUTH_CLOSED: (f'<path d="M 92,171 Q 100,175 108,171" fill="none" stroke="{OUTLINE}" '
                    'stroke-width="2.5"/>'),
}
_SMILE = (f'<path d="M 100,166 Q 94,175 87,170 M 100,166 Q 106,175 113,170" fill="none" '
          f'stroke="{OUTLINE}" stroke-width="2.5" stroke-linecap="round"/>')


def _limb(x1: float, y1: float, x2: float, y2: float, squash: bool = False) -> str:
    """A furry front leg with a round paw at (x2, y2)."""
    paw = (f'<ellipse cx="{x2:.1f}" cy="{y2:.1f}" rx="11" ry="7" fill="{FUR}" '
           f'stroke="{OUTLINE}" stroke-width="2"/>' if squash else
           f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="9" fill="{FUR}" stroke="{OUTLINE}" '
           'stroke-width="2"/>')
    return (f'<path d="M {x1},{y1} L {x2:.1f},{y2:.1f}" stroke="{OUTLINE}" stroke-width="16" '
            f'stroke-linecap="round"/>'
            f'<path d="M {x1},{y1} L {x2:.1f},{y2:.1f}" stroke="{FUR}" stroke-width="12" '
            f'stroke-linecap="round"/>' + paw)


def _paws(key: str, swing: float) -> str:
    left_down = _limb(80, 205, 74, 262)
    if key == _ARMS_PRESS:   # paw pushed into the corner, squashed by the press
        return left_down + _limb(122, 203, PAW_TIP[0] - 6, PAW_TIP[1] + 6, squash=True)
    if key == _ARMS_REACH:
        return left_down + _limb(122, 203, 178, 64)
    if key == _ARMS_WAVE:
        return left_down + _limb(120, 205, 158 - swing, 150 + swing * 0.3)
    if key == _ARMS_CROSSED:
        return _limb(80, 205, 122, 228) + _limb(120, 205, 78, 228)
    if key == _ARMS_THINKING:
        return left_down + _limb(120, 205, 110, 182)
    if key in (_ARMS_DANCE, _ARMS_UP):
        lift = swing if key == _ARMS_DANCE else 0.0
        return _limb(80, 205, 44, 150 + lift) + _limb(120, 205, 156, 150 - lift)
    if key == _ARMS_DOWN:
        return _limb(82, 210, 80, 264) + _limb(118, 210, 120, 264)
    return _limb(80, 205, 74 + swing, 262) + _limb(120, 205, 126 - swing, 262)


def _eyes(pose: str) -> str:
    if pose == "sleep":
        return (f'<path d="M 73,149 Q 82,155 91,149" fill="none" stroke="{OUTLINE}" stroke-width="3"/>'
                f'<path d="M 109,149 Q 118,155 127,149" fill="none" stroke="{OUTLINE}" stroke-width="3"/>')
    if pose == "laugh":
        return (f'<path d="M 74,152 L 82,143 L 90,152" fill="none" stroke="{OUTLINE}" stroke-width="3"/>'
                f'<path d="M 110,152 L 118,143 L 126,152" fill="none" stroke="{OUTLINE}" stroke-width="3"/>')
    if pose == "love":
        heart = ('<path d="M {x},156 l -9,-9 a 5,5 0 0,1 9,-5 a 5,5 0 0,1 9,5 Z" '
                 'fill="#e8436b"/>')
        return heart.format(x=82) + heart.format(x=118)
    eyes = ""
    for cx in (82, 118):
        eyes += (f'<ellipse cx="{cx}" cy="148" rx="9" ry="11" fill="{EYE}" stroke="{OUTLINE}" '
                 f'stroke-width="2"/><ellipse cx="{cx}" cy="149" rx="3" ry="8" fill="#111"/>'
                 f'<circle cx="{cx + 3}" cy="144" r="2.2" fill="#fff"/>')
    if pose == "sad":
        eyes += (f'<path d="M 80,160 q -4,8 0,12 q 4,-4 0,-12 Z" fill="#ffffff" '
                 f'stroke="{OUTLINE}" stroke-width="1.5"/>')
    return eyes


def character_svg(pose: str, frame: int = 0) -> str:
    """Full-body cat for `pose` at animation `frame` (unknown pose -> idle)."""
    (ldy, rdy), mouth, arm_key = _POSES.get(pose, _POSES["idle"])
    phase = (frame % _CYCLE) / _CYCLE * 2 * math.pi
    transform, swing = _body_motion(pose, phase)
    step = swing * 0.5 if pose in ("walk", "run") else 0.0
    tail_sway = math.sin(phase) * 8
    whiskers = "".join(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{OUTLINE}" '
        'stroke-width="1.5" opacity="0.7"/>'
        for x1, y1, x2, y2 in ((76, 166, 44, 160), (76, 170, 42, 172), (76, 174, 46, 184),
                               (124, 166, 156, 160), (124, 170, 158, 172), (124, 174, 154, 184)))
    mouth_svg = _CAT_MOUTH.get(mouth, _SMILE)
    return f'''<svg viewBox="0 0 {VIEW_W} {VIEW_H}" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="100" cy="290" rx="50" ry="7" fill="#000000" opacity="0.10"/>
  <g transform="{transform}">
  <path d="M 140,262 C 178,256 {188 + tail_sway:.1f},218 {170 + tail_sway:.1f},188" fill="none"
        stroke="{OUTLINE}" stroke-width="15" stroke-linecap="round"/>
  <path d="M 140,262 C 178,256 {188 + tail_sway:.1f},218 {170 + tail_sway:.1f},188" fill="none"
        stroke="{FUR}" stroke-width="11" stroke-linecap="round"/>
  <ellipse cx="{78 + step:.1f}" cy="284" rx="15" ry="8" fill="{FUR}" stroke="{OUTLINE}" stroke-width="2"/>
  <ellipse cx="{122 - step:.1f}" cy="284" rx="15" ry="8" fill="{FUR}" stroke="{OUTLINE}" stroke-width="2"/>
  <ellipse cx="100" cy="238" rx="46" ry="44" fill="{FUR}" stroke="{OUTLINE}" stroke-width="3"/>
  <ellipse cx="100" cy="250" rx="26" ry="29" fill="{BELLY}"/>
  <polygon points="58,134 63,82 96,110" fill="{FUR}" stroke="{OUTLINE}" stroke-width="3"
           stroke-linejoin="round"/>
  <polygon points="66,124 68,96 88,112" fill="{INNER_EAR}"/>
  <polygon points="142,134 137,82 104,110" fill="{FUR}" stroke="{OUTLINE}" stroke-width="3"
           stroke-linejoin="round"/>
  <polygon points="134,124 132,96 112,112" fill="{INNER_EAR}"/>
  <circle cx="100" cy="150" r="46" fill="{FUR}" stroke="{OUTLINE}" stroke-width="3"/>
  <path d="M 100,107 L 100,121 M 88,109 L 91,121 M 112,109 L 109,121" stroke="{FUR_DARK}"
        stroke-width="4" stroke-linecap="round"/>
  <path d="M 72,{130 + ldy} l 16,-3" stroke="{OUTLINE}" stroke-width="3" stroke-linecap="round"/>
  <path d="M 128,{130 + rdy} l -16,-3" stroke="{OUTLINE}" stroke-width="3" stroke-linecap="round"/>
  {_eyes(pose)}
  <ellipse cx="70" cy="170" rx="9" ry="6" fill="{CHEEK}" opacity="0.6"/>
  <ellipse cx="130" cy="170" rx="9" ry="6" fill="{CHEEK}" opacity="0.6"/>
  <path d="M 95,160 L 105,160 L 100,166 Z" fill="{NOSE}"/>
  {mouth_svg}
  {whiskers}
  {_paws(arm_key, swing)}
  </g>
</svg>'''
