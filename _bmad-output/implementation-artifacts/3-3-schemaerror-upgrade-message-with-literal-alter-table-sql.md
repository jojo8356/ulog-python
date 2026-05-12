# Story 3.3: `SchemaError` upgrade message with literal ALTER TABLE SQL

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-3-schemaerror-upgrade-message-with-literal-alter-table-sql`
**Implements:** Decision A2 (`SchemaError` with explicit ALTER TABLE in message), Gap G1 (pre-chain upgrade discontinuity documented at the upgrade point)
**Source:** PRD-v0.5 §3.1 (no auto-migrations), architecture.md §A2, §G1
**Built on:** Story 3.1 (the 4 chain columns + 2 indexes are part of the `Table` definition; `_verify_or_create_schema` already raises a generic missing-columns `SchemaError` for v0.4 DBs).
**Foundation for:** Story 3.5 (`SQLHandler` chain integration — assumes the user has already run the suggested ALTER TABLE before chain writes start), Story 3.7 (`ulog verify` — must skip NULL-hash backfilled rows per Gap G1).

## Story

As a **v0.4 user upgrading to v0.5**,
I want **`SchemaError` to fire with the exact ALTER TABLE statements I need to run** (deterministic, copy-paste, including the index creation),
so that **I can apply the upgrade without consulting external docs and without an auto-migration that could fail mid-way** (the v0.2 "no auto-migrations" contract).

## Acceptance Criteria

1. **Literal ALTER TABLE statements in error message** — Given a v0.4 SQLite DB (no `chain_pos`/`record_hash`/`prev_hash`/`immutable` columns), when v0.5 `SQLHandler._ensure_schema()` fires, then `SchemaError` is raised with a message containing **all four** literal statements (sorted deterministically — order locked below):
   ```
   ALTER TABLE logs ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0;
   ALTER TABLE logs ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0;
   ALTER TABLE logs ADD COLUMN prev_hash BLOB;
   ALTER TABLE logs ADD COLUMN record_hash BLOB;
   ```
   Order: alphabetical by column name (`chain_pos`, `immutable`, `prev_hash`, `record_hash`) — matches `sorted(missing)` for determinism.
2. **Literal CREATE INDEX statements** — The same error message also contains the 2 `CREATE INDEX` statements (only for the indexes that need creation — when the column is being added by the ALTER):
   ```
   CREATE INDEX ix_logs_chain_pos ON logs(chain_pos);
   CREATE INDEX ix_logs_immutable ON logs(immutable);
   ```
3. **Gap G1 discontinuity note** — The message includes a short paragraph stating that **existing rows will have `record_hash`/`prev_hash` NULL** (pre-chain backfilled), and **the first NEW chain record starts a fresh chain** with `prev_hash = b"\x00" * 32`. The exact wording must mention "pre-chain" and "fresh chain" so a user grepping log noise lands on the correct section of the v0.5 release notes.
4. **Resolved-after-manual-ALTER** — Given the user runs the suggested SQL against the v0.4 DB, when v0.5 `SQLHandler` re-initializes against it, then no `SchemaError` is raised, schema verification succeeds, and an emit persists the new record with `chain_pos=0`, `immutable=0`, `record_hash=NULL`, `prev_hash=NULL` (defaults — Story 3.5 will start populating chain values).
5. **Partial-upgrade tolerance** — Given a v0.4 DB where the user manually added ONLY `chain_pos` (other 3 still missing), when `SQLHandler._ensure_schema()` runs, then the `SchemaError` message lists **only the 3 still-missing columns** with their ALTER statements (not all 4) and **only the indexes that still need creating** (`ix_logs_chain_pos` is also missing — both indexes appear when both columns are missing; if `chain_pos` is present but `ix_logs_chain_pos` is missing, the CREATE INDEX for it still appears). This matters because real upgrades may happen in pieces under stress.
6. **Non-chain missing columns fall back to legacy message** — Given a DB missing a non-chain column (e.g., a v0.1 DB without the `context` column), when `_verify_or_create_schema` runs, then the legacy v0.2-style message is raised — the literal ALTER TABLE format is ONLY shown when the missing set intersects the chain columns. This protects backward compatibility for users upgrading older-than-v0.4 DBs (rare but valid).
7. **Error class unchanged** — `SchemaError` (defined at `ulog/handlers/sql.py:51`) is still the raised exception class. No new subclass.
8. **Type checking green** — `mypy --strict` passes for `ulog/handlers/sql.py`.
9. **Tests** — at minimum (updates `tests/test_handlers.py`):
   - **UPDATE existing** `test_sql_v04_upgrade_path_raises_schema_error` (line 371-418) — assert the new literal SQL format is present, not just the column names. The 4 ALTER TABLE strings + 2 CREATE INDEX strings + the Gap G1 phrasing must all appear in `str(excinfo.value)`.
   - **NEW** `test_sql_v05_upgrade_message_resolved_after_manual_alter` — pre-create v0.4 DB, parse the SQL out of the SchemaError message, execute it via raw SQLAlchemy, re-bootstrap handler, assert it proceeds and a subsequent emit lands with chain defaults.
   - **NEW** `test_sql_v05_upgrade_partial_chain_columns` — pre-create v0.4 + 1 chain column (`chain_pos` only), assert error message lists only the 3 remaining columns, not all 4.
   - **NEW** `test_sql_v05_upgrade_message_lists_indexes_when_columns_missing` — assert both `CREATE INDEX ix_logs_chain_pos` and `CREATE INDEX ix_logs_immutable` appear in the message when both columns are missing.
   - **NEW** `test_sql_v05_non_chain_missing_column_uses_legacy_message` — pre-create a DB missing a non-chain column (e.g. `exc`), assert the legacy message format (not the literal-SQL one) fires.
10. **No behavioral regression** — All test_handlers.py + the rest of the suite stay green. The trigger install from Story 3.2 is unaffected (it only runs when schema verification passes — i.e., when the user has applied the suggested ALTER, post-upgrade).

## Tasks / Subtasks

- [ ] **Task 1 — Module-level chain-DDL constants** (AC: 1, 2, 5)
  - [ ] 1.1 — At the top of `ulog/handlers/sql.py` (after the `_RESERVED` frozenset and before `class SchemaError`), define:
    ```python
    # Story 3.3 / Decision A2 — literal upgrade DDL.
    # Map each v0.5 chain column to its ALTER TABLE statement and
    # optional CREATE INDEX statement. Keyed by column name so the
    # error message can list only the columns actually missing.
    _CHAIN_COLUMN_ALTER_DDL: dict[str, str] = {
        "chain_pos": "ALTER TABLE {t} ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0;",
        "immutable": "ALTER TABLE {t} ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0;",
        "prev_hash": "ALTER TABLE {t} ADD COLUMN prev_hash BLOB;",
        "record_hash": "ALTER TABLE {t} ADD COLUMN record_hash BLOB;",
    }
    _CHAIN_COLUMN_INDEX_DDL: dict[str, str] = {
        "chain_pos": "CREATE INDEX ix_{t}_chain_pos ON {t}(chain_pos);",
        "immutable": "CREATE INDEX ix_{t}_immutable ON {t}(immutable);",
    }
    ```
    These are module-level so they can be referenced from both the error path and (future) docs / `ulog verify --suggest-upgrade` tooling.
- [ ] **Task 2 — Rewrite `_verify_or_create_schema` error message path** (AC: 1, 2, 3, 5, 6, 7)
  - [ ] 2.1 — Compute `chain_missing = sorted(missing & _CHAIN_COLUMN_ALTER_DDL.keys())`.
  - [ ] 2.2 — If `chain_missing` is non-empty, build the v0.5 upgrade message:
    - One ALTER TABLE per column (in sorted order).
    - For each missing column with an entry in `_CHAIN_COLUMN_INDEX_DDL`, append its CREATE INDEX (also sorted by column name to keep determinism).
    - Append the Gap G1 discontinuity paragraph (see exact wording below).
  - [ ] 2.3 — If `missing` contains ANY non-chain column (i.e., `non_chain_missing = sorted(missing - _CHAIN_COLUMN_ALTER_DDL.keys())` is non-empty), prefer the v0.5 upgrade message **only if** `chain_missing` is non-empty. If only non-chain columns are missing, fall through to the legacy generic message (AC6).
  - [ ] 2.4 — Index-only missing case — if a chain column is present but its index isn't, `missing` won't contain the column (only column-level diff is computed). To also surface missing-index DDL: check `existing_indexes = {i["name"] for i in inspector.get_indexes(self._table_name)}` and union into the message any index from `_CHAIN_COLUMN_INDEX_DDL` whose name isn't in `existing_indexes` AND whose column IS in `existing_cols`. Keep this branch quiet when the schema is otherwise complete (no SchemaError raised if everything else passes — the trigger-install / Story 3.2 path covers idempotent re-bootstrap).
    - **Pragmatic simplification (preferred):** only emit CREATE INDEX statements for indexes whose column is in `chain_missing`. Skipping the standalone "column present, index absent" case keeps the implementation tight; that case is extremely rare in practice (it means someone hand-ran an ALTER but forgot the CREATE INDEX, which is its own user error). If we keep the impl tight, AC2 still holds because the test pre-creates a v0.4 DB (no chain columns AT ALL) → both columns are in `chain_missing` → both indexes appear.
    - **Decision: go with the simplification.** Document the trade-off in dev notes. AC5 covers the "partial chain columns" case to make sure the message stays correct when some columns are already added.
  - [ ] 2.5 — Gap G1 wording — exact paragraph to append (one blank line before it):
    ```
    Note (Gap G1 — pre-chain upgrade discontinuity):
    Existing rows will have NULL record_hash/prev_hash after the
    ALTER (pre-chain backfilled). The first NEW chain record starts
    a fresh chain with prev_hash = b"\\x00" * 32. `ulog verify`
    only walks records with non-NULL hash.
    ```
  - [ ] 2.6 — Final error message structure:
    ```
    table 'logs' in <url> is a v0.4 schema; v0.5 requires the
    following ALTER TABLE / CREATE INDEX statements. v0.2's
    no-migrations contract is preserved — apply manually:

    ALTER TABLE logs ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE logs ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE logs ADD COLUMN prev_hash BLOB;
    ALTER TABLE logs ADD COLUMN record_hash BLOB;
    CREATE INDEX ix_logs_chain_pos ON logs(chain_pos);
    CREATE INDEX ix_logs_immutable ON logs(immutable);

    Note (Gap G1 — pre-chain upgrade discontinuity):
    Existing rows will have NULL record_hash/prev_hash after the
    ALTER (pre-chain backfilled). The first NEW chain record starts
    a fresh chain with prev_hash = b"\x00" * 32. `ulog verify`
    only walks records with non-NULL hash.
    ```
- [ ] **Task 3 — Update existing test + add 4 new tests** (AC: 9)
  - [ ] 3.1 — Update `test_sql_v04_upgrade_path_raises_schema_error` at lines 371-418:
    - Keep the v0.4 table pre-create.
    - Replace the "column names present in msg" loop with assertions on the literal SQL strings:
      ```python
      for stmt in (
          "ALTER TABLE logs ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0;",
          "ALTER TABLE logs ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0;",
          "ALTER TABLE logs ADD COLUMN prev_hash BLOB;",
          "ALTER TABLE logs ADD COLUMN record_hash BLOB;",
          "CREATE INDEX ix_logs_chain_pos ON logs(chain_pos);",
          "CREATE INDEX ix_logs_immutable ON logs(immutable);",
      ):
          assert stmt in msg, f"missing statement {stmt!r} in SchemaError: {msg!r}"
      assert "pre-chain" in msg.lower()
      assert "fresh chain" in msg.lower()
      ```
  - [ ] 3.2 — Add `test_sql_v05_upgrade_message_resolved_after_manual_alter`:
    - Pre-create v0.4 table.
    - Instantiate SQLHandler, capture SchemaError, extract `msg`.
    - Parse statements via `for stmt in msg.split("\n") if stmt.strip().startswith(("ALTER", "CREATE"))`.
    - Execute each on a fresh engine connection.
    - Re-bootstrap a new SQLHandler against the same URL; call `_ensure_schema()` — must not raise.
    - Emit one record via `ulog.setup` + log call; flush; assert `chain_pos=0`, `immutable=0`, hashes NULL.
  - [ ] 3.3 — Add `test_sql_v05_upgrade_partial_chain_columns`:
    - Pre-create v0.4 + chain_pos added manually (ALTER), no other chain columns.
    - Trigger SchemaError; assert message contains the 3 remaining ALTERs (`immutable`, `prev_hash`, `record_hash`) but NOT `chain_pos`.
    - With the pragmatic simplification (Task 2.4), CREATE INDEX for `ix_logs_chain_pos` will NOT appear in this case (column already present → omitted). Assert that.
    - CREATE INDEX `ix_logs_immutable` DOES appear (its column is in `chain_missing`).
  - [ ] 3.4 — Add `test_sql_v05_upgrade_message_lists_indexes_when_columns_missing` — actually subsumed by 3.1's assertion list. Confirm via the same test; no separate test file needed. **Drop this subtask** — folded into 3.1.
  - [ ] 3.5 — Add `test_sql_v05_non_chain_missing_column_uses_legacy_message`:
    - Pre-create a table with all v0.5 columns EXCEPT `exc` (a non-chain column from v0.2). Easiest: build a Table missing `exc`.
    - Trigger SchemaError.
    - Assert the legacy phrasing (`"v0.2 doesn't ship migrations"`) is present and the literal-SQL phrasing (`"ALTER TABLE"`) is NOT.
- [ ] **Task 4 — Validation** (AC: 8, 10)
  - [ ] 4.1 — Run `pytest tests/test_handlers.py` — all tests pass (1 updated + 3 new + 23 existing).
  - [ ] 4.2 — Run `pytest tests/` — full suite green minus the pre-existing `test_qa_view_renders_all_checkboxes_with_unique_ids` (already addressed in the previous turn → now also passes).
  - [ ] 4.3 — Run `mypy ulog/` → no issues.
  - [ ] 4.4 — Run `ruff check . && ruff format . --check` → clean.
  - [ ] 4.5 — Run `python -m deptry .` → no new dep issues.

## Dev Notes

### What this story is and is NOT

**IN scope:**
- Replace the generic `"is missing columns [...]"` message with a v0.5-specific message containing literal ALTER TABLE + CREATE INDEX statements + Gap G1 note, **when** chain columns are missing.
- Backward-compatibility branch: non-chain missing columns still get the legacy v0.2 message.
- Tests updated/added accordingly.

**OUT of scope:**
- `ulog verify --suggest-upgrade` CLI tooling that would render this message externally → **deferred to v0.5/v0.6 tooling sprint, not a story yet**.
- Auto-running the ALTER TABLE → **forbidden by Decision A2** (no migrations).
- Backfilling `record_hash` for pre-chain rows → **G1 + Gap G8 note; deferred to v0.6 `ulog repair --backfill-chain`**.
- Touching the trigger install (Story 3.2) — already correct: it runs only after schema verification passes, so on a v0.4 DB it never fires until the user runs the upgrade SQL.

### Files being modified — current state and required changes

#### `ulog/handlers/sql.py` (UPDATE)

Current `_verify_or_create_schema` body (lines 193-228) — modify only the `if missing:` branch at lines 221-227. The new logic:

```python
existing_cols = {col["name"] for col in inspector.get_columns(self._table_name)}
expected_cols = {c.name for c in self._table.columns}
missing = expected_cols - existing_cols
if missing:
    chain_missing = sorted(missing & _CHAIN_COLUMN_ALTER_DDL.keys())
    if chain_missing:
        t = self._table_name
        alters = "\n".join(
            _CHAIN_COLUMN_ALTER_DDL[c].format(t=t) for c in chain_missing
        )
        index_cols = [c for c in chain_missing if c in _CHAIN_COLUMN_INDEX_DDL]
        indexes = "\n".join(
            _CHAIN_COLUMN_INDEX_DDL[c].format(t=t) for c in index_cols
        )
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
            "= b\"\\x00\" * 32. `ulog verify` only walks records "
            "with non-NULL hash."
        )
    raise SchemaError(
        f"table {self._table_name!r} in {self._url} is missing columns "
        f"{sorted(missing)}. v0.2 doesn't ship migrations — delete "
        "the DB / use a fresh URL, or add the columns manually."
    )
```

Add the two module-level constants (`_CHAIN_COLUMN_ALTER_DDL`, `_CHAIN_COLUMN_INDEX_DDL`) above `class SchemaError` — top of the file, near other module-scope definitions, after `_RESERVED`.

#### `tests/test_handlers.py` (UPDATE)

- **Replace** the body of `test_sql_v04_upgrade_path_raises_schema_error` (lines 371-418) with the new assertions per Task 3.1.
- **Append** the 3 new tests after the trigger-test block (Story 3.2 tests). They live under a new comment block:
  ```python
  # ---- SQLHandler — v0.5 upgrade message (Story 3.3) -----------------------
  ```

### Architecture compliance — must follow

- **Decision A2 (SchemaError with explicit ALTER TABLE):** [Source: architecture.md, lines 336-345]
- **Gap G1 (pre-chain discontinuity documented at the upgrade point):** [Source: architecture.md, line 1257]
- **v0.2 "no migrations" contract:** preserved — error fires, user applies SQL manually. No `alembic`, no auto-DDL, no `_migrations` table. [Source: project-context.md (Technology Stack), architecture.md "Locked-out libraries"]
- **INTEGER not BOOLEAN:** the literal ALTER DDL uses `INTEGER NOT NULL DEFAULT 0` for both `chain_pos` and `immutable` — matches Story 3.1's schema. [Source: architecture.md, lines 636-639]

### Library / framework requirements

- **Zero new deps** — story is pure Python string-building + SQLAlchemy inspector (already imported).
- **No SQLAlchemy DDL constructs** — we emit raw SQL strings deliberately (the user copy-pastes them into the sqlite3 CLI; `ALTER TABLE` constructs in SA Core would not be copy-paste-friendly).

### Testing standards

- Same as Stories 3.1/3.2: `tmp_path`, `sqlite:///{tmp_path/...}`, `_isolate` autouse fixture handles cleanup.
- Parse-SQL-from-error pattern in test 3.2 — straightforward `line.strip().startswith(("ALTER", "CREATE"))` filter on `msg.split("\n")`. Execute each via `engine.begin() as conn: conn.execute(text(stmt.rstrip(";")))` — SQLAlchemy's `text()` accepts SQL with or without trailing semicolon; rstrip for safety. **Note** — `engine.execute()` is removed in SA 2.0; use `with engine.begin() as conn: conn.execute(text(...))`.
- All assertions use substring match (`in`) — tolerant to whitespace drift in the error message.

### Previous-work intelligence — patterns established in this codebase

- **Pattern: module-level DDL constants** — first instance in this codebase. Mirrors the existing `_RESERVED` frozenset pattern (also module-level, also a closed set of names tied to schema semantics).
- **Pattern: deterministic error messages** — already used in Story 3.1's `sorted(missing)` output. We carry it forward by iterating in alphabetical order of column name.
- **Pattern: branch on "is this a v0.X upgrade vs unknown schema"** — first instance. Future v0.5→v0.6 upgrades would follow the same shape (add another constant + branch).

### Recent commits — context for upcoming work

Story 3.2 just landed on the working tree (trigger DDL + 6 tests). Story 3.3 lands on top — both stories touch `_verify_or_create_schema` but **at non-overlapping branches**:

- Story 3.2 added a `_install_immutable_triggers()` call **after** the column-verify passes (the `if missing:` branch ALWAYS raises — control never reaches the trigger install when columns are missing). So the trigger install code is upstream of (and unaffected by) the error-message refactor here.
- Story 3.3 only touches the `if missing:` body. The control flow before and after is unchanged.

### Project context reference

- Repo-wide guardrails: `_bmad-output/project-context.md` (Python 3.10+, zero runtime deps, mypy --strict).
- Architecture: `architecture.md` §A2 (lines 336-345), §G1 (line 1257).
- Epics: `epics.md` §Epic 3, Story 3.3 (lines 1073-1087).
- Previous stories: `3-1-schema-extension-immutable-chain-pos-record-hash-prev-hash-columns.md`, `3-2-sql-trigger-blocking-update-delete-on-immutable-rows.md`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md, lines 1073-1087] — Story 3.3 acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 336-345] — Decision A2
- [Source: _bmad-output/planning-artifacts/architecture.md, line 1257] — Gap G1
- [Source: ulog/handlers/sql.py, lines 51-56] — `SchemaError` class
- [Source: ulog/handlers/sql.py, lines 193-228] — `_verify_or_create_schema` — extension point
- [Source: ulog/handlers/sql.py, lines 222-227] — current generic message (to be branched)
- [Source: tests/test_handlers.py, lines 371-418] — `test_sql_v04_upgrade_path_raises_schema_error` (UPDATE target)
- [Source: tests/test_handlers.py, lines 419+] — Story 3.2 test block; new Story 3.3 tests append after

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m]

### Debug Log References

n/a — string-building + branch in error path; no surprises.

### Completion Notes List

- Module-level `_CHAIN_COLUMN_ALTER_DDL` + `_CHAIN_COLUMN_INDEX_DDL`
  constants added before `class SchemaError`. Both dicts use `{t}`
  placeholders so the message respects the user's `table=` parameter.
- `_verify_or_create_schema` `if missing:` branch now splits into two
  paths: chain-missing (v0.5 literal-SQL message) and non-chain
  (legacy v0.2 message). Pragmatic simplification confirmed: indexes
  are only listed for columns in `chain_missing` — handled correctly
  by the partial-upgrade test.
- Gap G1 paragraph appended verbatim per spec. Uses double-quote
  Python string for the inner `b"\x00" * 32` literal so the raw
  string lands intact in the error message.
- Test `test_sql_v04_upgrade_path_raises_schema_error` updated:
  loops over 6 literal SQL strings + Gap G1 phrasing assertions.
- 3 new tests added under `# ---- SQLHandler — v0.5 upgrade message
  (Story 3.3) ----` block: resolved-after-manual-ALTER (parses SQL
  out of error, applies it, re-bootstraps clean), partial-chain
  (3 ALTERs only, no ix_logs_chain_pos), non-chain-missing (legacy
  message fires, no ALTER TABLE phrasing).
- Shared `_create_v04_table(url)` helper added to factor out the
  v0.4-shape pre-create across the 3 new tests.
- 26 / 26 `test_handlers.py` tests green (23 prior + 3 new). 7 / 7
  `test_qa_view.py` green (after prior turn's floor adjustment).
  `mypy --strict` clean. `ruff check` + `ruff format` clean after
  auto-fix. `deptry` clean. No SQLAlchemy DDL constructs used — raw
  SQL strings deliberate per dev notes (copy-paste-friendly).

### File List

- `ulog/handlers/sql.py` — `_CHAIN_COLUMN_ALTER_DDL` +
  `_CHAIN_COLUMN_INDEX_DDL` module constants; `_verify_or_create_schema`
  `if missing:` branch split into chain-missing (literal-SQL) +
  legacy paths.
- `tests/test_handlers.py` — `test_sql_v04_upgrade_path_raises_schema_error`
  updated to assert literal SQL + Gap G1 phrasing; new
  `_create_v04_table` helper; 3 new tests under v0.5 upgrade-message
  block.
