"""hotkey.py: pure 'Ctrl+Alt+B' parsing (no hotkey is actually registered)."""

from __future__ import annotations

import pytest

from client.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, parse_hotkey


@pytest.mark.parametrize("text,expected", [
    ("Ctrl+Alt+B", (MOD_CONTROL | MOD_ALT, ord("B"))),
    ("ctrl + shift + 9", (MOD_CONTROL | MOD_SHIFT, ord("9"))),
    ("Win+F2", (MOD_WIN, 0x71)),
    ("Alt+Space", (MOD_ALT, 0x20)),
])
def test_parse_valid(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["", "B", "Ctrl+", "Hyper+B", "Ctrl+Alt+Enter", "Ctrl+F13"])
def test_parse_invalid(text):
    assert parse_hotkey(text) is None
