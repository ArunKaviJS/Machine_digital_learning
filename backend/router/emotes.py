"""Speech-driven animation: what the user says decides how Bro moves.

Two tables, no I/O, no AI:
- EMOTES: the whole message is a body command ("dance", "jump", "come here",
  "go left") -> instant reply + animation (+ an on-screen `motion` the client
  performs by moving the character window).
- MOODS: words anywhere in the message ("thanks", "joke", "I'm sad") colour a
  plain reply's animation, e.g. a joke answer plays `laugh` not `answering`.
"""

from __future__ import annotations

import re
from typing import Any

from backend.router.rules import normalise

# softeners in front of a body command: "can you dance", "show me a spin"
_LEAD = (r"(?:(?:can|could|will|would) you |please |now |just |lets |let s |"
         r"show me |let me see |i want to see |)"
         r"(?:(?:do|show me|give me|make) )?(?:a |an |some |your |little |quick |)*")
_TAIL = r"(?: for me| please| now| again| bro| buddy| around)*"

# (pattern on normalised text, animation, motion, reply)
EMOTES: list[tuple[str, str, str | None, str]] = [
    (r"(?:dance|dancing|dance move|dance moves|boogie|groove)", "dance", None,
     "Watch these moves, bro! 💃"),
    (r"(?:jump|jumps|hop|jumping)", "jump", None, "Boing! 🦘"),
    (r"(?:spin|spins|turn around|twirl|backflip|flip)", "spin", None, "Wheee! 🌀"),
    (r"(?:laugh|lol|haha+|hehe+|smile)", "laugh", None, "Hahaha! 😂"),
    (r"(?:wave|say hi|say hello|wave at me)", "wave", None, "Hey hey! 👋"),
    (r"(?:nod|nod yes|say yes)", "nod", None, "Yes yes, bro."),
    (r"(?:shake your head|say no)", "shake", None, "Nope nope nope."),
    (r"(?:sleep|go to sleep|take a nap|nap|rest)", "sleep", None, "Zzz… wake me when you need me."),
    (r"(?:cry|be sad|sad face)", "sad", None, "*sniff* 😢"),
    (r"(?:heart|love|send love|blow a kiss)", "love", None, "Love you too, bro! 💙"),
    (r"(?:come here|come to me|come closer|follow me|follow my mouse)", "run", "to_cursor",
     "Coming, bro!"),
    (r"(?:go|walk|move|run) left", "walk", "left", "Going left!"),
    (r"(?:go|walk|move|run) right", "walk", "right", "Going right!"),
    (r"(?:walk|walk around|move|move around|run|run around|roam|explore)", "run", "roam",
     "Stretching my legs!"),
    (r"(?:go home|go back|go to your corner|go to the corner)", "walk", "home",
     "Back to my corner."),
]
_EMOTE_RES = [(re.compile(rf"{_LEAD}{pat}{_TAIL}"), anim, motion, reply)
              for pat, anim, motion, reply in EMOTES]

# (pattern anywhere in the raw lowercase text, animation) — first match wins
MOODS: list[tuple[str, str]] = [
    (r"\b(?:joke|jokes|funny|laugh|lol|lmao|haha+|hehe+|meme|cheer me up)\b", "laugh"),
    (r"\b(?:sad|upset|lonely|depressed|crying|bad day|tired|exhausted|bored)\b", "sad"),
    (r"\b(?:love you|you(?: a|')?re the best|you are the best|best bro|good boy|cute)\b", "love"),
    (r"\b(?:thanks|thank you|thx|good job|well done|great|awesome|nice|cool|wow)\b", "happy"),
    (r"\b(?:party|celebrate|let'?s go|yay|woo+)\b", "dance"),
]
_MOOD_RES = [(re.compile(p), anim) for p, anim in MOODS]

# a mood only replaces these neutral reply poses, never warn/angry/success…
NEUTRAL_POSES = {"answering", "idle", "smile", "happy", "greeting"}

VALID_MOTIONS = {"left", "right", "to_cursor", "roam", "home"}


def match_emote(text: str) -> dict[str, Any] | None:
    """A pure body command -> {text, animation, motion}, else None."""
    norm = normalise(text)
    if not norm or len(norm.split()) > 8:
        return None
    for regex, anim, motion, reply in _EMOTE_RES:
        if regex.fullmatch(norm):
            return {"text": reply, "animation": anim, "motion": motion}
    return None


def mood_animation(text: str) -> str | None:
    """Mood suggested by the user's words, or None."""
    low = text.lower()
    for regex, anim in _MOOD_RES:
        if regex.search(low):
            return anim
    return None


def apply_mood(text: str, animation: str) -> str:
    """Swap a neutral reply pose for the user's mood (jokes -> laugh…)."""
    if animation in NEUTRAL_POSES:
        return mood_animation(text) or animation
    return animation
