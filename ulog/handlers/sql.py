"""SQLAlchemy handler — persists log records to any SQL backend.

Schema (FR22): single table, indexed for the common filter axes
(ts, level, logger, file). Bound context + exception serialized as
JSON columns. SQLite by default; Postgres/MySQL via URL.
"""
from __future__ import annotations

import atexit
import json
import logging
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from ..context import get_bound

# Reserved LogRecord keys (matches CSVHandler / JsonFormatter).
_RESERVED = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
        "taskName",
    }
)


class SchemaError(Exception):
    """Raised when the existing DB schema doesn't match what ULog expects.

    Hint: delete the file (or use a fresh URL). v0.2 doesn't ship
    migrations.
    """


class SQLHandler(logging.Handler):
    """Persist log records to a SQL DB via SQLAlchemy.

    Example:

        ulog.setup(handlers=['sql'], sql_url='sqlite:///./logs.sqlite')

    Or directly:

        h = SQLHandler('sqlite:///./logs.sqlite')
        log = ulog.get_logger()
        log.addHandler(h)

    Records are buffered in-memory and flushed in batches of
    `batch_size` (default 100) for throughput. A flush also happens on
    `handler.flush()` and at process exit (registered via `atexit`).
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        table: str = "logs",
        batch_size: int = 100,
    ) -> None:
        super().__init__()
        from sqlalchemy import (
            JSON,
            Column,
            DateTime,
            Index,
            Integer,
            MetaData,
            String,
            Table,
            Text,
            create_engine,
        )

        self._url = url or f"sqlite:///{(Path.cwd() / 'ulog.sqlite').as_posix()}"
        self._table_name = table
        self._batch_size = max(1, batch_size)
        self._engine = create_engine(self._url, future=True)
        self._lock = threading.Lock()
        self._buffer: list[dict[str, Any]] = []

        metadata = MetaData()
        self._table = Table(
            self._table_name,
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("ts", DateTime(timezone=False), nullable=False),
            Column("level", String(10), nullable=False),
            Column("logger", String(255), nullable=False),
            Column("msg", Text, nullable=False),
            Column("file", String(255), nullable=False),
            Column("line", Integer, nullable=False),
            Column("exc", JSON, nullable=True),
            Column("context", JSON, nullable=True),
            Index(f"ix_{table}_ts", "ts"),
            Index(f"ix_{table}_level", "level"),
            Index(f"ix_{table}_logger", "logger"),
            Index(f"ix_{table}_file", "file"),
        )
        # Lazy-create on first emit; expose for tests.
        self._metadata = metadata
        self._schema_initialized = False
        # Process-exit flush — best-effort, prevents lost records.
        atexit.register(self._safe_flush)

    # -- Public API --

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_schema()
            row = self._record_to_row(record)
            with self._lock:
                self._buffer.append(row)
                buf_len = len(self._buffer)
            if buf_len >= self._batch_size:
                self.flush()
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def flush(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = []
        try:
            with self._engine.begin() as conn:
                conn.execute(self._table.insert(), batch)
        except Exception:
            # If the DB is unreachable, drop the batch on the floor —
            # logging MUST not block the host process.
            # FUTURE: capture into a fallback FileHandler.
            pass

    def close(self) -> None:
        self.flush()
        try:
            self._engine.dispose()
        finally:
            super().close()

    # -- Internal --

    def _ensure_schema(self) -> None:
        if self._schema_initialized:
            return
        self._verify_or_create_schema()
        self._schema_initialized = True

    def _verify_or_create_schema(self) -> None:
        from sqlalchemy import inspect

        inspector = inspect(self._engine)
        if self._table_name not in inspector.get_table_names():
            # Fresh DB — create our schema.
            self._metadata.create_all(self._engine)
            return
        # Existing table — verify columns match.
        existing_cols = {col["name"] for col in inspector.get_columns(self._table_name)}
        expected_cols = {c.name for c in self._table.columns}
        missing = expected_cols - existing_cols
        if missing:
            raise SchemaError(
                f"table {self._table_name!r} in {self._url} is missing columns "
                f"{sorted(missing)}. v0.2 doesn't ship migrations — delete "
                "the DB / use a fresh URL, or add the columns manually."
            )

    def _record_to_row(self, record: logging.LogRecord) -> dict[str, Any]:
        bound = dict(get_bound())
        # Merge `extra=...` from the record (mirrors JsonFormatter)
        for k, v in record.__dict__.items():
            if k not in _RESERVED and k not in bound and not k.startswith("_"):
                bound[k] = v
        exc_payload: dict[str, Any] | None = None
        if record.exc_info:
            etype, evalue, etb = record.exc_info
            exc_payload = {
                "type": etype.__name__ if etype else None,
                "msg": str(evalue) if evalue else None,
                "tb": [
                    line.rstrip("\n")
                    for line in (traceback.format_tb(etb) if etb else [])
                ],
            }
        # JSON columns can hold dicts directly with SQLAlchemy 2.x; for
        # SQLite the driver serializes via json.dumps under the hood.
        return {
            "ts": _ts_aware(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "file": record.filename,
            "line": record.lineno,
            "exc": exc_payload,
            "context": bound or None,
        }

    def _safe_flush(self) -> None:
        try:
            self.flush()
        except Exception:  # noqa: BLE001
            pass


def _ts_aware(epoch: float):
    """Convert a `time.time()` float to a naive UTC datetime suitable
    for SQLAlchemy's `DateTime(timezone=False)` column."""
    import datetime as _dt

    return _dt.datetime.fromtimestamp(epoch, tz=_dt.timezone.utc).replace(tzinfo=None)
