"""ULog formatters (FR6-FR10).

Four built-in formatters cover the user-facing CLI cases (qlnes,
simple, verbose) and the pipeline/aggregator case (json). Custom
formatters register via `register_formatter(name, cls)`.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from typing import Any

from ._color import color_level
from .context import get_bound


class _ColorAwareFormatter(logging.Formatter):
    """Common base: holds the `color_on` decision and exposes the
    `_decorate` helper that writes the level prefix with ANSI codes
    when colour is enabled."""

    def __init__(self, *, color_on: bool = False) -> None:
        super().__init__()
        self._color_on = color_on

    def _decorate(self, level_name: str, prefix: str) -> str:
        before, after = color_level(level_name, color_on=self._color_on)
        if not before:
            return prefix
        return before + prefix + after


class QlnesFormatter(_ColorAwareFormatter):
    """`<prefix>: <level>: <msg>` for non-INFO; bare `<msg>` for INFO/DEBUG.

    Default prefix is `qlnes` (set via `setup(format='qlnes', prefix='myapp')`
    to override). Matches the contract qlnes ships with — INFO lines are
    bare so user-facing progress markers like `→ rendu in-process` print
    cleanly without log noise.
    """

    def __init__(self, *, color_on: bool = False, prefix: str = "qlnes") -> None:
        super().__init__(color_on=color_on)
        self._prefix = prefix

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.levelno <= logging.INFO:
            return msg
        level_word = record.levelname.lower()
        prefix_chunk = f"{self._prefix}: {level_word}: "
        return self._decorate(record.levelname, prefix_chunk) + msg


class SimpleFormatter(_ColorAwareFormatter):
    """`[<LEVEL>] <msg>`. Compact, color-aware, universal default.

    Distinct from QlnesFormatter in that ALL levels carry a prefix
    (including INFO) — useful when users want consistent line shapes
    across levels.
    """

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        prefix = f"[{record.levelname}] "
        return self._decorate(record.levelname, prefix) + msg


class VerboseFormatter(_ColorAwareFormatter):
    """`<ts> <LEVEL> [<logger>] <msg> (file:line)`.

    Includes ISO-8601 UTC timestamp + the bound context fields when
    present. Best for development logs and bug reports.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created))
        msg = record.getMessage()
        bound = get_bound()
        bound_chunk = ""
        if bound:
            bound_chunk = " " + " ".join(f"{k}={v!r}" for k, v in bound.items())
        location = f" ({record.filename}:{record.lineno})"
        prefix = f"{ts} "
        level_chunk = self._decorate(record.levelname, record.levelname)
        body = f" [{record.name}] {msg}{bound_chunk}{location}"
        line = prefix + level_chunk + body
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class JsonFormatter(logging.Formatter):
    """One JSON object per record on the configured stream.

    Stable schema (v0.1):
        {
          "ts":     ISO-8601 UTC,
          "level":  str (DEBUG|INFO|WARNING|ERROR|CRITICAL),
          "logger": str (record.name),
          "msg":    str (record.getMessage()),
          "file":   str (record.filename),
          "line":   int (record.lineno),
          ...bound fields from contextvars
        }

    On `record.exc_info`, an `exc` field is added:
        "exc": {"type": ..., "msg": ..., "tb": [str, ...]}

    Custom fields can be added via the standard `extra=` kwarg:
        log.info("rendered", extra={'rom': 'alter_ego'})
    """

    # Reserved attribute names on LogRecord — anything in `extra=` not
    # in this set lands in the JSON output.
    _RESERVED = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "taskName",  # py3.12+
        }
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "file": record.filename,
            "line": record.lineno,
        }
        # Merge bound contextvars
        bound = get_bound()
        if bound:
            for k, v in bound.items():
                if k not in payload:
                    payload[k] = v
        # Merge `extra=` fields (anything on the record we don't reserve)
        for k, v in record.__dict__.items():
            if k not in self._RESERVED and k not in payload and not k.startswith("_"):
                payload[k] = v
        # Exception info
        if record.exc_info:
            etype, evalue, etb = record.exc_info
            tb_lines = traceback.format_tb(etb) if etb else []
            payload["exc"] = {
                "type": etype.__name__ if etype else None,
                "msg": str(evalue) if evalue else None,
                "tb": [line.rstrip("\n") for line in tb_lines],
            }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# -- Registration ---------------------------------------------------------


_BUILTINS: dict[str, type[logging.Formatter]] = {
    "qlnes": QlnesFormatter,
    "simple": SimpleFormatter,
    "verbose": VerboseFormatter,
    "json": JsonFormatter,
}

_REGISTERED: dict[str, type[logging.Formatter]] = dict(_BUILTINS)


def register_formatter(name: str, cls: type[logging.Formatter]) -> None:
    """Add a custom formatter under `name`. Replaces any previous
    formatter at that name (including built-ins, to allow overriding)."""
    if not issubclass(cls, logging.Formatter):
        raise TypeError(f"register_formatter requires a logging.Formatter subclass; got {cls!r}")
    _REGISTERED[name] = cls


def _resolve_formatter(name: str, *, color_on: bool, **kwargs: Any) -> logging.Formatter:
    """Internal: build a formatter instance from its registered name.

    `color_on` is forwarded to color-aware formatters; JSON ignores it.
    Extra kwargs (e.g. `prefix='myapp'` for QlnesFormatter) are passed
    through.
    """
    if name not in _REGISTERED:
        raise ValueError(f"unknown formatter {name!r}; registered: {sorted(_REGISTERED.keys())}")
    cls = _REGISTERED[name]
    if cls is JsonFormatter:
        return cls()
    if issubclass(cls, _ColorAwareFormatter):
        return cls(color_on=color_on, **kwargs)
    # Custom user-registered formatters: pass color_on if accepted, else not.
    try:
        return cls(color_on=color_on, **kwargs)  # type: ignore[call-arg]
    except TypeError:
        return cls(**kwargs)
