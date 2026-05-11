# Story 3.1: Schema extension — `immutable` + `chain_pos` + `record_hash` + `prev_hash` columns

Status: ready-for-dev

## Story

As a developer running the v0.5 SQL handler against a fresh DB,
I want the `logs` table to include `immutable INTEGER`, `chain_pos INTEGER`, `record_hash BLOB`, `prev_hash BLOB` columns with proper indexes,
so that chain integrity and immutability are first-class schema concerns from the moment the schema is materialized.

## Acceptance Criteria

1. **Fresh DB schema creation** — Given a fresh SQLite DB, when `SQLHandler.__init__` runs and `_ensure_schema()` fires on first emit, then `metadata.create_all()` creates the `logs` table with the 4 new columns plus the 2 new indexes `ix_logs_chain_pos` and `ix_logs_immutable` (Decision A1, A4).
2. **Column types and defaults** —
   - `chain_pos INTEGER NOT NULL DEFAULT 0`
   - `record_hash BLOB` nullable
   - `prev_hash BLOB` nullable
   - `immutable INTEGER NOT NULL DEFAULT 0` — explicit `INTEGER` (not `Boolean`), so the SQL DDL string we emit in v0.4→v0.5 upgrade hints (Story 3.3) is unambiguous (Decision A1, Format pattern "Boolean in SQL").
3. **Index creation** — `ix_logs_chain_pos` on `chain_pos`, `ix_logs_immutable` on `immutable`, both following the existing `ix_{table}_{col}` naming pattern at `ulog/handlers/sql.py:126-129`.
4. **Schema verification path unchanged behavior** — Given an existing v0.4 DB (no new columns), when v0.5 `SQLHandler` initializes against it, then `_verify_or_create_schema` raises the v0.2-style `SchemaError` listing the 4 missing columns (the *exact* upgrade message wording lands in Story 3.3 — for this story the existing diff-set error is acceptable as long as it surfaces ALL 4 missing columns).
5. **No behavioral regression** — Records emitted through the v0.5 handler against a fresh DB persist with `chain_pos=0`, `immutable=0`, `record_hash=NULL`, `prev_hash=NULL`. All 287 existing tests stay green. Default emit path (no chain logic yet — that lands in Story 3.5) is unchanged at the row-insert level.
6. **Pattern compliance** — New columns mirrored on the `Adapter.Record` dataclass and SQLite/JSONL/CSV adapters per Enforcement rule #8 ("Mirror new `Record` / `QueryResult` fields across all three adapters — never break adapter uniformity"). JSONL/CSV records read back without `chain_pos`/`immutable`/`record_hash`/`prev_hash` keys default to `chain_pos=0`, `immutable=0`, `record_hash=None`, `prev_hash=None`.
7. **Type checking green** — `mypy --strict` passes for `ulog/handlers/sql.py` and `ulog/web/viewer/adapters.py`.
8. **Tests** — at minimum:
   - `tests/test_handlers.py::test_sql_v05_schema_has_chain_and_immutable_columns` — fresh DB, inspect SQLAlchemy metadata: 4 cols + 2 indexes present.
   - `tests/test_handlers.py::test_sql_v05_default_values` — emit one record without chain logic, read back: `chain_pos=0`, `immutable=0`, `record_hash IS NULL`, `prev_hash IS NULL`.
   - `tests/test_handlers.py::test_sql_v04_upgrade_path_raises_schema_error` — pre-create a v0.4-shaped table (8 cols, no new ones), then SQLHandler emit raises `SchemaError` mentioning all 4 missing column names.

## Tasks / Subtasks

- [ ] **Task 1 — Extend `Table` definition in `ulog/handlers/sql.py`** (AC: 1, 2, 3)
  - [ ] 1.1 — Add 4 `Column(...)` entries inside the `Table(...)` block at `ulog/handlers/sql.py:114-130` (right after `Column("context", JSON, nullable=True)`):
    - `Column("chain_pos", Integer, nullable=False, server_default="0")`
    - `Column("record_hash", LargeBinary, nullable=True)`
    - `Column("prev_hash", LargeBinary, nullable=True)`
    - `Column("immutable", Integer, nullable=False, server_default="0")`
  - [ ] 1.2 — Import `LargeBinary` from sqlalchemy in the existing import block at line 98-109 (keep it lazy — same block).
  - [ ] 1.3 — Add 2 `Index(...)` entries after the existing 4 indexes at line 126-129:
    - `Index(f"ix_{table}_chain_pos", "chain_pos")`
    - `Index(f"ix_{table}_immutable", "immutable")`
- [ ] **Task 2 — Mirror schema on the `Record` dataclass** (AC: 6, 7)
  - [ ] 2.1 — Extend `Record` at `ulog/web/viewer/adapters.py:25-37` with 4 new fields:
    - `chain_pos: int = 0`
    - `record_hash: bytes | None = None`
    - `prev_hash: bytes | None = None`
    - `immutable: bool = False` — store as Python `bool` in the dataclass for ergonomics; the SQL column stays `INTEGER` per AC2.
  - [ ] 2.2 — Update `SQLiteAdapter._row_to_record` at `ulog/web/viewer/adapters.py:449` to populate the new fields from the row (`getattr(row, "chain_pos", 0)`, `bytes(row.record_hash) if row.record_hash else None`, idem `prev_hash`, `bool(row.immutable)`).
  - [ ] 2.3 — Update `JSONLAdapter` (`_payload_to_record` helper) and `CSVAdapter` constructors to read optional keys/columns and default to `0`/`None`/`False`. JSONL/CSV writers never produce these fields in v0.5 (chain is SQL-only per Decision B1) — readers just tolerate them missing.
- [ ] **Task 3 — Tests** (AC: 8)
  - [ ] 3.1 — Add `test_sql_v05_schema_has_chain_and_immutable_columns` to `tests/test_handlers.py` near line 113 (the `# ---- SQLHandler ----` block). Use `sqlalchemy.inspect(engine)` and assert the 4 column names + 2 index names are present after a fresh `setup(handlers=['sql'], sql_url=...)`.
  - [ ] 3.2 — Add `test_sql_v05_default_values` — emit one info record, read it back via `text("SELECT chain_pos, immutable, record_hash, prev_hash FROM logs")`, assert `(0, 0, None, None)`.
  - [ ] 3.3 — Add `test_sql_v04_upgrade_path_raises_schema_error` — pre-create the v0.4 shape via raw SQLAlchemy in `tmp_path`, then call `ulog.setup(handlers=['sql'], sql_url=...)` + emit, assert `SchemaError` is raised on emit and the message contains `"chain_pos"`, `"record_hash"`, `"prev_hash"`, `"immutable"`. **Important** — the handler swallows in `emit()` via `self.handleError(record)`; you must trigger `_ensure_schema()` directly or catch the swallowed error via a `logging` capture / pytest `caplog`. The simplest path: instantiate `SQLHandler(url=..., batch_size=1)` directly and call `handler._ensure_schema()` — this bypasses the `emit()` try/except.
- [ ] **Task 4 — Validation** (AC: 5, 7)
  - [ ] 4.1 — Run `pytest tests/` — all 287+ prior tests still green, 3 new tests pass.
  - [ ] 4.2 — Run `mypy ulog/` — `Success: no issues found`.
  - [ ] 4.3 — Run `ruff check . && ruff format . --check` — both clean.
  - [ ] 4.4 — Run `python -m deptry .` — no new dep issues.

## Dev Notes

### What this story is and is NOT

**IN scope (this story):**
- Extending the SQLAlchemy `Table` definition in `ulog/handlers/sql.py` with the 4 new columns + 2 new indexes.
- Mirroring the fields on the `Record` dataclass and the 3 adapters per Enforcement rule #8 (`ulog/web/viewer/adapters.py`).
- 3 new tests covering: schema creation, default values, upgrade-path `SchemaError`.

**OUT of scope (other Epic 3 stories — do NOT implement here):**
- `CREATE TRIGGER` blocking UPDATE/DELETE on `immutable=1` rows → **Story 3.2**
- Crafting the *exact* upgrade-hint `SchemaError` message with literal `ALTER TABLE … ` SQL → **Story 3.3** (this story only requires the existing v0.2-style "missing columns" error)
- `ChainWriter` Protocol + `SQLiteChainWriter` impl → **Story 3.4**
- WAL mode, `BEGIN IMMEDIATE`, hash computation, `prev_hash` linkage → **Story 3.5**
- `setup(integrity='hash-chain', …)` public param wiring → **Story 3.6**
- `ulog verify` / `ulog repair` CLI → **Story 3.7 / 3.8**

This story is **pure additive schema work**. After landing it, all chain columns exist and persist with defaults; the chain isn't yet *populated* with meaningful hashes — that's Stories 3.4/3.5.

### Files being modified — current state and required changes

#### `ulog/handlers/sql.py` (UPDATE)

Current schema definition at lines 113-130 — 8 columns + 4 indexes. **Read the file fully before editing.** Key existing patterns to preserve:

- Lazy import block at lines 98-109 — add `LargeBinary` to this block, **never** at module top-level (Enforcement rule #2: SQLAlchemy stays lazy so `import ulog` works without the `[storage]` extra installed).
- Index naming `f"ix_{table}_{col}"` — `table` here is `self._table_name` (parameter, defaults to `"logs"`); the new indexes follow the same pattern.
- The `_verify_or_create_schema` method at line 181 already diffs `expected_cols - existing_cols` and raises the v0.2 `SchemaError`. With the new columns added to the `Table` definition, this will automatically surface them in the missing-columns set for v0.4 DBs — no separate code change needed for AC4 in this story. (Story 3.3 will replace this with the literal ALTER TABLE wording.)
- The race-window guard at lines 187-205 (table-exists race under multi-process bootstrap) — leave intact.
- `_record_to_row` at line 217 — **do NOT** populate the new columns from this method in this story. They default via `server_default="0"` (SQL-side) or stay NULL. The chain values land in Story 3.5 via the `ChainWriter`.

Existing test at `tests/test_handlers.py:205-…::test_sql_handler_no_race_under_concurrent_bootstrap` — your `metadata.create_all()` change must not break this multi-process race test. The new indexes go through `create_all` too; they're idempotent on re-create per SQLAlchemy semantics.

#### `ulog/web/viewer/adapters.py` (UPDATE)

Current `Record` dataclass at lines 25-37 has 9 fields. Adding 4 nullable/defaulted fields keeps backward compat for existing call sites that construct `Record(id=..., ts=..., …)` positionally. **Caution:** the existing 4-column inferred type on the SQLAlchemy clauses list (`list[ColumnElement[bool]]`) at line 202 is unrelated — don't touch it.

- `SQLiteAdapter._row_to_record` at line 449 — reads via attribute access on a SQLAlchemy `Row` object. Use `getattr(row, "chain_pos", 0)` defensively so JSON_extract-based reflected schemas without the new columns don't crash (the existing v0.4 demo DBs won't have them).
- `JSONLAdapter` and `CSVAdapter` constructors at lines 533+/594+ — they call `_payload_to_record(payload, i)` (JSONL) and inline-build `Record(...)` (CSV). Update both paths to read optional keys with defaults.

### Architecture compliance — must follow

- **Decision A1 (Storage shape):** Single `logs` table with column flag. **Not** two physical tables. [Source: architecture.md#Storage-Architecture, lines 328-335]
- **Decision A4 (`chain_pos` strategy):** Dedicated `INTEGER NOT NULL` column with `ix_logs_chain_pos` index. **Not** reusing `id`. [Source: architecture.md, lines 751-758]
- **Format pattern (Boolean in SQL):** `INTEGER DEFAULT 0`, **never** `Boolean`. SQLAlchemy maps `Boolean → INTEGER` anyway; explicit `INTEGER` keeps the upgrade-path SQL string we emit (Story 3.3) unambiguous. [Source: architecture.md, lines 636-639]
- **Enforcement rule #2 (Lazy imports):** Keep `LargeBinary` import inside the existing lazy block at lines 98-109. [Source: architecture.md#Enforcement, line 779]
- **Enforcement rule #8 (Adapter uniformity):** Mirror new `Record` fields across SQLite + JSONL + CSV adapters. Never break adapter uniformity. [Source: architecture.md#Enforcement, lines 793-794]

### Library / framework requirements

- **SQLAlchemy ≥ 2.0** — already pinned via `[storage]` extra at `pyproject.toml`. `LargeBinary` is exported from the top-level `sqlalchemy` package since 1.x; no version surprise.
- **No new dependency** — this story adds zero PyPI packages. The CI gate `dependencies = []` (Decision E2) is unaffected because the new columns use stdlib types and existing SQLAlchemy primitives.

### Testing standards

- **Framework:** pytest (already on `[testing]` + `[dev]` extras).
- **Location:** Append new tests to `tests/test_handlers.py` after the `# ---- SQLHandler ----` block at line 113 — keep the file organization intact (qlnes formatter tests first, then SQLHandler block).
- **Fixtures:** `tmp_path` (pytest built-in) for the SQLite DB — same pattern as `test_sql_records_persist_to_sqlite` at line 116.
- **DB URL:** `f"sqlite:///{tmp_path / 'logs.sqlite'}"` — never an in-memory `:memory:` URL (each engine connect would see a fresh DB; we need cross-connection persistence for the schema verification).
- **Setup helpers:** Reuse the existing `ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)` idiom — `batch_size=1` forces immediate flush.
- **Cleanup:** The `_isolate` autouse fixture in this file (if present — verify lines 1-40) already clears handlers between tests. Don't add new cleanup logic.
- **Assertion style:** raw SQL via `engine.execute(text("SELECT … FROM logs"))` for round-trip verification — matches `test_sql_records_persist_to_sqlite` at line 130. For schema inspection use `sqlalchemy.inspect(engine).get_columns("logs")` / `get_indexes("logs")`.

### Previous-work intelligence — patterns established in Epics 1-2 that apply here

- **Pattern: lazy SQLAlchemy imports** — established in `ulog/handlers/sql.py` at lines 98-109. Every new SQLA type goes in the same `from sqlalchemy import (…)` block. Don't add a second import block.
- **Pattern: column verification on existing tables** — `_verify_or_create_schema` already handles the v0.4→v0.5 missing-column case via set-diff (line 207). Don't reinvent.
- **Pattern: race-window-tolerant `create_all`** — lines 187-205 catch the `OperationalError("table already exists")` race. The new indexes go through the same `create_all` call and inherit this protection.
- **Pattern: adapter-uniformity Record fields** — Epic 2 (Stories 2.6-2.8) added author-related fields to all 3 adapters in lockstep. Same drill here.
- **Pattern: `[ColumnElement[bool]]` typed clauses** — adapters.py:202 was just typed in the recent lint pass. **Don't touch.**

### Recent commits — context for upcoming work

- `1b7d645 feat(qa): item-1.1-3-full uses 8000px viewport so sidebar reaches the last test group` — Playwright screenshot pipeline, unrelated.
- `5834b60 chore(deps,linters): pyproject extras + pre-commit + bash _lib.sh helpers` — established `[dev]` extras (ruff, mypy, deptry, pip-audit, pre-commit) and `tool.ruff.lint.isort` + mypy overrides for Django/ucolor. Your new code will be linted by the same gate.
- Pre-`a25443f` — Epic 2 (author attribution) work; gives the adapter-uniformity precedent.

The most recent uncommitted change set is a sweeping lint cleanup (139 ruff + 57 mypy + 7 CVE fixes — all green). Your story lands on top of that clean tree. **Stay green** with all linters per Task 4.

### Project context reference

- Repo-wide guardrails: `_bmad-output/project-context.md` — focus on the "Technology Stack & Versions" section (Python 3.10+, `mypy --strict`, zero runtime deps, SQLAlchemy under `[storage]` extra only).
- Architecture: `_bmad-output/planning-artifacts/architecture.md` §Storage Architecture (lines 326-358), §Format patterns (lines 600-645), §`chain_pos` column strategy (lines 751-758), §Enforcement (lines 773-803).
- Epics: `_bmad-output/planning-artifacts/epics.md` Epic 3 intro at line 1025 — stories 3.1 through 3.12 collectively deliver v0.5 chain integrity.

### References

- [Source: _bmad-output/planning-artifacts/epics.md, lines 1029-1049] — Story 3.1 acceptance criteria
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 326-358] — Decisions A1, A2, A3, A4 (Storage Architecture)
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 360-391] — Decisions B1, B3 (Chain integrity placement + `ChainWriter` Protocol)
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 600-645] — Format patterns (canonical JSON, Boolean→INTEGER)
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 751-758] — `chain_pos` column strategy (dedicated INTEGER, not reused `id`)
- [Source: _bmad-output/planning-artifacts/architecture.md, lines 773-803] — Enforcement rules (lazy imports, adapter uniformity)
- [Source: ulog/handlers/sql.py, lines 98-130] — current `Table` definition + imports
- [Source: ulog/handlers/sql.py, lines 181-215] — `_verify_or_create_schema` (will auto-surface 4 new missing columns for v0.4 DBs)
- [Source: ulog/web/viewer/adapters.py, lines 25-37] — `Record` dataclass
- [Source: ulog/web/viewer/adapters.py, lines 449-475] — `SQLiteAdapter._row_to_record`
- [Source: tests/test_handlers.py, lines 113-215] — existing SQLHandler test patterns to mirror

## Dev Agent Record

### Agent Model Used

_To be populated by dev agent._

### Debug Log References

### Completion Notes List

### File List
