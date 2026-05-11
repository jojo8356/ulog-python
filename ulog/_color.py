"""Color resolution layer.

Wraps ucolor when installed; provides a 50-line ANSI fallback so ULog
stays usable zero-deps. The fallback supports the 8 basic ANSI colors
+ bold/dim styles — enough for level-prefix rendering without 24-bit
truecolor accuracy.
"""

from __future__ import annotations

import os
from typing import IO, Any, Literal

ColorMode = Literal["auto", "always", "never"]

# 8-color ANSI codes for the fallback (when ucolor isn't installed).
# Matches the qlnes/io/log.py pre-ucolor palette.
_FALLBACK_ANSI: dict[str, str] = {
    "red": "\033[31m",
    "red_bold": "\033[31;1m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "blue": "\033[34m",
    "grey": "\033[90m",
    "grey_dim": "\033[2m",
    "reset": "\033[0m",
}


def resolve_color(mode: ColorMode, stream: IO[Any]) -> bool:
    """Decide whether ANSI escapes should be emitted for this stream.

    `NO_COLOR` env var hard-clamps to False (per https://no-color.org).
    `mode='always'` overrides isatty(); `mode='never'` clamps off.
    """
    if os.environ.get("NO_COLOR") is not None:
        return False
    if mode == "never":
        return False
    if mode == "always":
        return True
    # auto
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    return os.environ.get("TERM") != "dumb"


def have_ucolor() -> bool:
    """Return True if `ucolor` is importable in the current environment.

    ULog uses ucolor for 24-bit truecolor when available; falls back to
    the 8-color ANSI palette otherwise.
    """
    try:
        import ucolor  # noqa: F401

        return True
    except ImportError:
        return False


def color_level(level_name: str, *, color_on: bool) -> tuple[str, str]:
    """Return `(prefix, suffix)` ANSI codes for a level prefix.

    With `color_on=False` returns `("", "")` so the formatter emits
    plain text. With ucolor installed, uses ucolor's truecolor styling;
    otherwise falls back to the 8-color palette.
    """
    if not color_on:
        return "", ""
    if have_ucolor():
        return _ucolor_level(level_name)
    return _fallback_level(level_name)


def _ucolor_level(level_name: str) -> tuple[str, str]:
    from ucolor import UColor
    from ucolor.color_mode import ColorMode as UColorMode

    UColor.force_mode(UColorMode.TRUE_COLOR)
    style_map = {
        "DEBUG": UColor.css("grey").dim(),
        "INFO": None,  # plain
        "WARNING": UColor.css("yellow"),
        "ERROR": UColor.css("red").bold(),
        "CRITICAL": UColor.css("red").bold(),
    }
    style = style_map.get(level_name)
    if style is None:
        return "", ""
    # ucolor doesn't expose pure-prefix; we wrap a placeholder and split.
    wrapped = style.wrap("\x00")
    prefix, _, suffix = wrapped.partition("\x00")
    return prefix, suffix


def _fallback_level(level_name: str) -> tuple[str, str]:
    code = {
        "DEBUG": _FALLBACK_ANSI["grey_dim"],
        "INFO": "",
        "WARNING": _FALLBACK_ANSI["yellow"],
        "ERROR": _FALLBACK_ANSI["red_bold"],
        "CRITICAL": _FALLBACK_ANSI["red_bold"],
    }.get(level_name, "")
    if not code:
        return "", ""
    return code, _FALLBACK_ANSI["reset"]
