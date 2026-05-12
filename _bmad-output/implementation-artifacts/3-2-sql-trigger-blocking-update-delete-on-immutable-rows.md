# Story 3.2: SQL trigger blocking UPDATE/DELETE on immutable rows

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-2-sql-trigger-blocking-update-delete-on-immutable-rows`
**Implements:** FR91 (invariant I4 — immutable records uncuttable through any path)
**Source:** PRD-v0.5 §3.1 (Storage & immutability), Decision A1 (column-flag single table + trigger blocks UPDATE/DELETE on immutable=1)
**Built on:** Story 3.1 (schema extension — `immutable INTEGER NOT NULL DEFAULT 0` column landed in the `Table` definition, indexes `ix_logs_chain_pos` and `ix_logs_immutable` exist)
**Foundation for:** Story 3.4 (`ChainWriter` Protocol — needs the trigger as the bottom-of-stack enforcement to be honest about immutability guarantees), Story 3.7 (`ulog verify` — relies on the trigger blocking tampering between writes and verification), Story 3.8 (`ulog repair` — must archive orphans, never UPDATE/DELETE immutable rows)

## Story

As a **compliance officer (Erika persona)** running ULog as part of a forensic archive,
I want **a SQL trigger to block any UPDATE or DELETE on a row where `immutable=1`**,
so that **invariant I4 is enforced at the storage layer — regardless of which client connects to the DB** (the application, an external sqlite3 shell, a forgotten Django admin, a malicious actor with read/write file access).

## Acceptance Criteria

1. **Trigger DDL created on fresh DB** — Given a fresh SQLite DB, when `SQLHandler._ensure_schema()` fires on first emit, then `sqlite_master` contains two triggers: `trg_logs_block_update_immutable` (BEFORE UPDATE) and `trg_logs_block_delete_immutable` (BEFORE DELETE). Both are scoped `FOR EACH ROW` and guarded by `WHEN OLD.immutable = 1`.
2. **Trigger DDL created on existing v0.5 DB** — Given an existing v0.5 SQLite DB (table exists, columns match, but no triggers yet — e.g., DB created by 3.1 code that pre-dated 3.2), when `_verify_or_create_schema` runs, then the same two triggers are installed via `CREATE TRIGGER IF NOT EXISTS`. The existing-table branch (line 218+ of `ulog/handlers/sql.py`) must also install triggers, not only the fresh-create branch.
3. **UPDATE blocked on immutable=1 row** — Given a row inserted via raw SQL with `immutable=1`, when any client runs `UPDATE logs SET msg='tampered' WHERE id=<n>`, then SQLAlchemy raises an `IntegrityError` (mapped from SQLite `RAISE(ABORT, ...)`), the transaction is rolled back, and a subsequent `SELECT msg FROM logs WHERE id=<n>` returns the original message unchanged.
4. **DELETE blocked on immutable=1 row** — Same as AC3 but for `DELETE FROM logs WHERE id=<n>`. The row is still present after the failed DELETE.
5. **UPDATE allowed on immutable=0 row** — Given a row with `immutable=0` (the default — rotable), when `UPDATE logs SET msg='rotated' WHERE id=<n>` runs, then the operation succeeds and `SELECT msg` returns `'rotated'`. Story 3.9 (`ulog purge --before <date>`) depends on this — must not break.
6. **DELETE allowed on immutable=0 row** — Same as AC5 but for DELETE. The row is gone after the operation.
7. **Trigger error message identifies the invariant** — The error raised by the trigger contains the literal string `immutable row` and a reference to `I4` so that downstream operators reading log noise can grep for the cause (e.g. `immutable row: UPDATE forbidden (invariant I4)`).
8. **Idempotent re-bootstrap** — Given a SQLHandler instance is constructed twice against the same v0.5 DB (mirror of multi-process bootstrap covered for tables by Story 1.13), when both call `_verify_or_create_schema()`, then no `OperationalError("trigger already exists")` surfaces. `CREATE TRIGGER IF NOT EXISTS` handles this — no try/except needed for the trigger path.
9. **Dialect-gated** — The trigger DDL uses SQLite-specific `RAISE(ABORT, ...)` syntax. Implementation must inspect `self._engine.dialect.name == "sqlite"` and only install triggers when true. Other dialects (e.g. a future Postgres path per Decision B3) skip silently. **No** runtime warning when skipping — the architecture explicitly defers the Postgres trigger equivalent to v0.7.
10. **No behavioral regression** — All 290+ existing tests stay green (the 287 pre-3.1 + the 3 v0.5 schema tests added by 3.1). Insertion path of `SQLHandler.flush()` is untouched.
11. **Type checking green** — `mypy --strict` passes for `ulog/handlers/sql.py`. New tests pass `mypy` too (annotations on fixtures + return types where applicable).
12. **Tests** — at minimum (in `tests/test_handlers.py`, appended after `test_sql_v04_upgrade_path_raises_schema_error` around line 419):
    - `test_sql_v05_triggers_created_on_fresh_db` — fresh DB, after one emit, inspect `sqlite_master` for both trigger names + assert their SQL bodies contain `BEFORE UPDATE` / `BEFORE DELETE` / `OLD.immutable = 1`.
    - `test_sql_v05_trigger_blocks_update_on_immutable_row` — insert one row with `immutable=1` via raw SQL, attempt UPDATE → expect `IntegrityError` (or `OperationalError` — accept either to stay tolerant to SQLAlchemy version drift), verify msg is unchanged.
    - `test_sql_v05_trigger_blocks_delete_on_immutable_row` — same, DELETE path, verify row still present.
    - `test_sql_v05_trigger_allows_update_on_rotable_row` — insert with `immutable=0`, UPDATE succeeds.
    - `test_sql_v05_trigger_allows_delete_on_rotable_row` — insert with `immutable=0`, DELETE succeeds.
    - `test_sql_v05_triggers_idempotent_on_double_bootstrap` — instantiate two `SQLHandler(url=...)` against same URL, call `_ensure_schema()` on both, no exception.

## Tasks / Subtasks

- [ ] **Task 1 — Install triggers in `_verify_or_create_schema`** (AC: 1, 2, 8, 9)
  - [ ] 1.1 — After `self._metadata.create_all(self._engine)` succeeds (line 209) AND after the existing-table column-verify passes (line 227), call a new private method `self._install_immutable_triggers()`. Both paths must reach it — fresh DBs and existing v0.5 DBs.
  - [ ] 1.2 — Implement `_install_immutable_triggers(self) -> None`:
    - Return early if `self._engine.dialect.name != "sqlite"` (Decision A1 gates trigger to SQLite for v0.5; Postgres v0.7 will use a different mechanism).
    - Open `with self._engine.begin() as conn:` and `conn.execute(text(...))` twice — one per trigger DDL.
    - DDL uses `CREATE TRIGGER IF NOT EXISTS` for idempotency (AC8); no try/except needed.
  - [ ] 1.3 — Trigger DDL — use these exact strings (the error wording is part of AC7):
    ```sql
    CREATE TRIGGER IF NOT EXISTS trg_{table}_block_update_immutable
    BEFORE UPDATE ON {table}
    FOR EACH ROW
    WHEN OLD.immutable = 1
    BEGIN
        SELECT RAISE(ABORT, 'immutable row: UPDATE forbidden (invariant I4)');
    END;
    ```
    ```sql
    CREATE TRIGGER IF NOT EXISTS trg_{table}_block_delete_immutable
    BEFORE DELETE ON {table}
    FOR EACH ROW
    WHEN OLD.immutable = 1
    BEGIN
        SELECT RAISE(ABORT, 'immutable row: DELETE forbidden (invariant I4)');
    END;
    ```
    `{table}` is `self._table_name` (defaults to `"logs"`). The trigger names follow the existing `ix_{table}_*` index pattern → `trg_{table}_block_{update,delete}_immutable`.
  - [ ] 1.4 — Import `text` lazily into the existing SQLAlchemy lazy-import block at lines 98-110 (Enforcement rule #2 — never module-top-level for SQLA).
- [ ] **Task 2 — Tests** (AC: 12)
  - [ ] 2.1 — Append the 6 new tests to `tests/test_handlers.py` after line 419 (right after `test_sql_v04_upgrade_path_raises_schema_error`).
  - [ ] 2.2 — Test pattern for trigger-presence — use `sqlite_master`:
    ```python
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' AND tbl_name='logs'"
            )
        ).all()
    names = {r[0] for r in rows}
    assert "trg_logs_block_update_immutable" in names
    assert "trg_logs_block_delete_immutable" in names
    ```
  - [ ] 2.3 — Test pattern for block-on-immutable — insert via raw SQL (NOT through SQLHandler.emit which only sets `immutable=0`):
    ```python
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO logs (ts, level, logger, msg, file, line, immutable, chain_pos) "
                "VALUES ('2026-05-12 00:00:00', 'INFO', 'test', 'sealed', 'x.py', 1, 1, 0)"
            )
        )
    with pytest.raises((IntegrityError, OperationalError)) as excinfo:
        with engine.begin() as conn:
            conn.execute(text("UPDATE logs SET msg='tampered' WHERE id=1"))
    assert "immutable row" in str(excinfo.value)
    # Verify rollback
    with engine.begin() as conn:
        row = conn.execute(text("SELECT msg FROM logs WHERE id=1")).first()
    assert row[0] == "sealed"
    ```
  - [ ] 2.4 — Test pattern for idempotent re-bootstrap — `SQLHandler(url=url)._ensure_schema()` twice in a row, no exception. Different from Story 1.13's multi-process race test (which is `OperationalError("table already exists")` on `create_all`); this is `CREATE TRIGGER IF NOT EXISTS` covering the trigger-already-exists race.
  - [ ] 2.5 — Import line for the new tests: `from sqlalchemy.exc import IntegrityError, OperationalError` — add to the test file's existing imports (look near top of test_handlers.py; sqlalchemy is already used so the import is local-friendly).
- [ ] **Task 3 — Validation** (AC: 10, 11)
  - [ ] 3.1 — Run `pytest tests/` — all prior tests green + 6 new tests pass.
  - [ ] 3.2 — Run `mypy ulog/` — `Success: no issues found`.
  - [ ] 3.3 — Run `ruff check . && ruff format . --check` — both clean.
  - [ ] 3.4 — Run `python -m deptry .` — no new dep issues (this story adds zero PyPI deps).

## Dev Notes

### What this story is and is NOT

**IN scope (this story):**
- Two SQLite triggers (`BEFORE UPDATE` + `BEFORE DELETE`) installed via `CREATE TRIGGER IF NOT EXISTS` after schema bootstrap.
- Dialect gate (SQLite-only — Postgres path deferred to v0.7 per Decision B3).
- 6 new tests covering: trigger presence on fresh DB, block UPDATE on immutable, block DELETE on immutable, allow UPDATE on rotable, allow DELETE on rotable, idempotent re-bootstrap.

**OUT of scope (other Epic 3 stories — do NOT implement here):**
- Setting `immutable=1` on chain rows → **Story 3.5** (the `ChainWriter` will set it at INSERT time when `setup(integrity='hash-chain', immutable_when=...)` is wired in Story 3.6).
- v0.4 → v0.5 SchemaError wording with literal ALTER TABLE — already partially in 3.1; refined in **Story 3.3**.
- `ChainWriter` Protocol → **Story 3.4**.
- `BEGIN IMMEDIATE` / WAL mode → **Story 3.5**.
- `ulog verify` / `ulog repair` / `ulog purge` CLI subcommands → **Stories 3.7 / 3.8 / 3.9**.

This story is **trigger-only**. Rows can still be inserted with `immutable=1` only via raw SQL (the production application code path is `SQLHandler.emit()` which always sets `immutable=0` until Story 3.5 wires the ChainWriter). Tests prove the trigger fires correctly by inserting `immutable=1` directly via SQLAlchemy text DML.

### Files being modified — current state and required changes

#### `ulog/handlers/sql.py` (UPDATE)

Current `_verify_or_create_schema` at lines 193-227 has two terminal paths:
- **Fresh DB** (table absent) — `metadata.create_all()` then `return` (line 210).
- **Existing v0.5 DB** (table + all columns present) — fall through to end of method silently (after the `if missing:` raise at line 222 is skipped).
- **v0.4 DB** (missing columns) — raises `SchemaError`, never reaches trigger install.

The new `_install_immutable_triggers()` call must be inserted on BOTH success paths (fresh + existing-v0.5). Cleanest refactor:

```python
def _verify_or_create_schema(self) -> None:
    from sqlalchemy import inspect
    from sqlalchemy.exc import OperationalError

    inspector = inspect(self._engine)
    if self._table_name not in inspector.get_table_names():
        try:
            self._metadata.create_all(self._engine)
        except OperationalError as exc:
            if "already exists" not in str(exc).lower():
                raise
            inspector = inspect(self._engine)
            if self._table_name not in inspector.get_table_names():
                raise
        else:
            self._install_immutable_triggers()  # <-- new (fresh path)
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
    self._install_immutable_triggers()  # <-- new (existing-v0.5 path)
```

**Important** — the trigger install on the existing-DB branch is what makes v0.5-shaped DBs created by Story 3.1 alone (no triggers) self-heal at next bootstrap. This matters because Story 3.1 shipped without triggers; a user upgrading code in-place finds their DB silently gain triggers on next process start.

**Race-window precedent** — Story 1.13 already covered the `OperationalError("table already exists")` race on `create_all`. The trigger install is also under multi-process bootstrap pressure, but `CREATE TRIGGER IF NOT EXISTS` is the SQLite-supported idempotent form (since SQLite 3.3.8 — 2007 — well below any supported runtime). No try/except needed for AC8; the `IF NOT EXISTS` clause is sufficient.

Existing test `test_sql_handler_no_race_under_concurrent_bootstrap` at line 205 — this test will now also bootstrap triggers. Verify it still passes; the test asserts the table exists and a record can be inserted, neither affected by trigger DDL.

#### `tests/test_handlers.py` (UPDATE)

Append the 6 new tests after the existing `test_sql_v04_upgrade_path_raises_schema_error` at line 371-418. Test file already imports `pytest`, `ulog`, `logging`, `text`. Add `IntegrityError, OperationalError` from `sqlalchemy.exc` (local in test or near top — check current import grouping).

The existing `_isolate` fixture (autouse — verify by looking at lines 1-40) already clears handlers between tests. No new cleanup logic needed.

### Architecture compliance — must follow

- **Decision A1 (Storage shape):** Single `logs` table with `immutable` column flag + SQL trigger blocking UPDATE/DELETE `WHERE immutable = 1`. [Source: architecture.md, lines 328-334]
- **Decision B3 (`ChainWriter` abstraction):** v0.5 ships SQLite-only; Postgres v0.7. The trigger must be dialect-gated to allow the v0.7 Postgres backend to install its own equivalent (likely a `RULE` or function-based `BEFORE` trigger). [Source: architecture.md, lines 372-386]
- **Invariant I4 (immutable hard):** "immutable records uncuttable through any path (API, CLI, admin)". SQL trigger is the *storage-layer* enforcement of I4 — the bottom of the defense-in-depth stack. [Source: architecture.md, line 133, line 1240]
- **Enforcement rule #2 (Lazy SQLAlchemy imports):** `text` import lives inside the existing lazy block at lines 98-110, never at module top-level. [Source: architecture.md, lines 779, 793]
- **Enforcement rule "INTEGER not BOOLEAN":** Trigger condition uses `OLD.immutable = 1` (not `= TRUE`). This mirrors the column type (`INTEGER NOT NULL DEFAULT 0`) and the Story 3.3 upgrade-hint SQL. [Source: architecture.md, lines 636-639]

### Library / framework requirements

- **SQLAlchemy ≥ 2.0** — already pinned via `[storage]` extra. `sqlalchemy.text` and `engine.dialect.name` are stable API. `IntegrityError` / `OperationalError` re-exports from `sqlalchemy.exc` unchanged since 1.x.
- **SQLite ≥ 3.3.8** — `CREATE TRIGGER IF NOT EXISTS` requires this. Every Python 3.10+ binary ships a far newer sqlite3 (3.31+ on Debian 11, 3.40+ on Debian 12, 3.45+ on Python 3.13). No version surprise.
- **No new dependency** — story adds zero PyPI packages. CI gate `dependencies = []` unaffected.

### Testing standards

- **Framework:** pytest (already on `[testing]` + `[dev]` extras).
- **Location:** Append to `tests/test_handlers.py` after the existing 3 v0.5 tests (line 419+). Keep file organization: csv → jsonline → sql v0.2 → race → multi → setup-rejections → sql v0.5 (3.1) → **sql v0.5 (3.2 — new tests here)**.
- **Fixtures:** `tmp_path` for per-test DB (same as Story 3.1 tests).
- **DB URL:** `f"sqlite:///{tmp_path / 'logs.sqlite'}"`.
- **Bypass the handler for trigger-presence tests** — Tests that assert trigger DDL exists use raw SQLAlchemy `create_engine(url)` + `text("SELECT … FROM sqlite_master")`. Tests that assert the trigger BLOCKS write use raw `text("INSERT INTO logs … VALUES (…, immutable=1, …)")` because `SQLHandler.emit()` always sets `immutable=0` (Story 3.5 will change that).
- **Error tolerance** — Use `pytest.raises((IntegrityError, OperationalError))` not just `IntegrityError` — SQLAlchemy 2.0+ tends to wrap `sqlite3.IntegrityError` as `IntegrityError`, but some older driver paths surface `OperationalError`. Both indicate trigger fired.

### Previous-work intelligence — patterns established in Stories 3.1 and 1.13

- **Pattern: lazy SQLAlchemy imports** — every new SQLA type goes in the same `from sqlalchemy import (...)` block at lines 98-110. `text` is **already imported there** as of Story 1.13's race-test fixture work — verify before editing; if absent add it alphabetically.
- **Pattern: schema verification idempotency** — Story 1.13 added the `OperationalError("table already exists")` catch on `create_all`. The trigger install uses a different idempotency mechanism (`IF NOT EXISTS` in DDL) because SQLite supports it natively for triggers but `metadata.create_all` does not for tables (it tries fresh).
- **Pattern: dialect-gated SQL DDL** — first instance in this codebase. Mirror in Story 3.5 which will use `engine.dialect.name == "sqlite"` to set WAL mode. The conditional should be one-line (`if self._engine.dialect.name != "sqlite": return`) at the top of the new method.
- **Pattern: raw SQL via `text()` for `_install_*` private methods** — preferred over Core-level `CreateTrigger` constructors (which don't exist for triggers in SQLAlchemy 2.0; you'd be reaching for `DDL()` objects which add nothing here). Plain `conn.execute(text(...))` is the idiomatic path.

### Recent commits — context for upcoming work

```
1b7d645 feat(qa): item-1.1-3-full uses 8000px viewport so sidebar reaches the last test group
5834b60 chore(deps,linters): pyproject extras + pre-commit + bash _lib.sh helpers
a25443f feat(qa): Playwright + sidebar-only shots + pngquant pipeline
ac04a31 feat(qa): tall screenshots use 1920×12000 to capture truly full page
927b89d feat(qa): bypass tutorial overlay for screenshots + tall viewport for full-sidebar shots
```

Latest commits are QA tooling (Playwright screenshots). No SQL handler changes since Story 3.1. Story 3.2 lands on a clean tree.

### Project context reference

- Repo-wide guardrails: `_bmad-output/project-context.md` — Technology Stack & Versions (Python 3.10+, `mypy --strict`, zero runtime deps, SQLAlchemy under `[storage]` extra only).
- Architecture: `_bmad-output/planning-artifacts/architecture.md` §Storage Architecture (A1), §Concurrency, Integrity & Input Validation (B1, B3), §Invariants (I4), §Enforcement (lazy imports, INTEGER not BOOLEAN).
- Epics: `_bmad-output/planning-artifacts/epics.md` Epic 3 intro at line 1025, Story 3.2 at lines 1051-1071.
- Previous story: `_bmad-output/implementation-artifacts/3-1-schema-extension-immutable-chain-pos-record-hash-prev-hash-columns.md` — schema landed, no triggers yet.

### References

- [Source: _bmad-output/planning-artifacts/epics.md, lines 1051-1071] — Story 3.2 acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 328-334] — Decision A1 (column-flag single table + trigger)
- [Source: _bmad-output/planning-artifacts/architecture.md, line 133] — Invariant I4 (immutable hard)
- [Source: _bmad-output/planning-artifacts/architecture.md, line 1240] — I4 enforcement mechanism (SQL trigger)
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 779, 793] — Enforcement rules (lazy imports)
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 636-639] — Format pattern (INTEGER not BOOLEAN)
- [Source: ulog/handlers/sql.py, lines 193-227] — `_verify_or_create_schema` — extension point for trigger install
- [Source: ulog/handlers/sql.py, lines 98-110] — lazy SQLAlchemy import block — add `text` here if absent
- [Source: tests/test_handlers.py, lines 315-418] — v0.5 test patterns (Story 3.1) — mirror these for Story 3.2 tests
- [Source: tests/test_handlers.py, line 205] — `test_sql_handler_no_race_under_concurrent_bootstrap` — existing race test, must stay green after trigger install lands
- [SQLite docs] https://www.sqlite.org/lang_createtrigger.html — `CREATE TRIGGER IF NOT EXISTS`, `RAISE(ABORT, ...)`, `OLD.column` semantics

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m]

### Debug Log References

n/a — pure additive DDL + tests, no surprises expected.

### Completion Notes List

- Two SQLite triggers installed via `CREATE TRIGGER IF NOT EXISTS`
  after schema bootstrap. Both fresh-create AND existing-v0.5 paths in
  `_verify_or_create_schema` reach the trigger install (refactored
  `try/except/else` so fresh path returns inside `else`, race-lost
  path falls through to existing-table branch which also installs).
- Dialect-gated via `self._engine.dialect.name != "sqlite"` — silent
  return for non-SQLite (Postgres v0.7 will install its own
  equivalent per Decision B3). No warning emitted.
- `text` imported lazily inside `_install_immutable_triggers` (mirrors
  the existing `inspect` lazy import pattern in
  `_verify_or_create_schema`).
- 6 new tests added under a `# ---- SQLHandler — v0.5 immutable
  triggers (Story 3.2) -----` block. Shared `_bootstrap_v05_db` helper
  factors out the setup boilerplate (setup + emit + return engine).
- Tests accept `(IntegrityError, OperationalError)` in `pytest.raises`
  to stay tolerant to SQLAlchemy version drift on trigger-raised
  `RAISE(ABORT, …)` mapping.
- AC9 (dialect-gated) is covered in code but not by an explicit test —
  the only currently-supported dialect is SQLite; a `mock dialect`
  test would be testing a trivial branch. Documented for v0.7 when
  Postgres handler arrives.
- All 23 tests in `tests/test_handlers.py` green (17 pre-existing +
  6 new). `mypy --strict` clean. `ruff check` + `ruff format` clean.
  `deptry` clean.
- Pre-existing unrelated failure in `tests/test_qa_view.py::test_qa_view_renders_all_checkboxes_with_unique_ids`
  (≥50 checkbox count assertion now hits 48 due to earlier QA section
  retirement via e2e automation) is NOT introduced by this story —
  reproduced on a clean stash before changes.

### File List

- `ulog/handlers/sql.py` — `_verify_or_create_schema` refactored to
  `try/except/else` form, new `_install_immutable_triggers` method
  installs both UPDATE-blocking and DELETE-blocking triggers via
  `CREATE TRIGGER IF NOT EXISTS`.
- `tests/test_handlers.py` — 6 new tests for Story 3.2 + shared
  `_bootstrap_v05_db` helper, appended after the Story 3.1 tests.
