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

from .context import bind, clear, context, get_bound, unbind
from .formatters import (
    JsonFormatter,
    QlnesFormatter,
    SimpleFormatter,
    VerboseFormatter,
    register_formatter,
)
from .handlers import CSVHandler, JSONLineHandler, SchemaError, SQLHandler
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
    # Setup
    "setup",
    "get_logger",
    "set_level",
    "is_configured",
    "default_db_path",
    "LOG_LEVELS",
    "LogLevel",
    "PROFILES",
    "Profile",
    # Context binding
    "bind",
    "unbind",
    "clear",
    "context",
    "get_bound",
    # Formatter registration / classes (advanced)
    "QlnesFormatter",
    "SimpleFormatter",
    "VerboseFormatter",
    "JsonFormatter",
    "register_formatter",
    # Storage handlers (v0.2)
    "SQLHandler",
    "JSONLineHandler",
    "CSVHandler",
    "SchemaError",
    "__version__",
]
