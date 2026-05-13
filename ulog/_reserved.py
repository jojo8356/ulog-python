"""Canonical set of reserved `logging.LogRecord` attribute names (Story 7.1).

Anything in `extra={...}` whose key is NOT in `RESERVED` lands in the
JSON payload / SQL `context` column / CSV `context_json` column. This
module is the single source of truth — previously the same frozenset
was duplicated in `formatters.py`, `handlers/sql.py`, `handlers/csv_file.py`.

When a new stdlib `LogRecord` attribute appears (e.g. `taskName` in
3.12), update this set and every consumer picks it up automatically.
"""

from __future__ import annotations

RESERVED: frozenset[str] = frozenset(
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
