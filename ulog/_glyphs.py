"""Locale-aware glyph fallback for CLI output (Story 6.9 / NFR-PORT-50).

On UTF-8 terminals (default on modern Linux/macOS), uses Unicode
glyphs (`∞`, `⚠`, `✓`, `✗`, `•`). On non-UTF-8 environments
(`LC_ALL=C`, Windows cmd.exe, no-locale CI), falls back to ASCII
(`inf`, `WARN`, `OK`, `X`, `*`) to avoid mojibake.

Stdlib `locale.getpreferredencoding(False)` decides at module-import
time. Resolved once per process — no re-evaluation cost per glyph.
"""

from __future__ import annotations

import locale

_GLYPHS_UTF8 = {
    "check": "✓",
    "cross": "✗",
    "inf": "∞",
    "warn": "⚠",
    "bullet": "•",
}

_GLYPHS_ASCII = {
    "check": "OK",
    "cross": "X",
    "inf": "inf",
    "warn": "WARN",
    "bullet": "*",
}


def _resolve_unicode_ok() -> bool:
    """True if the active locale claims UTF-8."""
    try:
        enc = locale.getpreferredencoding(False) or ""
    except Exception:
        return False
    return enc.lower().replace("-", "") in {"utf8", "utf"}


_UNICODE_OK = _resolve_unicode_ok()
_TABLE = _GLYPHS_UTF8 if _UNICODE_OK else _GLYPHS_ASCII


def g(name: str) -> str:
    """Return the appropriate glyph for the active locale.

    Raises `KeyError` on an unknown name — callers should use the
    documented set (`check`, `cross`, `inf`, `warn`, `bullet`).
    """
    return _TABLE[name]
