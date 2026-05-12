# Story 4.2: `_REPLAY_ACTIVE` contextvar + `is_replaying()` + `is_replay=True` flag

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-2-replay-active-contextvar-is-replaying-flag`
**Implements:** FR99, NFR-REL-51, Gap G2 resolution.
**Built on:** Story 4.1 (`replay()` core), Story 3.1 (schema extension pattern), Story 3.3 (SchemaError upgrade message helper).
**Foundation for:** Story 4.9 (`replay_records` test context manager uses the same contextvar), Story 4.10 (replay-write-attempt edge case relies on the flag).

## Story

As an **observer of replay-emitted records**,
I want **any record emitted during a replay to be marked `is_replay=True` automatically** by the SQL handler at insert time,
so that **I can distinguish replay-induced records from production records** and prevent infinite-loop scenarios.

## Acceptance Criteria

1. **New module-level contextvar** `_REPLAY_ACTIVE: ContextVar[bool]` in `ulog/replay.py` with default `False`.
2. **`is_replaying() -> bool`** exported from `ulog/replay.py` (and re-exported as `ulog.is_replaying`). Reads `_REPLAY_ACTIVE.get(False)`. Returns `False` outside any replay context.
3. **`replay()` sets the contextvar at entry, restores at exit** (Gap G2). Uses `_REPLAY_ACTIVE.set(True)` to obtain a `Token`, then `_REPLAY_ACTIVE.reset(token)` in a `try/finally`. Works correctly under nested replays (inner sets True, outer's True is preserved on inner's reset).
4. **New column `logs.is_replay INTEGER NOT NULL DEFAULT 0`** (Decision A1 — INTEGER not BOOLEAN for SQL DDL clarity, mirrors `immutable`).
5. **`_CHAIN_COLUMN_ALTER_DDL` extended** with `is_replay` so Story 3.3's v0.4 → v0.5 upgrade message auto-includes it (deterministic alphabetical order: `chain_pos`, `immutable`, `is_replay`, `prev_hash`, `record_hash`).
6. **SQLHandler stamps `is_replay`** in `_record_to_row`: `row["is_replay"] = 1 if is_replaying() else 0`. Works in BOTH chain and non-chain modes.
7. **Chain canonical JSON includes `is_replay`** — same key set as `immutable`. Tamper-evidence preserved.
8. **Test count delta on existing v0.5 tests**: tests asserting `row == (0, 0, None, None)` for `(chain_pos, immutable, record_hash, prev_hash)` need updating where they introspect the full row — search/replace expected. Specifically: `test_sql_v05_default_values`, `test_integrity_none_string_runs_v04_compatible_path`.
9. **No regression in chain integrity** — Stories 3.4/3.5 chain emit + verify still pass. `record_hash` now hashes a 9-key dict (including `is_replay=0` on regular emits). Pre-Story-4.2 chain DBs verify-fail because the column-set differs; documented as a v0.5-internal-development progression (no v0.5 release yet, no real upgrade path needed).
10. **Tests** — `tests/test_replay_state.py` (NEW):
    - `test_is_replaying_false_outside_context`
    - `test_is_replaying_true_inside_replay_callback`
    - `test_is_replaying_returns_false_after_replay_completes`
    - `test_record_emitted_inside_replay_marked_is_replay_1`
    - `test_record_emitted_outside_replay_marked_is_replay_0`
    - `test_record_inside_replay_chain_mode_persists_is_replay_1`
    - `test_nested_replays_preserve_outer_state` (inner exits → outer still active)
    - `test_replay_raised_exception_resets_contextvar`
    - `test_v04_upgrade_message_now_includes_is_replay` (regression on Story 3.3's literal-SQL block)
    - `test_chain_hash_canonical_includes_is_replay` (canonical_record_json contains `"is_replay":0/1`)

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/replay.py` extend**
  - [ ] 1.1 — Add `from contextvars import ContextVar` import.
  - [ ] 1.2 — Define `_REPLAY_ACTIVE: ContextVar[bool] = ContextVar("_ulog_replay_active", default=False)`.
  - [ ] 1.3 — Define `def is_replaying() -> bool: return _REPLAY_ACTIVE.get(False)`.
  - [ ] 1.4 — In `replay()`, wrap iteration body in `token = _REPLAY_ACTIVE.set(True); try: ...; finally: _REPLAY_ACTIVE.reset(token)`.
- [ ] **Task 2 — Public export**
  - [ ] 2.1 — `from .replay import is_replaying, replay` in `ulog/__init__.py`. Add `is_replaying` to `__all__`.
- [ ] **Task 3 — SQLHandler `is_replay` stamping**
  - [ ] 3.1 — In `_record_to_row`, after the immutable_when block: `from ..replay import is_replaying; row["is_replay"] = 1 if is_replaying() else 0`.
  - [ ] 3.2 — Add `Column("is_replay", Integer, nullable=False, server_default="0")` to the `Table(...)` definition right after `immutable`. Add `Index(f"ix_{table}_is_replay", "is_replay")` so the records-list filter Story 4.x can use it without table scan.
- [ ] **Task 4 — Upgrade message extension**
  - [ ] 4.1 — Add `"is_replay": "ALTER TABLE {t} ADD COLUMN is_replay INTEGER NOT NULL DEFAULT 0;"` to `_CHAIN_COLUMN_ALTER_DDL`.
  - [ ] 4.2 — Add `"is_replay": "CREATE INDEX ix_{t}_is_replay ON {t}(is_replay);"` to `_CHAIN_COLUMN_INDEX_DDL`.
- [ ] **Task 5 — Update existing tests touching the column set**
  - [ ] 5.1 — `tests/test_handlers.py::test_sql_v05_default_values`: extend SELECT + assertion to include `is_replay` (expect 0).
  - [ ] 5.2 — `tests/test_handlers.py::test_sql_v05_schema_has_chain_and_immutable_columns`: assert `is_replay` is in the column set + `ix_logs_is_replay` index exists.
  - [ ] 5.3 — `tests/test_handlers.py::test_sql_v04_upgrade_path_raises_schema_error`: assert the new `ALTER TABLE … is_replay …` + `CREATE INDEX … ix_logs_is_replay …` are in the SchemaError message.
  - [ ] 5.4 — `tests/test_setup_v05_params.py::test_integrity_none_string_runs_v04_compatible_path`: extend expected row from `(0, 0, None, None)` to `(0, 0, None, None, 0)` (add `is_replay`).
  - [ ] 5.5 — `tests/test_chain.py::test_sqlite_chain_writer_append_preserves_record_fields`: pass `is_replay` through; verify it lands.
  - [ ] 5.6 — `tests/test_qa_epic3_e2e.py::TestSchemaErrorCopyPaste::test_sql_pasted_into_sqlite_executes_cleanly`: assertion on `len(statements) == 6` → bump to `7` (5 ALTERs + 2 CREATE INDEX; was 4+2).
  - [ ] 5.7 — Same file, `EXPECTED_ALTERS` and `EXPECTED_INDEXES` constants: add the `is_replay` ALTER + the new index.
- [ ] **Task 6 — Tests in `tests/test_replay_state.py` (NEW)**
  - [ ] 6.1 — 10 tests per AC10.
- [ ] **Task 7 — Validation**
  - [ ] 7.1 — pytest tests/ — full suite green.
  - [ ] 7.2 — mypy / ruff / deptry clean.

## Dev Notes

### What this story is and is NOT

**IN scope:**
- The contextvar + public `is_replaying()`.
- The schema column `is_replay`.
- SQL handler stamping at insert time.
- Story 3.3 upgrade message auto-extended via `_CHAIN_COLUMN_ALTER_DDL`.
- Existing tests updated for the new column set.

**OUT of scope:**
- `replay()` rejecting WRITE attempts during callback execution → Story 4.10.
- `replay_records` test context manager → Story 4.9.
- Records-list filter axis `?is_replay=0|1` → Story 4.x or v0.5 UI epic.

### Architecture compliance

- **Decision A1 (Storage shape):** INTEGER not BOOLEAN. Mirrors `immutable` from Story 3.1.
- **Gap G2 resolution:** [Source: architecture.md, line 1258]. Contextvar in `ulog/replay.py`.
- **FR99:** SQL handler stamps at insert time, NOT at emit time. (Subtle — the v0.5 record_hash includes `is_replay`, so the value must be set before hashing. In our code `_record_to_row` already runs before chain_writer.append, so timing works.)
- **NFR-REL-51:** Replay-induced records distinguishable from production. The flag is the contract.

### Concurrency note

`ContextVar` is the right primitive for this (not a thread-local or a global) because:
- `replay()` is a sync function; the contextvar is set/reset around its body.
- A callback that schedules an asyncio task inheriting the context will see `is_replaying()=True` correctly.
- A callback that spawns a new thread WILL NOT inherit (Python's contextvar semantics). Documented as a v0.5 limitation; threads inside callbacks don't get the replay flag.

### Snippet — concurrent contextvar handling

```python
# ulog/replay.py (excerpts)
from contextvars import ContextVar, Token

_REPLAY_ACTIVE: ContextVar[bool] = ContextVar("_ulog_replay_active", default=False)


def is_replaying() -> bool:
    """True iff the current context is inside a `replay()` body."""
    return _REPLAY_ACTIVE.get(False)


def replay(db_path, *, where=None, where_fn=None, on, order="chain") -> int:
    # ... existing arg validation + URL resolution ...
    token = _REPLAY_ACTIVE.set(True)
    try:
        count = 0
        # ... existing iteration ...
        return count
    finally:
        _REPLAY_ACTIVE.reset(token)
```

### SQLHandler stamping snippet

```python
# ulog/handlers/sql.py:_record_to_row (excerpts, after the immutable_when block):
from ..replay import is_replaying
row["is_replay"] = 1 if is_replaying() else 0
return row
```

### References

- [Source: epics.md, lines 1329-1348] — Story 4.2 AC
- [Source: architecture.md, line 1258] — Gap G2 resolution
- [Source: docs/prds/PRD-v0.5-forensic-archive.md] — FR99 + NFR-REL-51
- [Source: ulog/handlers/sql.py:_CHAIN_COLUMN_ALTER_DDL] — extension point for the schema migration message
- [Python `contextvars.ContextVar`] — chosen primitive

## Dev Agent Record

### Completion Notes List

- `_REPLAY_ACTIVE: ContextVar[bool]` + `is_replaying()` in
  `ulog/replay.py`. Set/reset via `Token` in `try/finally` so nested
  replays + callback exceptions both restore the prior state
  correctly (tested).
- Schema: new column `logs.is_replay INTEGER NOT NULL DEFAULT 0` +
  index `ix_logs_is_replay`. Added to `_CHAIN_COLUMN_ALTER_DDL`
  + `_CHAIN_COLUMN_INDEX_DDL` so Story 3.3's upgrade message
  auto-extends.
- `SQLHandler._record_to_row` stamps `row["is_replay"] = 1 if
  is_replaying() else 0`. Works in BOTH non-chain and chain emit
  paths (the chain hash now includes `is_replay` in the canonical
  dict).
- **Cross-cutting fix surfaced during testing**: `cmd_verify.run`
  and `cmd_repair._find_first_break` reconstruct the rec dict from
  SELECT for chain hash recomputation. The dict was missing
  `is_replay`, so hashes wouldn't match post-Story-4.2 chains.
  Fixed both — SELECT now pulls `is_replay`, rec dict includes
  `"is_replay": row[12]`.
- Public namespace: `ulog.is_replaying` + `ulog.replay` exported,
  `__all__` updated.
- 10 / 10 tests in `tests/test_replay_state.py` green: false
  outside / true inside / reset after / nested preservation /
  exception reset / is_replay=0 on plain emit / is_replay=1 inside
  replay (non-chain) / is_replay=1 inside replay (chain mode +
  chain link valid) / canonical JSON includes `"is_replay":1` /
  upgrade message regression.
- 169 affected-area tests green across replay + handlers + chain +
  setup_v05 + cli_verify/repair/purge + verify_state + qa_epic3_e2e
  (post column-set updates).
- mypy --strict / ruff check / ruff format / deptry all clean.

### File List

- `ulog/replay.py` — `_REPLAY_ACTIVE` ContextVar + `is_replaying()`
  + `try/finally` token-reset around iteration.
- `ulog/handlers/sql.py` — `is_replay` column + index + stamping
  in `_record_to_row`. `_CHAIN_COLUMN_ALTER_DDL` +
  `_CHAIN_COLUMN_INDEX_DDL` extended.
- `ulog/__init__.py` — `is_replaying` export + `__all__`.
- `ulog/_cli/cmd_verify.py` — SELECT + rec dict include `is_replay`.
- `ulog/_cli/cmd_repair.py` — same.
- `tests/test_handlers.py` — column-set assertions + upgrade-message
  statement-count bumped 6 → 8 + non-chain test fixture updated.
- `tests/test_setup_v05_params.py` — expected row updated.
- `tests/test_qa_epic3_e2e.py` — `EXPECTED_ALTERS` / `EXPECTED_INDEXES`
  + `len(statements) == 8` bump.
- `tests/test_replay_state.py` (NEW) — 10 tests.
