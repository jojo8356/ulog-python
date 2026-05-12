"""Chain integrity backend abstraction (Decision B3) + hash helpers.

A `ChainWriter` encapsulates the storage-side hash-chain append
semantics. v0.5 ships `SQLiteChainWriter`; v0.7 will add
`PostgresChainWriter` using `SELECT ... FOR UPDATE` instead of
`BEGIN IMMEDIATE`. The Protocol is `@runtime_checkable` so chain-
related tests can mock the backend without spinning up SQLite.

`canonical_record_json` + `sha256_record` (Story 3.5) are reusable by
`SQLHandler.emit` (chain write) and `ulog verify` (Story 3.7,
re-walks the chain to recompute hashes).
"""

from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import json as _json
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ChainWriter(Protocol):
    """Storage-side hash-chain append contract.

    Implementations must serialise concurrent appends so that
    chain_pos values are monotonic and gap-free.
    """

    def get_last_hash(self) -> bytes:
        """Return the most recent record_hash, or b'\\x00' * 32 if empty."""
        ...

    def append(
        self,
        record: dict[str, Any],
        record_hash: bytes,
        prev_hash: bytes,
    ) -> int:
        """Insert a record with chain metadata. Returns assigned chain_pos."""
        ...


class SQLiteChainWriter:
    """Chain writer backed by SQLAlchemy + SQLite under BEGIN IMMEDIATE.

    Concurrent appends are serialised by SQLite's write lock (acquired
    eagerly via BEGIN IMMEDIATE, wired here as a `do_begin` event
    listener on the engine — registered once per engine, idempotent
    across multiple `SQLiteChainWriter` instances).
    """

    _ZERO_HASH: bytes = b"\x00" * 32

    def __init__(self, engine: Any, table_name: str = "logs") -> None:
        self._engine = engine
        self._table_name = table_name
        if engine.dialect.name == "sqlite" and not getattr(
            engine, "_ulog_chain_begin_immediate", False
        ):
            from sqlalchemy import event

            # pysqlite's default isolation_level mode emits its own
            # BEGIN; disable that so our explicit BEGIN IMMEDIATE wins.
            # Pattern documented in SQLAlchemy SQLite dialect docs.
            @event.listens_for(engine, "connect")
            def _disable_pysqlite_begin(dbapi_conn: Any, _rec: Any) -> None:
                dbapi_conn.isolation_level = None

            @event.listens_for(engine, "begin")
            def _begin_immediate(conn: Any) -> None:
                conn.exec_driver_sql("BEGIN IMMEDIATE")

            engine._ulog_chain_begin_immediate = True

    def get_last_hash(self) -> bytes:
        from sqlalchemy import text

        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    f"SELECT record_hash FROM {self._table_name} "
                    "WHERE record_hash IS NOT NULL "
                    "ORDER BY chain_pos DESC LIMIT 1"
                )
            ).first()
        if row is None or row[0] is None:
            return self._ZERO_HASH
        return bytes(row[0])

    def append(
        self,
        record: dict[str, Any],
        record_hash: bytes,
        prev_hash: bytes,
    ) -> int:
        from sqlalchemy import text

        row = dict(record)
        # Raw text() INSERT bypasses SQLAlchemy's type adapters, so
        # dict/list values (destined for JSON columns) need to be
        # serialised here. The hash was already computed over the
        # logical dict form; verify-time we parse JSON back to dicts
        # before recomputing.
        for k, v in list(row.items()):
            if isinstance(v, dict | list):
                row[k] = _json.dumps(v, sort_keys=True, separators=(",", ":"))
        with self._engine.begin() as conn:
            next_pos = conn.execute(
                text(f"SELECT COALESCE(MAX(chain_pos), 0) + 1 FROM {self._table_name}")
            ).scalar_one()
            row["chain_pos"] = int(next_pos)
            row["record_hash"] = record_hash
            row["prev_hash"] = prev_hash
            cols = list(row.keys())
            col_list = ", ".join(cols)
            placeholders = ", ".join(f":{c}" for c in cols)
            conn.execute(
                text(f"INSERT INTO {self._table_name} ({col_list}) VALUES ({placeholders})"),
                row,
            )
        return int(next_pos)

    def append_atomic(
        self,
        record: dict[str, Any],
        hash_fn: Any,
    ) -> int:
        """Read prev_hash, compute record_hash, and INSERT — all inside
        ONE `BEGIN IMMEDIATE` transaction. Required for cross-process
        correctness: with `get_last_hash` + `append` as separate
        transactions, two processes could read the same prev_hash and
        produce diverging chains. Story 3.11 stress test exercises this.

        `hash_fn(record_dict, prev_hash) -> bytes` computes the row's
        hash; injected so this module stays free of hashing logic
        (which lives in `sha256_record` for verify-side reuse).
        """
        from sqlalchemy import text

        row = dict(record)
        for k, v in list(row.items()):
            if isinstance(v, dict | list):
                row[k] = _json.dumps(v, sort_keys=True, separators=(",", ":"))
        with self._engine.begin() as conn:
            prev_row = conn.execute(
                text(
                    f"SELECT record_hash FROM {self._table_name} "
                    "WHERE record_hash IS NOT NULL "
                    "ORDER BY chain_pos DESC LIMIT 1"
                )
            ).first()
            prev_hash = (
                bytes(prev_row[0]) if prev_row and prev_row[0] is not None else self._ZERO_HASH
            )
            next_pos = conn.execute(
                text(f"SELECT COALESCE(MAX(chain_pos), 0) + 1 FROM {self._table_name}")
            ).scalar_one()
            record_hash = hash_fn(record, prev_hash)
            row["chain_pos"] = int(next_pos)
            row["record_hash"] = record_hash
            row["prev_hash"] = prev_hash
            cols = list(row.keys())
            col_list = ", ".join(cols)
            placeholders = ", ".join(f":{c}" for c in cols)
            conn.execute(
                text(f"INSERT INTO {self._table_name} ({col_list}) VALUES ({placeholders})"),
                row,
            )
        return int(next_pos)


# ---- Canonical JSON + hash helpers (Story 3.5) ---------------------------


def _canonical_default(obj: Any) -> Any:
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, bytes | bytearray):
        return obj.hex()
    raise TypeError(f"non-canonicalisable value of type {type(obj).__name__}")


def canonical_record_json(record: Mapping[str, Any]) -> bytes:
    """Deterministic UTF-8 bytes representation of a record dict.

    Stable across runs and across Python dict insertion order
    (sort_keys=True). datetime → ISO-8601, bytes → hex. Used as the
    pre-image for `sha256_record`.
    """
    return _json.dumps(
        dict(record),
        sort_keys=True,
        separators=(",", ":"),
        default=_canonical_default,
    ).encode("utf-8")


def sha256_record(record: Mapping[str, Any], prev_hash: bytes) -> bytes:
    """Compute `sha256(canonical_record_json(record) + prev_hash)`.

    Decision: stdlib hashlib, no external crypto lib.
    """
    return _hashlib.sha256(canonical_record_json(record) + prev_hash).digest()
