# Story 3.4: `ChainWriter` Protocol + `SQLiteChainWriter` impl

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-4-chainwriter-protocol-sqlitechainwriter-impl`
**Implements:** Decision B3 (`ChainWriter` abstraction defined now, SQLite impl in v0.5, Postgres impl in v0.7), part of Decision B1 (chain logic encapsulated, accessed via Protocol)
**Source:** PRD-v0.5 §8.4 (ChainWriter recommended shape), architecture.md §B1/B3
**Built on:** Story 3.1 (schema has chain columns), Story 3.2 (immutable triggers in place to protect the chain), Story 3.3 (clean upgrade path so chain code only runs on a verified v0.5 schema).
**Foundation for:** Story 3.5 (`SQLHandler.emit` will call `chain_writer.append(...)` instead of buffered insert when integrity='hash-chain'), Story 3.7 (`ulog verify` walks `record_hash`/`prev_hash` written by this writer), Story 3.11 (concurrency stress test exercises this writer under 8 procs × 10K records).

## Story

As a **v0.5 implementer**,
I want **a small `ChainWriter` Protocol in `ulog/_chain.py` with a SQLite-backed impl that serialises chain appends under `BEGIN IMMEDIATE`**,
so that **chain-related tests can mock the backend without an actual SQLite DB, and v0.7 can swap in `PostgresChainWriter` without touching `SQLHandler`**.

## Acceptance Criteria

1. **`ulog/_chain.py` exists** and exports two public names: `ChainWriter` (a `typing.Protocol`, decorated `@runtime_checkable` so `isinstance` works) and `SQLiteChainWriter` (a concrete class). No other public names — keep the module tight per Decision B3 ("tiny interface").
2. **`ChainWriter` Protocol signature** —
   ```python
   class ChainWriter(Protocol):
       def get_last_hash(self) -> bytes: ...
       def append(
           self,
           record: dict[str, Any],
           record_hash: bytes,
           prev_hash: bytes,
       ) -> int: ...  # returns chain_pos
   ```
   Decorated `@runtime_checkable` so `isinstance(mock, ChainWriter)` returns True for any duck-typed object — supports AC8 (mockability).
3. **`SQLiteChainWriter(engine, table_name="logs")`** constructor accepts an existing SQLAlchemy `Engine` (sync; v0.7 Postgres impl will accept its own). `table_name` defaults to `"logs"` and mirrors `SQLHandler._table_name` so a chain writer can target a custom table when the host uses `setup(sql_table=...)`.
4. **`get_last_hash()` on empty chain** returns the **32-byte zero hash** (`b"\x00" * 32`). Empty = no row has a non-NULL `record_hash` (pre-chain backfilled rows from a Story 3.3 upgrade are treated as empty per Gap G1).
5. **`get_last_hash()` after one append** returns the `record_hash` of the most recent record (by `chain_pos DESC`).
6. **`append()` semantics** under SQLite:
   - Opens `BEGIN IMMEDIATE` (write lock acquired immediately, no SQLite "database is locked" surprises on concurrent reads).
   - Computes `next_chain_pos = COALESCE(MAX(chain_pos), 0) + 1` atomically INSIDE the same txn.
   - INSERTs the row with `chain_pos = next_chain_pos`, `record_hash`/`prev_hash` populated, and every other key from the `record` dict passed through verbatim (so `immutable=1` in the caller's dict flows through — Stories 3.5/3.6 use this).
   - Returns `next_chain_pos` as `int`.
   - Commits on context exit (`engine.begin()` semantics).
7. **`BEGIN IMMEDIATE` is wired via SQLAlchemy `do_begin` event** registered ONCE per engine in `SQLiteChainWriter.__init__`. Guard against duplicate registration via a sentinel attribute on the engine (`engine._ulog_chain_begin_immediate = True`). Multiple `SQLiteChainWriter` instances over the same engine must not stack BEGIN IMMEDIATE calls (would crash with "cannot start a transaction within a transaction").
8. **Mockability for chain-logic unit tests** — A `MagicMock(spec=ChainWriter)` (or any duck-typed double) must:
   - Pass `isinstance(mock, ChainWriter)` (proves `@runtime_checkable` works).
   - Allow `chain_writer.get_last_hash()` and `chain_writer.append(record, h, ph)` to be set up via standard `mock.return_value` API.
   - Cover the use case of Story 3.5/3.7 unit tests that mock chain operations without spinning up a SQLite DB.
9. **Lazy SQLAlchemy import** — `from sqlalchemy import text, event` lives inside methods (mirror the `ulog/handlers/sql.py` pattern at line 211). Module top-level imports only stdlib (`typing`, `__future__`).
10. **Type checking green** — `mypy --strict` passes for `ulog/_chain.py`. Use proper `dict[str, Any]` (3.10+ generic syntax).
11. **Concurrency safety** — Two `SQLiteChainWriter` instances sharing the same engine + two threads calling `append()` concurrently must produce monotonic, gap-free `chain_pos` values (1, 2, 3, ...) with no duplicates. Verified by a 2-thread × 50-iteration stress test.
12. **No behavioral regression on `SQLHandler`** — This story does NOT modify `ulog/handlers/sql.py`. The chain writer is a new module; integration into the handler is Story 3.5. All 26 `test_handlers.py` tests stay green.
13. **Tests** — at minimum (new file `tests/test_chain.py`):
    - `test_chain_writer_protocol_signature` — import `ChainWriter`, assert `get_last_hash` and `append` are defined, assert `isinstance(MagicMock(spec=ChainWriter), ChainWriter)` is True.
    - `test_sqlite_chain_writer_get_last_hash_empty_returns_zero` — fresh DB, no rows → zero hash.
    - `test_sqlite_chain_writer_get_last_hash_after_one_append` — append one record, get_last_hash returns that record's hash.
    - `test_sqlite_chain_writer_append_assigns_monotonic_chain_pos` — append 3 records, assert chain_pos values are 1, 2, 3.
    - `test_sqlite_chain_writer_append_preserves_record_fields` — pass `{"ts": ..., "level": "INFO", "msg": "x", "logger": "l", "file": "f.py", "line": 1, "immutable": 1}`, read back row, assert all fields land.
    - `test_sqlite_chain_writer_begin_immediate_registered_once` — instantiate 2 writers on same engine, inspect engine's `_sa_listeners` (or check sentinel `_ulog_chain_begin_immediate`); confirm only one listener.
    - `test_sqlite_chain_writer_concurrent_append_serialised` — 2 threads × 50 appends → 100 rows with chain_pos 1..100, no duplicates, no gaps.

## Tasks / Subtasks

- [ ] **Task 1 — Create `ulog/_chain.py`** (AC: 1, 2, 9, 10)
  - [ ] 1.1 — Module docstring referencing Decision B3 + the two extension points (v0.7 PostgresChainWriter, mock-based test path).
  - [ ] 1.2 — `from __future__ import annotations` + `from typing import Any, Protocol, runtime_checkable`. No top-level SQLAlchemy import.
  - [ ] 1.3 — Define `@runtime_checkable class ChainWriter(Protocol)`:
    - `def get_last_hash(self) -> bytes: ...`
    - `def append(self, record: dict[str, Any], record_hash: bytes, prev_hash: bytes) -> int: ...`
  - [ ] 1.4 — Define `class SQLiteChainWriter` (NOT inheriting `ChainWriter` — pure duck-typed conformance via Protocol):
    - `_ZERO_HASH: bytes = b"\x00" * 32` (class constant).
    - `__init__(self, engine: Any, table_name: str = "logs") -> None` — registers the `do_begin` event listener (guarded) and stores engine + table_name.
    - `get_last_hash(self) -> bytes` — SELECT the last non-NULL record_hash by chain_pos DESC; return zero on None.
    - `append(self, record, record_hash, prev_hash) -> int` — `engine.begin()`, next_pos via `COALESCE(MAX...)+1`, INSERT with all record fields + chain fields, return next_pos.
- [ ] **Task 2 — `BEGIN IMMEDIATE` event listener** (AC: 6, 7, 11)
  - [ ] 2.1 — Inside `__init__`, only when `engine.dialect.name == "sqlite"`:
    ```python
    if not getattr(engine, "_ulog_chain_begin_immediate", False):
        from sqlalchemy import event

        @event.listens_for(engine, "do_begin")
        def _do_begin_immediate(conn):
            conn.exec_driver_sql("BEGIN IMMEDIATE")

        engine._ulog_chain_begin_immediate = True
    ```
  - [ ] 2.2 — Engine sentinel survives the constructor exit → re-construction is a no-op. Verified by AC11's "registered once" test.
- [ ] **Task 3 — INSERT statement** (AC: 6)
  - [ ] 3.1 — Build INSERT dynamically from the record dict keys (caller-controlled column set). Required keys in `record` at minimum: `ts`, `level`, `logger`, `msg`, `file`, `line`. Optional: `exc`, `context`, `immutable`. The writer overrides `chain_pos`, `record_hash`, `prev_hash` from its own arguments.
  - [ ] 3.2 — Use `sqlalchemy.text()` with bound parameters (`:name` style) — never f-string-interpolate user data into SQL. The column-name and table-name interpolation IS f-string-safe because both come from internal callers (caller is `SQLHandler` or test code; never raw user input).
- [ ] **Task 4 — Tests in `tests/test_chain.py` (NEW FILE)** (AC: 13)
  - [ ] 4.1 — Module docstring: "Tests for ulog._chain — Story 3.4."
  - [ ] 4.2 — Shared fixture `_chain_engine(tmp_path)`: creates a SQLite DB, runs `SQLHandler(url)._ensure_schema()` to materialise the v0.5 schema (with triggers), returns the engine. NOTE: import `SQLHandler` only to bootstrap the schema; tests target `_chain.py` not the handler.
  - [ ] 4.3 — Tests per AC13 list. For the concurrency test, use `concurrent.futures.ThreadPoolExecutor(max_workers=2)` with 50 iterations each → 100 calls. Assert `set(chain_pos values) == set(range(1, 101))`.
  - [ ] 4.4 — Mock-protocol test uses `from unittest.mock import MagicMock` + `isinstance(MagicMock(spec=ChainWriter), ChainWriter)`.
- [ ] **Task 5 — Validation** (AC: 10, 12)
  - [ ] 5.1 — `pytest tests/test_chain.py` → 7 new tests pass.
  - [ ] 5.2 — `pytest tests/test_handlers.py` → 26 tests still green (no regression).
  - [ ] 5.3 — `pytest tests/` → full suite green (modulo pre-existing unrelated).
  - [ ] 5.4 — `mypy ulog/` → no issues (especially `ulog/_chain.py` typed properly).
  - [ ] 5.5 — `ruff check .` and `ruff format .` clean.
  - [ ] 5.6 — `python -m deptry .` clean (zero new deps).

## Dev Notes

### What this story is and is NOT

**IN scope:**
- New file `ulog/_chain.py` with `ChainWriter` Protocol + `SQLiteChainWriter` concrete impl.
- BEGIN IMMEDIATE via SQLAlchemy `do_begin` event listener registered once per engine.
- New test file `tests/test_chain.py` with 7 tests covering Protocol surface, basic semantics, and concurrent correctness.

**OUT of scope:**
- Wiring `SQLiteChainWriter` into `SQLHandler.emit()` → **Story 3.5**.
- WAL mode setup → **Story 3.5** (it's a separate engine-level pragma; the chain writer doesn't need it to be correct, just to be fast under concurrency).
- `setup(integrity='hash-chain', immutable_when=..., min_retention_days=...)` public API → **Story 3.6**.
- `ulog verify` / `ulog repair` CLI subcommands that walk the chain → **Stories 3.7 / 3.8**.
- Computing `record_hash` from the record content (canonical JSON serialisation) → that lives in `SQLHandler` per Story 3.5 (the writer just accepts a pre-computed hash).
- Postgres impl → **v0.7**.

### Files being modified — current state and required changes

#### `ulog/_chain.py` (NEW)

Net-new module. Follow this skeleton:

```python
"""Chain integrity backend abstraction (Decision B3).

A `ChainWriter` encapsulates the storage-side hash-chain append
semantics. v0.5 ships `SQLiteChainWriter`; v0.7 will add
`PostgresChainWriter` using `SELECT ... FOR UPDATE` instead of
`BEGIN IMMEDIATE`. The Protocol is `@runtime_checkable` so chain-
related tests can mock the backend without spinning up SQLite.
"""

from __future__ import annotations

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
    listener on the engine — registered once, idempotent).
    """

    _ZERO_HASH: bytes = b"\x00" * 32

    def __init__(self, engine: Any, table_name: str = "logs") -> None:
        self._engine = engine
        self._table_name = table_name
        if engine.dialect.name == "sqlite" and not getattr(
            engine, "_ulog_chain_begin_immediate", False
        ):
            from sqlalchemy import event

            @event.listens_for(engine, "do_begin")
            def _do_begin_immediate(conn: Any) -> None:
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
        with self._engine.begin() as conn:
            next_pos = conn.execute(
                text(
                    f"SELECT COALESCE(MAX(chain_pos), 0) + 1 "
                    f"FROM {self._table_name}"
                )
            ).scalar_one()
            row["chain_pos"] = int(next_pos)
            row["record_hash"] = record_hash
            row["prev_hash"] = prev_hash
            cols = list(row.keys())
            col_list = ", ".join(cols)
            placeholders = ", ".join(f":{c}" for c in cols)
            conn.execute(
                text(
                    f"INSERT INTO {self._table_name} ({col_list}) "
                    f"VALUES ({placeholders})"
                ),
                row,
            )
        return int(next_pos)
```

#### `tests/test_chain.py` (NEW)

```python
"""Tests for ulog._chain — Story 3.4 (ChainWriter Protocol + SQLite impl)."""

from __future__ import annotations

import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from ulog._chain import ChainWriter, SQLiteChainWriter
from ulog.handlers.sql import SQLHandler

# fixtures + 7 tests per AC13
```

### Architecture compliance — must follow

- **Decision B1 (Hash chain hook encapsulated in SQL handler, delegated to ChainWriter):** [Source: architecture.md, lines 362-370]
- **Decision B3 (ChainWriter abstraction now, SQLite v0.5 / Postgres v0.7):** [Source: architecture.md, lines 372-386]
- **Decision B2 (BEGIN IMMEDIATE + WAL):** WAL deferred to Story 3.5; BEGIN IMMEDIATE here. [Source: architecture.md, line 670]
- **Locked-out libraries:** No `alembic`, no `msgpack`, no `cryptography` — only stdlib `hashlib` (Story 3.5 will use SHA-256 from stdlib). [Source: architecture.md "Locked-out libraries"]
- **Enforcement rule #2 (Lazy SQLAlchemy imports):** `text` and `event` lazy-imported inside methods. Module top-level uses stdlib only. [Source: architecture.md, lines 779, 793]

### Library / framework requirements

- **Python 3.10+** — `typing.Protocol`, `typing.runtime_checkable`, PEP 604 generic syntax (`dict[str, Any]`).
- **SQLAlchemy ≥ 2.0** — `engine.begin()`, `text()`, `event.listens_for(engine, "do_begin")`, `conn.exec_driver_sql()`. All stable since 2.0.
- **Zero new deps** — chain writer is pure stdlib + existing SQLAlchemy from `[storage]` extra.

### Testing standards

- New test file `tests/test_chain.py`. Follow same `tmp_path` + `sqlite:///{path}` URL pattern as `test_handlers.py`.
- For Schema bootstrap: instantiate `SQLHandler(url)._ensure_schema()` and `handler.close()` to leave just the DB on disk; tests then create their own engine for chain writes.
- Concurrency test uses `ThreadPoolExecutor(max_workers=2)`. SQLite handles concurrent writes from multiple threads in the same process by serialising on the file lock — BEGIN IMMEDIATE makes that serialisation eager so the test is reliable.
- Protocol-mockability test uses `MagicMock(spec=ChainWriter)` — confirms duck typing + `@runtime_checkable` work as advertised.

### Previous-work intelligence — patterns established in this codebase

- **Lazy imports in handler-style modules** — established by `ulog/handlers/sql.py`. The chain module follows the same: stdlib at module level, SQLA inside methods.
- **Sentinel attribute on engine for one-time setup** — first instance. Same shape as `_ulog_managed` on handlers (`getattr(h, "_ulog_managed", False)` at `tests/test_handlers.py:27` and elsewhere). Documented as a viable pattern for ChainWriter init.
- **Test file naming** — `tests/test_chain.py` lines up with `ulog/_chain.py` (1:1 mapping is the convention — `tests/test_handlers.py` ↔ `ulog/handlers/`, etc.).

### Recent commits — context for upcoming work

Stories 3.1, 3.2, 3.3 just landed on `_verify_or_create_schema`. Story 3.4 introduces a NEW module orthogonal to `sql.py` — no merge risk with the recent changes.

### Project context reference

- Repo-wide guardrails: `_bmad-output/project-context.md` (zero runtime deps, mypy strict, SQLAlchemy under `[storage]` extra).
- Architecture: `architecture.md` §B1 (chain encapsulated in handler), §B3 (Protocol shape), §B2 (BEGIN IMMEDIATE + WAL).
- Epics: `epics.md` §Epic 3, Story 3.4 (lines 1091-1110).
- Previous stories: 3.1 (schema columns), 3.2 (triggers), 3.3 (upgrade message).

### References

- [Source: _bmad-output/planning-artifacts/epics.md, lines 1091-1110] — Story 3.4 acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 362-370] — Decision B1
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 372-386] — Decision B3 (Protocol shape)
- [Source: _bmad-output/planning-artifacts/architecture.md, line 670] — Decision B2 (BEGIN IMMEDIATE + WAL)
- [Source: ulog/handlers/sql.py, lines 115-127] — lazy SQLAlchemy import pattern (mirror in _chain.py)
- [Source: ulog/handlers/sql.py, lines 56-65] — module-level constants pattern (mirror for _ZERO_HASH)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m]

### Debug Log References

n/a — new module + stdlib types + standard SQLA patterns.

### Completion Notes List

- New module `ulog/_chain.py` with `@runtime_checkable ChainWriter`
  Protocol and concrete `SQLiteChainWriter` class. Stdlib-only imports
  at module level; SQLAlchemy lazy-imported inside methods (mirrors
  `ulog/handlers/sql.py` pattern).
- **BEGIN IMMEDIATE wiring corrected mid-cycle**: the initial spec
  used SQLAlchemy event name `do_begin`, which doesn't exist on the
  Engine in SQLAlchemy 2.x. Correct pattern (per SA SQLite dialect
  docs) is two listeners: `connect` to set
  `dbapi_conn.isolation_level = None` (suppress pysqlite's auto-BEGIN)
  + `begin` to emit our own `BEGIN IMMEDIATE`. First test run surfaced
  this as `InvalidRequestError: No such event 'do_begin'`; fix landed
  in `_chain.py` with both listeners registered behind the
  `_ulog_chain_begin_immediate` sentinel.
- Sentinel attribute `engine._ulog_chain_begin_immediate` on the
  SQLAlchemy Engine prevents duplicate listener registration when
  multiple `SQLiteChainWriter` instances target the same engine.
- 8 tests in `tests/test_chain.py` (1 above plan):
  Protocol/mockability, empty get_last_hash, get_last_hash after
  append, monotonic chain_pos, record fields preserved (incl.
  immutable=1 flow-through), sentinel-only-once, composition with
  Story 3.2 trigger (UPDATE blocked on immutable=1 from chain
  append), concurrent 2-thread×50-append serialisation.
- All 34 affected tests green (26 in test_handlers.py — no regression
  — + 8 new in test_chain.py). `mypy --strict` clean. `ruff check` +
  `ruff format` clean. `deptry` clean. Zero new PyPI deps.
- Python 3.12 DeprecationWarnings on the default datetime adapter
  (`cursor.execute(statement, parameters)`) are noise from SA + 3.12;
  not introduced by this story and not load-bearing.

### File List

- `ulog/_chain.py` (NEW) — `ChainWriter` Protocol + `SQLiteChainWriter`
  impl with `connect` + `begin` event listeners gated by engine
  sentinel.
- `tests/test_chain.py` (NEW) — 8 tests + `chain_engine` fixture +
  `_make_record` helper.
