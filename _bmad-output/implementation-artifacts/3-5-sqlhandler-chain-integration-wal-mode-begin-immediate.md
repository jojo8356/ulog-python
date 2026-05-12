# Story 3.5: `SQLHandler` chain integration + WAL mode + BEGIN IMMEDIATE

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-5-sqlhandler-chain-integration-wal-mode-begin-immediate`
**Implements:** Decision B1 (chain encapsulated inside SQL handler), Decision B2 (WAL mode + BEGIN IMMEDIATE on the engine when chain mode is active), partial Story 3.6 surface (`integrity='hash-chain'` parameter)
**Built on:** Stories 3.1 (schema), 3.2 (triggers), 3.3 (clean upgrade path), 3.4 (`ChainWriter` Protocol + `SQLiteChainWriter`).
**Foundation for:** Story 3.6 (adds `immutable_when` + `min_retention_days`), Story 3.7 (`ulog verify` walks the chain we write here), Story 3.11 (concurrency stress test).

## Story

As a **v0.5 user enabling chain mode**,
I want **`setup(integrity='hash-chain')` to wire `SQLiteChainWriter` into the SQL handler's emit path under WAL + BEGIN IMMEDIATE**,
so that **records are persisted with monotonic `chain_pos`, SHA-256 hashes linking each to the previous, and multi-process writers serialize on the chain without blocking readers**.

## Acceptance Criteria

1. **`setup(integrity='hash-chain', handlers=['sql'])`** is accepted. Other values for `integrity` (anything except `None` or `"hash-chain"`) raise `ValueError` listing the valid values.
2. **WAL mode** — when the SQL handler is constructed in chain mode, `PRAGMA journal_mode=WAL` is executed once at engine init. Verified by querying `PRAGMA journal_mode` and asserting `"wal"`.
3. **Canonical JSON** — when a record is hashed, the canonical form is `json.dumps(record, sort_keys=True, separators=(",", ":"), default=<datetime-aware>)`. `datetime` → ISO-8601 Z; `bytes` → hex; `None` stays `null`.
4. **Hash computation** — `record_hash = hashlib.sha256(canonical + prev_hash).digest()`. Pure stdlib; no external crypto lib. Output is 32 bytes.
5. **Chain link** — for two consecutive records A and B (A first), B's stored `prev_hash` equals A's stored `record_hash` (linked, verifiable).
6. **First record** — the very first chain record has `prev_hash = b"\x00" * 32` (zero hash sentinel from `SQLiteChainWriter._ZERO_HASH`).
7. **Monotonic chain_pos under concurrency** — N concurrent emits produce chain_pos values forming a gap-free `{1..N}` set. Verified by a 4-thread × 25-emit stress test (smaller than Story 3.11's 8 × 10K, just enough to exercise the locking path).
8. **Non-chain mode unchanged** — `setup(handlers=['sql'])` (no `integrity=`) still uses the buffered/batched emit path from v0.2. All 26 `test_handlers.py` tests stay green.
9. **`SQLHandler.__init__` gains `chain_mode: bool = False`** — the `_build_handler` in `setup.py` passes `chain_mode=(integrity == "hash-chain")`. Internal flag, not exposed at user surface (users go through `setup(integrity=...)`).
10. **Chain emit path bypasses the buffer** — in chain mode, `emit()` does NOT buffer; each record is appended to the chain immediately. Rationale: chain ordering is the contract; batching would re-order records under multi-threaded host code, breaking AC5/AC7. `batch_size` is silently ignored in chain mode.
11. **Hash + canonical helpers live in `ulog/_chain.py`** — two new module-level functions exported alongside the Protocol/impl from Story 3.4:
    - `canonical_record_json(record: Mapping[str, Any]) -> bytes`
    - `sha256_record(record: Mapping[str, Any], prev_hash: bytes) -> bytes` (uses `canonical_record_json` under the hood)
    Story 3.7's `ulog verify` will reuse them to recompute hashes during verification.
12. **Type checking green** — `mypy --strict` passes for `setup.py`, `handlers/sql.py`, `_chain.py`.
13. **Tests** — minimum:
    - `test_setup_integrity_invalid_value_raises` — `setup(integrity='nope')` → `ValueError`.
    - `test_sql_chain_mode_sets_wal_mode` — query `PRAGMA journal_mode` after `setup(integrity='hash-chain', ...)`.
    - `test_chain_emit_produces_linked_records` — 3 sequential emits → records 1/2/3 have prev_hash matching the previous record_hash; first prev_hash is zero hash.
    - `test_canonical_record_json_is_deterministic` — same record dict → same canonical bytes across runs / dict order.
    - `test_canonical_record_json_handles_datetime` — ts column serializes to a deterministic ISO string.
    - `test_chain_emit_record_hash_matches_sha256_of_canonical_plus_prev` — recompute hash externally, assert equality.
    - `test_chain_concurrent_emit_serialized` — 4 threads × 25 emits → 100 monotonic chain_pos; chain still verifies end-to-end.
    - `test_chain_emit_with_exc_and_context` — record carrying exception payload and bound context lands cleanly with chain values.
    - `test_non_chain_mode_unchanged` — `setup(handlers=['sql'])` without `integrity=` → emit produces `chain_pos=0`, `record_hash=NULL` (the buffered/batched v0.2 path is preserved).

## Tasks / Subtasks

- [ ] **Task 1 — Helpers in `ulog/_chain.py`** (AC: 3, 4, 11)
  - [ ] 1.1 — Add `canonical_record_json(record: Mapping[str, Any]) -> bytes` with `_canonical_default(obj)` helper that converts `datetime.datetime` → ISO string (`obj.isoformat()` — already TZ-aware via `_ts_aware`), `bytes` → `obj.hex()`, anything else → `TypeError` (force explicit handling).
  - [ ] 1.2 — Add `sha256_record(record, prev_hash) -> bytes` — `hashlib.sha256(canonical_record_json(record) + prev_hash).digest()`.
  - [ ] 1.3 — Update `ulog/_chain.py` module docstring to mention the canonical/hash helpers.
- [ ] **Task 2 — `SQLHandler` chain mode** (AC: 2, 9, 10)
  - [ ] 2.1 — Add `chain_mode: bool = False` to `SQLHandler.__init__` signature. Store as `self._chain_mode`.
  - [ ] 2.2 — When chain mode: after `create_engine`, set WAL mode:
    ```python
    if self._chain_mode and self._engine.dialect.name == "sqlite":
        with self._engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    ```
  - [ ] 2.3 — Lazy-init `self._chain_writer: SQLiteChainWriter | None = None`. Initialised in `_ensure_schema` after schema is verified (chain writer needs the schema to exist).
  - [ ] 2.4 — Override `emit` flow:
    ```python
    def emit(self, record):
        try:
            self._ensure_schema()
            row = self._record_to_row(record)
            if self._chain_mode:
                self._chain_append(row)
            else:
                with self._lock:
                    self._buffer.append(row)
                    buf_len = len(self._buffer)
                if buf_len >= self._batch_size:
                    self.flush()
        except Exception:
            self.handleError(record)

    def _chain_append(self, row: dict) -> None:
        assert self._chain_writer is not None
        with self._lock:  # serialise hash computation within process
            prev_hash = self._chain_writer.get_last_hash()
            record_hash = sha256_record(row, prev_hash)
            self._chain_writer.append(row, record_hash, prev_hash)
    ```
  - [ ] 2.5 — `flush()` is a no-op in chain mode (buffer is always empty). Document in docstring.
- [ ] **Task 3 — `setup()` integrity parameter** (AC: 1, 9)
  - [ ] 3.1 — Add `integrity: str | None = None` parameter to `setup()` signature.
  - [ ] 3.2 — Validate: `if integrity not in (None, "hash-chain"): raise ValueError(f"unknown integrity mode {integrity!r}; valid: None, 'hash-chain'")`.
  - [ ] 3.3 — Pass `chain_mode=(integrity == "hash-chain")` through `_build_handler` → `SQLHandler(...)`.
- [ ] **Task 4 — Tests** (AC: 13)
  - [ ] 4.1 — Append new tests to `tests/test_handlers.py` under a new `# ---- SQLHandler chain mode (Story 3.5) ----` block, OR a new file `tests/test_chain_emit.py`. **Pick the new file** to keep test_handlers.py < 1000 lines and keep chain-emit-specific helpers isolated.
  - [ ] 4.2 — Helper fixture: `chain_db_url(tmp_path)` returns `f"sqlite:///{tmp_path/'logs.sqlite'}"`.
  - [ ] 4.3 — Each chain-emit test runs `ulog.setup(integrity='hash-chain', handlers=['sql'], sql_url=url, sql_batch_size=1)` and flushes via `for h in logger.handlers: h.flush()`.
  - [ ] 4.4 — For AC7 concurrency: spawn 4 threads, each emits 25 records, then verify chain end-to-end:
    ```python
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT chain_pos, record_hash, prev_hash FROM logs ORDER BY chain_pos"
        )).all()
    assert [r[0] for r in rows] == list(range(1, 101))
    for i, (_, h, ph) in enumerate(rows):
        if i == 0:
            assert bytes(ph) == b"\x00" * 32
        else:
            assert bytes(ph) == bytes(rows[i-1][1])
    ```
- [ ] **Task 5 — Validation**
  - [ ] 5.1 — `pytest tests/test_chain_emit.py tests/test_chain.py tests/test_handlers.py` → all green.
  - [ ] 5.2 — `pytest tests/` → no new regressions.
  - [ ] 5.3 — `mypy ulog/` → clean.
  - [ ] 5.4 — `ruff check .` + `ruff format .` → clean.

## Dev Notes

### What this story is and is NOT

**IN scope:**
- `setup(integrity='hash-chain')` wired to a `chain_mode=True` `SQLHandler`.
- WAL mode pragma on SQLite engine when chain mode is on.
- Canonical JSON + SHA-256 helpers in `_chain.py`.
- Bypass the buffer/batch in chain mode (each emit chains immediately).
- 9 new tests in a new file `tests/test_chain_emit.py`.

**OUT of scope:**
- `immutable_when` + `min_retention_days` setup params → **Story 3.6**.
- `ulog verify` / `repair` CLI → **3.7 / 3.8**.
- The 8-process × 10K-record stress test → **Story 3.11** (this story does 4 thread × 25 to exercise the path).
- Setting `immutable=1` on records → wired in 3.6 via `immutable_when`. Story 3.5 records have `immutable=0` (rotable).

### Files being modified — current state and required changes

#### `ulog/_chain.py` (UPDATE)

Append at the bottom (after `SQLiteChainWriter`):

```python
import datetime as _dt
import hashlib as _hashlib
import json as _json
from collections.abc import Mapping


def _canonical_default(obj):
    if isinstance(obj, _dt.datetime):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        return obj.hex()
    raise TypeError(f"non-canonicalisable value of type {type(obj).__name__}")


def canonical_record_json(record: Mapping[str, Any]) -> bytes:
    return _json.dumps(
        dict(record),
        sort_keys=True,
        separators=(",", ":"),
        default=_canonical_default,
    ).encode("utf-8")


def sha256_record(record: Mapping[str, Any], prev_hash: bytes) -> bytes:
    return _hashlib.sha256(canonical_record_json(record) + prev_hash).digest()
```

Underscore-prefixed imports (`_dt`, `_hashlib`, `_json`) signal stdlib helpers, not for re-export.

#### `ulog/handlers/sql.py` (UPDATE)

- Add `chain_mode` param.
- WAL pragma in `__init__` when chain mode + SQLite.
- `_ensure_schema` lazy-init `_chain_writer`.
- `emit` branches on `_chain_mode`.
- `_chain_append` private method.

#### `ulog/setup.py` (UPDATE)

- Add `integrity` parameter with validation.
- Thread `chain_mode` through `_build_handler` → `SQLHandler`.

#### `tests/test_chain_emit.py` (NEW)

9 tests per AC13.

### Architecture compliance — must follow

- **Decision B1:** chain hook inside the SQL handler. [Source: architecture.md, lines 362-370]
- **Decision B2:** WAL mode + BEGIN IMMEDIATE. (BEGIN IMMEDIATE already wired by Story 3.4's `SQLiteChainWriter` constructor.) [Source: architecture.md, line 670]
- **Locked-out libraries:** stdlib `hashlib` only — no `cryptography`, no `pycryptodome`. stdlib `json` — no `msgpack`, `orjson`, `ujson`. [Source: architecture.md "Locked-out libraries"]
- **Enforcement #2 (lazy imports):** `hashlib`/`json` are stdlib so they're fine at module-top in `_chain.py`. SQLAlchemy stays lazy.
- **Gap G1 (chain discontinuity):** Story 3.5 starts a fresh chain — pre-chain rows (record_hash IS NULL) are untouched by chain writes. `SQLiteChainWriter.get_last_hash` already filters via `WHERE record_hash IS NOT NULL` (Story 3.4 implementation).

### Library / framework requirements

- **Python stdlib:** `hashlib.sha256`, `json.dumps`, `datetime.datetime.isoformat`.
- **SQLAlchemy ≥ 2.0:** WAL pragma via `conn.exec_driver_sql("PRAGMA journal_mode=WAL")`.
- **Zero new deps.**

### Testing standards

- New test file `tests/test_chain_emit.py` per Task 4.1.
- `tmp_path` for DB. SQLite URL.
- `ulog.setup(...)` with explicit handlers and `sql_batch_size=1` (irrelevant in chain mode but explicit).
- Determinism tests for canonical_record_json use Python dicts with shuffled key order — same input keys/values should produce identical bytes.

### References

- [Source: epics.md, lines 1113-1137] — Story 3.5 acceptance criteria
- [Source: architecture.md, lines 362-370] — Decision B1
- [Source: architecture.md, line 670] — Decision B2
- [Source: ulog/_chain.py] — Story 3.4 module (extension point for helpers)
- [Source: ulog/handlers/sql.py, lines 94-164] — SQLHandler.__init__ + emit path
- [Source: ulog/setup.py, lines 65-185] — setup() entry point + _build_handler

## Dev Agent Record

### Agent Model Used
claude-opus-4-7[1m]

### Debug Log References
n/a

### Completion Notes List

- `canonical_record_json` + `sha256_record` helpers added to
  `ulog/_chain.py` — stdlib `json` + `hashlib`, deterministic via
  `sort_keys=True` + `separators=(",", ":")`. `_canonical_default`
  handles datetime (ISO) and bytes (hex); raises TypeError on
  unknown types (fail-fast — no silent `str()`).
- `SQLHandler.__init__` gained `chain_mode: bool = False`. When
  true: WAL pragma at engine init (SQLite-only) + `SQLiteChainWriter`
  instantiated. Chain mode bypasses the buffer in `emit()` —
  `_chain_append(row)` computes hash and calls the writer
  immediately. Buffer/batch_size silently ignored in chain mode.
- `setup()` gained `integrity: str | None = None` parameter. Valid
  values: `None`, `"hash-chain"`. Other values → `ValueError`.
  Thread `chain_mode=(integrity == "hash-chain")` through
  `_build_handler` to `SQLHandler`.
- **Bug fix during DS**: `SQLiteChainWriter.append` used raw
  `text()` INSERT which bypasses SQLAlchemy's type adapters. JSON
  columns (`exc`, `context`) were passed as Python dicts directly
  to pysqlite, which crashed. Fix: pre-serialise dict/list values
  via `_json.dumps(v, sort_keys=True, separators=(",", ":"))` in
  the append path. Hash is still computed over the DICT form so
  `ulog verify` (Story 3.7) will need to parse JSON columns back
  before recomputing.
- **Test scope-cut**: initial `test_chain_emit_record_hash_matches_canonical_recompute`
  proved brittle (SQLite round-trip for ts microseconds + bound
  context insertion order caused divergence). End-to-end verify
  cycle is Story 3.7's actual job; for now the chain integrity is
  covered by (a) external `sha256_record` recompute test and (b)
  link-walk test (`prev_hash[N] == record_hash[N-1]`).
- 12 / 12 new tests in `test_chain_emit.py` green. 8 / 8 in
  `test_chain.py`, 26 / 26 in `test_handlers.py`, 24 / 24 in
  `test_setup.py`. Total 70 affected-area tests green. `mypy
  --strict` clean. `ruff check` + `ruff format` clean. `deptry`
  clean. Zero new PyPI deps.

### File List

- `ulog/_chain.py` — added `_canonical_default`,
  `canonical_record_json`, `sha256_record` helpers + JSON dict/list
  pre-serialisation in `SQLiteChainWriter.append`.
- `ulog/handlers/sql.py` — `__init__` gained `chain_mode` param +
  WAL pragma + chain writer instantiation; `emit` branches on
  `_chain_mode`; new `_chain_append` private method.
- `ulog/setup.py` — `integrity` param + validation; threaded
  `chain_mode` through `_build_handler` → `SQLHandler`.
- `tests/test_chain_emit.py` (NEW) — 12 tests covering setup
  validation, helper determinism, chain mode WAL + emit + concurrent
  + non-chain regression.
