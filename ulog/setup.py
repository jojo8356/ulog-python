"""ULog setup + helpers (FR1-FR3, FR15-FR20).

`setup()` is the only function 99% of users need. It:
  - resolves the color decision via `_color.resolve_color`
  - builds a formatter via `formatters._resolve_formatter`
  - removes any previously-installed ULog handler (idempotency, FR2)
  - installs a fresh StreamHandler tagged `_ulog_managed=True`
  - applies the requested level

`get_logger()` and `set_level()` are thin stdlib passthroughs so users
keep the standard `logging.Logger` API.
"""
from __future__ import annotations

import logging
import sys
from typing import IO, Any, Literal

from ._color import ColorMode, resolve_color
from .formatters import _resolve_formatter

LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def setup(
    *,
    level: LogLevel | str = "INFO",
    format: str = "qlnes",
    color: ColorMode = "auto",
    stream: IO[str] | None = None,
    name: str | None = None,
    propagate: bool = False,
    **formatter_kwargs: Any,
) -> logging.Logger:
    """Configure a ulog-managed handler on the named (or root) logger.

    Args:
      level: minimum level to emit. Accepts a string ('INFO') or stdlib
        int constant (`logging.INFO`).
      format: name of a registered formatter — built-ins are 'qlnes',
        'simple', 'verbose', 'json'. Custom names register via
        `register_formatter()`.
      color: 'auto' (default — TTY-detect), 'always', or 'never'. The
        `NO_COLOR` env var hard-clamps to 'never' regardless.
      stream: defaults to `sys.stderr`. Tests inject `io.StringIO`.
      name: target logger name; `None` means the root logger. Setting
        `name='myproject'` configures only `getLogger('myproject')`
        and its children.
      propagate: when `name` is non-None, controls whether records
        bubble up to the root logger. Default `False` for namespaced
        setup (avoids double-printing if the host configured the root
        with a different formatter); set `True` if you want to feed an
        upstream config.
      **formatter_kwargs: passed through to the formatter's
        constructor — e.g. `prefix='myapp'` for the qlnes formatter.

    Returns the configured `logging.Logger` (handy for chaining).
    """
    if level not in LOG_LEVELS and not isinstance(level, int):
        raise ValueError(
            f"unknown log level {level!r}; valid: {', '.join(LOG_LEVELS)}"
        )
    if color not in ("auto", "always", "never"):
        raise ValueError(
            f"unknown color mode {color!r}; valid: 'auto', 'always', 'never'"
        )

    use_stream = stream if stream is not None else sys.stderr
    color_on = resolve_color(color, use_stream)
    formatter = _resolve_formatter(
        format, color_on=color_on, **formatter_kwargs
    )

    logger = logging.getLogger(name)

    # FR2 idempotency: drop only handlers WE installed; preserve user
    # handlers (e.g. file handlers attached separately).
    for h in list(logger.handlers):
        if getattr(h, "_ulog_managed", False):
            logger.removeHandler(h)

    handler = logging.StreamHandler(use_stream)
    handler.setFormatter(formatter)
    handler._ulog_managed = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(level)
    if name is not None:
        logger.propagate = propagate

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return `logging.getLogger(name)` — a normal stdlib logger.

    Works whether or not `setup()` has been called. In a library use
    pattern, callers do `log = ulog.get_logger(__name__)` and the
    application decides logging policy via `setup()` (or doesn't, in
    which case Python's defaults apply).
    """
    return logging.getLogger(name)


def set_level(level: LogLevel | str | int, name: str | None = None) -> None:
    """Adjust an existing logger's level without re-running setup.

    Convenience for CLI tools that want to flip levels mid-run (e.g.
    `--debug` raising the level after argument parsing).
    """
    logging.getLogger(name).setLevel(level)


def is_configured(name: str | None = None) -> bool:
    """Return True if `setup()` has been called for that logger name.

    Detects ulog-managed handlers specifically — user-installed
    handlers (or other logging configurations) do not count.
    """
    logger = logging.getLogger(name)
    return any(getattr(h, "_ulog_managed", False) for h in logger.handlers)
