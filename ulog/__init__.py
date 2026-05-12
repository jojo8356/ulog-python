"""ULog — stdlib `logging`, with the batteries that should have been included.

A thin layer on top of Python's standard `logging` module that ships
sensible defaults, four built-in formatters (qlnes / simple / verbose /
json), ucolor integration for terminal colour, and `contextvars`-based
field binding for structured logging.

Designed to be dropped in alongside any code that already uses
`logging.getLogger(__name__)` — ULog never installs a parallel logger
hierarchy. See docs/prds/PRD-v0.1-core.md for the full design rationale.

Quick start:

    import ulog
    ulog.setup(format='qlnes', color='auto')
    log = ulog.get_logger(__name__)
    log.info("hello")
    log.error("boom")        # → "qlnes: error: boom" in red on a TTY
"""

from __future__ import annotations

from ._bisect import BisectResult, bisect
from ._correlate import CorrelationReport, CorrelationRow, correlate
from ._incidents import IncidentState, compute_states, reopen, resolve
from .context import bind, clear, context, get_bound, unbind
from .formatters import (
    JsonFormatter,
    QlnesFormatter,
    SimpleFormatter,
    VerboseFormatter,
    register_formatter,
)
from .handlers import CSVHandler, JSONLineHandler, SchemaError, SQLHandler
from .replay import is_replaying, replay, replay_to_pytest
from .setup import (
    LOG_LEVELS,
    PROFILES,
    LogLevel,
    Profile,
    default_db_path,
    get_logger,
    is_configured,
    set_level,
    setup,
)

__version__ = "0.1.0"

__all__ = [
    "LOG_LEVELS",
    "PROFILES",
    # Bisect (v0.5, Story 4.7)
    "BisectResult",
    "CSVHandler",
    # Correlate (v0.5, Story 4.5)
    "CorrelationReport",
    "CorrelationRow",
    # Incidents (v0.5, Epic 5)
    "IncidentState",
    "JSONLineHandler",
    "JsonFormatter",
    "LogLevel",
    "Profile",
    # Formatter registration / classes (advanced)
    "QlnesFormatter",
    # Storage handlers (v0.2)
    "SQLHandler",
    "SchemaError",
    "SimpleFormatter",
    "VerboseFormatter",
    "__version__",
    # Context binding
    "bind",
    "bisect",
    "clear",
    "compute_states",
    "context",
    "correlate",
    "default_db_path",
    "get_bound",
    "get_logger",
    "is_configured",
    # Replay state (v0.5, Story 4.2)
    "is_replaying",
    "register_formatter",
    # Incidents (v0.5, Epic 5)
    "reopen",
    # Replay (v0.5, Story 4.1)
    "replay",
    # Replay-to-pytest generator (v0.5, Story 4.3)
    "replay_to_pytest",
    "resolve",
    "set_level",
    # Setup
    "setup",
    "unbind",
]
