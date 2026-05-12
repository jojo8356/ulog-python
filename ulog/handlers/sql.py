"""SQLAlchemy handler — persists log records to any SQL backend.

Schema (FR22): single table, indexed for the common filter axes
(ts, level, logger, file). Bound context + exception serialized as
JSON columns. SQLite by default; Postgres/MySQL via URL.
"""

from __future__ import annotations

import atexit
import contextlib
import datetime
import logging
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from ..context import get_bound

# Reserved LogRecord keys (matches CSVHandler / JsonFormatter).
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
        "taskName",
    }
)


# Story 3.3 / Decision A2 — literal upgrade DDL for v0.4 → v0.5.
# Map each v0.5 chain column to its ALTER TABLE statement and (when
# applicable) its CREATE INDEX statement, keyed by column name so the
# error message can list only the columns actually missing on a given
# DB. `{t}` placeholder is `_table_name` at format time.
_CHAIN_COLUMN_ALTER_DDL: dict[str, str] = {
    "chain_pos": "ALTER TABLE {t} ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0;",
    "immutable": "ALTER TABLE {t} ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0;",
    "is_replay": "ALTER TABLE {t} ADD COLUMN is_replay INTEGER NOT NULL DEFAULT 0;",
    "prev_hash": "ALTER TABLE {t} ADD COLUMN prev_hash BLOB;",
    "record_hash": "ALTER TABLE {t} ADD COLUMN record_hash BLOB;",
}
_CHAIN_COLUMN_INDEX_DDL: dict[str, str] = {
    "chain_pos": "CREATE INDEX ix_{t}_chain_pos ON {t}(chain_pos);",
    "immutable": "CREATE INDEX ix_{t}_immutable ON {t}(immutable);",
    "is_replay": "CREATE INDEX ix_{t}_is_replay ON {t}(is_replay);",
}


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
        chain_mode: bool = False,
        immutable_when: Any = None,
    ) -> None:
        super().__init__()
        # Initialize the lock + empty buffer FIRST. logging.Handler.__init__
        # has already registered us in the global handler list; if the
        # sqlalchemy import below fails, logging.shutdown() will still
        # iterate this instance and call flush() — which would crash on
        # a missing _lock. With these set, flush() becomes a clean no-op
        # on a degraded handler. (Bug found running run.sh demo on a
        # python without sqlalchemy installed.)
        self._lock = threading.Lock()
        self._buffer: list[dict[str, Any]] = []
        self._url = url or f"sqlite:///{(Path.cwd() / 'ulog.sqlite').as_posix()}"
        self._table_name = table
        self._batch_size = max(1, batch_size)
        self._chain_mode = chain_mode
        self._immutable_when = immutable_when
        self._immutable_when_warned: bool = False

        from sqlalchemy import (
            JSON,
            Column,
            DateTime,
            Index,
            Integer,
            LargeBinary,
            MetaData,
            String,
            Table,
            Text,
            create_engine,
        )

        self._engine = create_engine(self._url, future=True)

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
            # v0.5 chain integrity (Epic 3 / Story 3.1). Columns ride
            # along on every v0.5 schema; population is gated by
            # `setup(integrity='hash-chain')` once Story 3.6 lands.
            # `INTEGER` not `Boolean` for `immutable` — keeps the v0.4→v0.5
            # upgrade-hint SQL string (Story 3.3) unambiguous.
            Column("chain_pos", Integer, nullable=False, server_default="0"),
            Column("record_hash", LargeBinary, nullable=True),
            Column("prev_hash", LargeBinary, nullable=True),
            Column("immutable", Integer, nullable=False, server_default="0"),
            # Story 4.2 — set to 1 by `_record_to_row` when emitted
            # from inside a `replay()` body. Distinguishes replay-
            # induced records from production records (FR99 / Gap G2).
            Column("is_replay", Integer, nullable=False, server_default="0"),
            Index(f"ix_{table}_ts", "ts"),
            Index(f"ix_{table}_level", "level"),
            Index(f"ix_{table}_logger", "logger"),
            Index(f"ix_{table}_file", "file"),
            Index(f"ix_{table}_chain_pos", "chain_pos"),
            Index(f"ix_{table}_immutable", "immutable"),
            Index(f"ix_{table}_is_replay", "is_replay"),
        )
        # Lazy-create on first emit; expose for tests.
        self._metadata = metadata
        self._schema_initialized = False
        # Story 3.5 — chain mode wiring. WAL pragma at engine init so
        # multi-process writers serialise on chain_pos under BEGIN
        # IMMEDIATE (which the chain writer registers) without
        # blocking readers.
        self._chain_writer: Any = None
        if self._chain_mode:
            if self._engine.dialect.name == "sqlite":
                with self._engine.connect() as conn:
                    conn.exec_driver_sql("PRAGMA journal_mode=WAL")
                # Story 3.12 AC1 — refuse to open in chain mode if a
                # previous verify reported BROKEN. Forces the user to
                # run `ulog repair --confirm` before any new chain
                # writes can land.
                from .._verify_state import read_verify_state

                db_path = Path(self._url.replace("sqlite:///", "", 1))
                state = read_verify_state(db_path)
                if state and state.get("status") == "BROKEN":
                    raise SchemaError(
                        f"chain integrity is BROKEN at #{state.get('broken_at')}. "
                        "Run `ulog repair --confirm` to resolve before "
                        "re-opening the handler in chain mode."
                    )
            from .._chain import SQLiteChainWriter

            self._chain_writer = SQLiteChainWriter(self._engine, self._table_name)
        # Process-exit flush — best-effort, prevents lost records.
        atexit.register(self._safe_flush)

    # -- Public API --

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_schema()
            row = self._record_to_row(record)
            if self._chain_mode:
                self._chain_append(row)
                return
            with self._lock:
                self._buffer.append(row)
                buf_len = len(self._buffer)
            if buf_len >= self._batch_size:
                self.flush()
        except Exception:
            self.handleError(record)

    def _chain_append(self, row: dict[str, Any]) -> None:
        # Cross-process serialisation: get-prev + compute-hash + INSERT
        # MUST happen inside one BEGIN IMMEDIATE txn. Doing
        # get_last_hash + append as separate txns races between
        # processes (Story 3.11 stress test surfaced this — two procs
        # would read the same prev_hash and write diverging chains).
        from .._chain import sha256_record

        with self._lock:
            self._chain_writer.append_atomic(row, sha256_record)

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
        from sqlalchemy.exc import OperationalError

        inspector = inspect(self._engine)
        if self._table_name not in inspector.get_table_names():
            # Fresh DB — create our schema.
            #
            # Race window: under multi-process bootstrap (xdist workers
            # sharing one --ulog-db, or any multi-process app sharing a
            # SQL handler), worker A and B may both see the table as
            # missing, both call create_all, and the loser raises
            # OperationalError("table already exists"). The table DOES
            # exist after the race, so we just fall through to the
            # column-verify path on retry.
            try:
                self._metadata.create_all(self._engine)
            except OperationalError as exc:
                if "already exists" not in str(exc).lower():
                    raise
                # Re-inspect: the winning worker created the table.
                inspector = inspect(self._engine)
                if self._table_name not in inspector.get_table_names():
                    raise  # not the race we expected
            else:
                self._install_immutable_triggers()
                return
        # Existing table — verify columns match.
        existing_cols = {col["name"] for col in inspector.get_columns(self._table_name)}
        expected_cols = {c.name for c in self._table.columns}
        missing = expected_cols - existing_cols
        if missing:
            chain_missing = sorted(missing & _CHAIN_COLUMN_ALTER_DDL.keys())
            if chain_missing:
                t = self._table_name
                alters = "\n".join(_CHAIN_COLUMN_ALTER_DDL[c].format(t=t) for c in chain_missing)
                index_cols = [c for c in chain_missing if c in _CHAIN_COLUMN_INDEX_DDL]
                indexes = "\n".join(_CHAIN_COLUMN_INDEX_DDL[c].format(t=t) for c in index_cols)
                sep = "\n" if indexes else ""
                raise SchemaError(
                    f"table {t!r} in {self._url} is a v0.4 schema; v0.5 "
                    "requires the following ALTER TABLE / CREATE INDEX "
                    "statements. v0.2's no-migrations contract is "
                    "preserved — apply manually:\n\n"
                    f"{alters}{sep}{indexes}\n\n"
                    "Note (Gap G1 — pre-chain upgrade discontinuity):\n"
                    "Existing rows will have NULL record_hash/prev_hash "
                    "after the ALTER (pre-chain backfilled). The first "
                    "NEW chain record starts a fresh chain with prev_hash "
                    '= b"\\x00" * 32. `ulog verify` only walks records '
                    "with non-NULL hash."
                )
            raise SchemaError(
                f"table {self._table_name!r} in {self._url} is missing columns "
                f"{sorted(missing)}. v0.2 doesn't ship migrations — delete "
                "the DB / use a fresh URL, or add the columns manually."
            )
        self._install_immutable_triggers()

    def _install_immutable_triggers(self) -> None:
        # Story 3.2 / invariant I4 — storage-layer enforcement that
        # rows with immutable=1 cannot be UPDATEd or DELETEd through
        # ANY client (not just SQLHandler). SQLite-only; v0.7 Postgres
        # will install an equivalent via partial-index + rule or
        # plpgsql function (Decision B3).
        if self._engine.dialect.name != "sqlite":
            return
        from sqlalchemy import text

        t = self._table_name
        update_trigger = (
            f"CREATE TRIGGER IF NOT EXISTS trg_{t}_block_update_immutable "
            f"BEFORE UPDATE ON {t} "
            "FOR EACH ROW "
            "WHEN OLD.immutable = 1 "
            "BEGIN "
            "SELECT RAISE(ABORT, 'immutable row: UPDATE forbidden (invariant I4)'); "
            "END;"
        )
        delete_trigger = (
            f"CREATE TRIGGER IF NOT EXISTS trg_{t}_block_delete_immutable "
            f"BEFORE DELETE ON {t} "
            "FOR EACH ROW "
            "WHEN OLD.immutable = 1 "
            "BEGIN "
            "SELECT RAISE(ABORT, 'immutable row: DELETE forbidden (invariant I4)'); "
            "END;"
        )
        with self._engine.begin() as conn:
            conn.execute(text(update_trigger))
            conn.execute(text(delete_trigger))

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
                "tb": [line.rstrip("\n") for line in (traceback.format_tb(etb) if etb else [])],
            }
        # JSON columns can hold dicts directly with SQLAlchemy 2.x; for
        # SQLite the driver serializes via json.dumps under the hood.
        row: dict[str, Any] = {
            "ts": _ts_aware(record.created),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "file": record.filename,
            "line": record.lineno,
            "exc": exc_payload,
            "context": bound or None,
        }
        # Decision B5 (Story 3.12) — immutable_when fail-safe: on
        # exception, treat the record AS IMMUTABLE (preserve forensic
        # evidence). Stderr print, NOT ulog logging (would recurse).
        # One-shot guard so a broken callable doesn't flood stderr.
        immutable_flag = 0
        if self._immutable_when is not None:
            try:
                if self._immutable_when(record):
                    immutable_flag = 1
            except Exception as exc:
                if not self._immutable_when_warned:
                    print(
                        f"ulog: immutable_when callable raised "
                        f"{type(exc).__name__}: {exc!r}; treating as immutable=1 "
                        "(Decision B5 fail-safe)",
                        file=sys.stderr,
                    )
                    self._immutable_when_warned = True
                immutable_flag = 1  # fail-safe: preserve evidence
        row["immutable"] = immutable_flag
        # Story 4.2 / Gap G2 — stamp is_replay at insert time. The
        # ContextVar is set by `ulog.replay()` around the callback;
        # outside replay context it's False → is_replay=0.
        from ..replay import is_replaying

        row["is_replay"] = 1 if is_replaying() else 0
        return row

    def _safe_flush(self) -> None:
        with contextlib.suppress(Exception):
            self.flush()


def _ts_aware(epoch: float) -> datetime.datetime:
    """Convert a `time.time()` float to a naive UTC datetime suitable
    for SQLAlchemy's `DateTime(timezone=False)` column."""
    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc).replace(tzinfo=None)
