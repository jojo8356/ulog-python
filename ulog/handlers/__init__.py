"""Storage handlers for ULog v0.2 (FR21-FR31).

Three persistent handlers compose with the v0.1 stream handler:

    ulog.setup(handlers=['stream', 'sql', 'json'],
               sql_url='sqlite:///./logs.sqlite',
               json_path='./logs.jsonl')

Each handler is a stdlib `logging.Handler` subclass — they emit records
the same way the built-in stream handler does, just to a persistent
target. This means user-installed handlers (file rotation, syslog,
Sentry…) keep working alongside ULog's storage backends.
"""

from __future__ import annotations

from .csv_file import CSVHandler
from .json_line import JSONLineHandler
from .sql import SchemaError, SQLHandler

__all__ = [
    "CSVHandler",
    "JSONLineHandler",
    "SQLHandler",
    "SchemaError",
]
