"""Open sites/apps and close apps (SKILL §7 action handlers).

Apps are discovered dynamically from the OS (Start menu catalog: classic and
Store apps; running windows for close) and fuzzy-matched — nothing about
which apps exist is hard-coded. Closing is the polite WM_CLOSE (same as the
window's X), so apps still prompt to save; nothing is force-killed and no
admin rights are needed.
"""

from __future__ import annotations

import re
import time
import webbrowser
from difflib import SequenceMatcher
from typing import Any

from backend.os_integration.helpers import app_identity, process_label

APP_CACHE_SECONDS = 600.0
_cache: dict[str, Any] = {"at": 0.0, "apps": []}

# Start-menu entries that are rarely what "open X" means.
_NOISE = re.compile(r"\b(uninstall|readme|release notes|help|documentation|"
                    r"manual|website|license|changelog)\b")
_DOMAIN = re.compile(r"^(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?$", re.I)
# Typos ("whatsap", "notpad", "calculater") score >= 0.9; a *different* app
# sharing a prefix ("photoshop" vs "Photos") scores 0.8 — keep it out.
MIN_FUZZY_RATIO = 0.85


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _is_abbreviation(compact: str, words: list[str]) -> bool:
    """True if `compact` is a non-empty prefix of every word, in order:
    'vscode' = v(isual) s(tudio) code, 'msteams' = m(icro)s(oft) teams."""
    if len(words) < 2 or len(compact) < len(words):
        return False

    def match(i: int, w: int) -> bool:
        if w == len(words):
            return i == len(compact)
        word = words[w]
        for n in range(min(len(word), len(compact) - i), 0, -1):
            if compact[i:i + n] == word[:n] and match(i + n, w + 1):
                return True
        return False

    return match(0, 0)


def _score(query: str, name: str) -> float:
    q, n = _norm(query), _norm(name)
    if not q or not n:
        return 0.0
    q_words, n_words = q.split(), n.split()
    if n == q or n.replace(" ", "") == q.replace(" ", ""):
        score = 100.0
    elif all(w in n_words for w in q_words):
        score = 85.0 if n.startswith(q) else 80.0
    elif q in n:
        score = 70.0
    elif _is_abbreviation(q.replace(" ", ""), n_words):
        score = 65.0  # "vsc", "vscode", "vs code" -> Visual Studio Code
    else:
        ratio = SequenceMatcher(None, q, n).ratio()
        score = 60.0 * ratio if ratio >= MIN_FUZZY_RATIO else 0.0
    if score and _NOISE.search(n) and not _NOISE.search(q):
        score -= 30.0
    return score


_STOPWORDS = {
    "a", "an", "the", "my", "me", "to", "for", "please", "pls", "can", "could",
    "you", "would", "will", "i", "want", "need", "on", "in", "of", "up", "it",
    "that", "this", "app", "application", "program", "window", "open", "launch",
    "start", "run", "bring", "get", "rid", "close", "quit", "kill", "stop", "bro",
    "now", "with", "and", "just", "is", "do", "some", "friends", "message",
}
SENTENCE_MIN_SCORE = 65.0  # exact / whole-word / abbreviation — never fuzzy


def _ngrams(text: str, max_n: int = 4) -> set[str]:
    words = _norm(text).split()
    grams = set()
    for n in range(1, max_n + 1):
        for i in range(len(words) - n + 1):
            gram = words[i:i + n]
            if not all(w in _STOPWORDS for w in gram):
                grams.add(" ".join(gram))
    return grams


def best_app_in_text(text: str, apps: list[dict[str, str]]) -> dict[str, str] | None:
    """Find an installed app *mentioned somewhere* in a sentence ("bring my
    calculator" -> Calculator), for when the AI picked the intent but not the
    name. Fuzzy matches are excluded: a stray word must not launch an app."""
    best: tuple[tuple, dict] | None = None
    for gram in _ngrams(text):
        for app in apps:
            score = _score(gram, app["name"])
            if score < SENTENCE_MIN_SCORE:
                continue
            key = (score, len(gram), -len(app["name"]))
            if best is None or key > best[0]:
                best = (key, app)
    return best[1] if best else None


def best_app_match(query: str, apps: list[dict[str, str]]) -> dict[str, str] | None:
    """Best installed app for `query`, or None if nothing is a credible match.
    Ties go to the shorter name ("Settings" over "WSL Settings")."""
    best: tuple[float, int, dict] | None = None
    for app in apps:
        score = _score(query, app["name"])
        if score <= 0:
            continue
        key = (score, -len(app["name"]), app)
        if best is None or key[:2] > best[:2]:
            best = key
    return best[2] if best else None


class AppLauncherService:
    def __init__(self, os_adapter=None, clock=time.monotonic):
        self.os_adapter = os_adapter
        self.clock = clock

    def open_site(self, site: str) -> bool:
        url = site if site.startswith("http") else f"https://{site}"
        try:
            return webbrowser.open(url)
        except Exception:
            return False

    def installed_apps(self) -> list[dict[str, str]]:
        if self.os_adapter is None:
            return []
        if not _cache["apps"] or self.clock() - _cache["at"] > APP_CACHE_SECONDS:
            apps = self.os_adapter.list_apps()
            if apps:
                _cache.update(at=self.clock(), apps=apps)
            return apps
        return _cache["apps"]

    def open_app(self, query: str) -> dict[str, Any]:
        """{'status': opened|opened_url|not_found|error, 'query', 'name'}."""
        query = query.strip()
        apps = self.installed_apps()
        app = best_app_match(query, apps)
        if app is None and _DOMAIN.match(query):
            ok = self.open_site(query)
            return {"status": "opened_url" if ok else "error", "query": query,
                    "name": query}
        if app is None and len(query.split()) > 1:
            app = best_app_in_text(query, apps)
        if app is not None:
            ok = self.os_adapter.launch_app(app["app_id"])
            return {"status": "opened" if ok else "error", "query": query,
                    "name": app["name"]}
        return {"status": "not_found", "query": query, "name": None}

    def close_app(self, query: str) -> dict[str, Any]:
        """{'status': closed|not_running|error, 'query', 'name', 'count'}.
        Closes every window of the best-matching running app."""
        query = query.strip()
        windows = self.os_adapter.list_windows() if self.os_adapter else []
        scored = []
        for win in windows:
            score = _score(query, process_label(win["process_name"]))
            title_score = _score(query, win["title"])
            if title_score >= 80:  # whole-word title match only (Store apps)
                score = max(score, title_score)
            if score > 0:
                scored.append((score, win))
        if not scored and len(query.split()) > 1:
            # sentence fallback ("get rid of the whatsapp window"): process
            # names only (+ exact Store-app titles) — never loose title words
            grams = _ngrams(query)
            for win in windows:
                key, name = app_identity(win)
                label = name if key.startswith("title:") else process_label(win["process_name"])
                score = max((_score(g, label) for g in grams), default=0.0)
                if key.startswith("title:") and score < 100:
                    score = 0.0
                if score >= SENTENCE_MIN_SCORE:
                    scored.append((score, win))
        if not scored:
            return {"status": "not_running", "query": query, "name": None, "count": 0}
        top = max(score for score, _ in scored)
        targets = [win for score, win in scored if score == top]
        closed = sum(1 for win in targets if self.os_adapter.close_window(win["hwnd"]))
        return {"status": "closed" if closed else "error", "query": query,
                "name": app_identity(targets[0])[1], "count": closed}


def clear_app_cache() -> None:
    _cache.update(at=0.0, apps=[])
