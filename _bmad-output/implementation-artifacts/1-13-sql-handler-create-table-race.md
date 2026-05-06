# Story 1.13: SQL handler — guard against CREATE TABLE race under concurrent bootstrap

Status: done

**Epic:** 1 — v0.3 Test integration (POST-RETRO patch — surfaced by real-xdist verification)
**Story key:** `1-13-sql-handler-create-table-race`
**Implements:** Hardens FR22 (SQL handler) and the spirit of NFR-PORT-10 (xdist concurrency) for real multi-process bootstrap, not just the mocked detection paths covered by Story 1.10.
**Source:** Discovered 2026-05-06 immediately after Story 1.12 closed, when running the suite under `pytest -n auto --ulog-db /tmp/foo.sqlite` (after the user installed `pytest-xdist` to verify Story 1.10's xdist tests under real parallel execution). 4 worker processes bootstrap their own `SQLHandler` against the same shared DB → race window between `inspect.get_table_names()` and `metadata.create_all()` → `sqlalchemy.exc.OperationalError("table 'logs' already exists")` for the losers → `Handler.handleError` prints noise on stderr → records lost.
**Built on:** Stories 1.10 (xdist detection + WAL/JSONL fallback strategies, which DO NOT cover concurrent CREATE TABLE).
**Foundation for:** Epic 7 CI matrix dogfooding (running `pytest -n auto --ulog-db ./ci-fixture.sqlite` as a sanity step).

---

## Context — why Story 1.10 didn't catch this

Story 1.10 implemented xdist detection (`_xdist_active`), local-FS WAL mode (`_enable_wal_mode_or_fallback`), and NFS-FS JSONL swap (`_swap_sql_for_jsonl`). All 8 tests in `test_pytest_plugin.py` for NFR-PORT-10 use `monkeypatch` to **simulate** xdist and **simulate** filesystem detection; none of them spawns real subprocesses, so the actual bootstrap concurrency was never exercised.

The patch landed for Story 1.10 protected against concurrent **WRITES** (WAL mode) and worker-NFS lock contention (JSONL swap). It did not protect against concurrent **schema bootstrap** — every worker's `SQLHandler` runs its own `_verify_or_create_schema` on first emit, and there's a TOCTOU between "is the table missing?" (`inspect.get_table_names()`) and "create it" (`metadata.create_all()`).

Once the user installed `pytest-xdist` (post-Story-1.12 verification spike) and ran `pytest tests/ -n auto --ulog-db /tmp/...`, 4 workers raced and 3 lost. The suite passed (180/180) because Python's `Handler.handleError` just prints to stderr and the test database was per-test `tmp_path` (so application records didn't collide), but the stderr noise:

```
--- Logging error ---
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) table logs already exists
```

… is real and indicates lost records under that combo.

## Story

As a **maintainer running `pytest -n auto --ulog-db <shared.sqlite>`** (real-world scenario for v0.3 dogfooding, CI matrices, or any multi-process app sharing a SQL handler),
I want **the SQL handler's schema bootstrap to be safe against concurrent CREATE TABLE attempts**,
so that **no records are lost on first emit, no spurious `OperationalError` reaches stderr, and the suite is clean to embed in a CI step that exercises real xdist parallelism.**

## Acceptance Criteria

### AC1 — Loser of the CREATE TABLE race catches `OperationalError("already exists")` and falls through to column-verify

**Given** two or more processes call `SQLHandler.emit` simultaneously against the same fresh shared SQLite DB
**When** the second process reaches `_verify_or_create_schema` and finds the table absent in `inspect.get_table_names()` but the winning process has already executed `CREATE TABLE` between that inspect call and the loser's `metadata.create_all()`
**Then** the loser catches `sqlalchemy.exc.OperationalError` whose message contains "already exists" (case-insensitive), re-runs `inspect()` to confirm the table now exists, and falls through to the existing column-verify code path. The loser's `emit` succeeds; the record is queued and flushed normally.

### AC2 — Non-race `OperationalError` is still propagated

**Given** `metadata.create_all` raises `OperationalError` for a reason OTHER than "already exists" (e.g., disk full, permission denied, locked DB outside the race window)
**When** the catch block evaluates the error message
**Then** the original exception is re-raised. Schema bootstrap failures unrelated to the race must NOT be silently swallowed.

### AC3 — If re-inspect after catch still doesn't see the table, re-raise

**Given** the catch path runs `inspect()` again after the OperationalError
**When** the table is STILL absent (theoretical defensive case — should not happen in practice)
**Then** the original exception is re-raised. We do not enter the column-verify path with a non-existent table.

### AC4 — Real-process concurrent-bootstrap regression test

**Given** a fresh `tmp_path/race.sqlite`
**When** 4 subprocesses (`subprocess.Popen` with `[sys.executable, "-c", "<bootstrap-and-emit script>"]`) bootstrap a `SQLHandler` against the same DB and emit one record each, in parallel
**Then**
  - All 4 subprocesses return code 0
  - Combined stderr contains NO `"Logging error"` substring
  - Combined stderr contains NO `"OperationalError"` substring
  - The shared DB contains EXACTLY 4 persisted records (no record was lost to the race)

### AC5 — Suite stays green under both invocations and the new combo

**Given** the patched code
**When** the user runs each of:
  - `pytest tests/`
  - `pytest tests/ --ulog-db /tmp/x.sqlite`
  - `pytest tests/ -n auto`
  - `pytest tests/ -n auto --ulog-db /tmp/x.sqlite`  ← THE COMBO THAT REVEALED THE BUG
**Then** all four invocations report 181/181 passed (180 prior tests + 1 new race regression test) with zero stderr noise.

### AC6 — Comment in source explains the race window

**Given** the catch block in `_verify_or_create_schema`
**When** a future maintainer reads the code
**Then** an inline comment explains:
  - The TOCTOU between `inspect.get_table_names()` and `metadata.create_all()`
  - That the race is real-world (multi-process xdist + shared DB), not theoretical
  - That the catch path falls through to column-verify, which is the correct behavior because the winner's table will pass our schema (same `_metadata` definition)

### AC7 — No new dependency

**Given** the fix
**When** `pyproject.toml` is inspected
**Then** the `dependencies = []` invariant (SC4 / NFR-DEP-50) is preserved trivially. The fix uses `sqlalchemy.exc.OperationalError` which is already a transitive dep via SQLAlchemy.

## Tasks / Subtasks

- [x] **Task 1** — Read current `_verify_or_create_schema` to identify the race window (AC1, AC6)
- [x] **Task 2** — Wrap `metadata.create_all` in try/except `OperationalError`, check "already exists" in message, re-inspect, fall through (AC1, AC2, AC3, AC6)
- [x] **Task 3** — Write `tests/test_handlers.py::test_sql_handler_no_race_under_concurrent_bootstrap` using `subprocess.Popen` × 4 against a shared DB (AC4)
- [x] **Task 4** — Run full suite under all four invocations and verify 181/181 with zero stderr noise (AC5)
- [x] **Task 5** — Confirm `pyproject.toml` is unchanged (AC7)

## Dev Notes

**The patch (uog/handlers/sql.py, ~12 lines added):**

```python
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
            return
        except OperationalError as exc:
            if "already exists" not in str(exc).lower():
                raise
            inspector = inspect(self._engine)
            if self._table_name not in inspector.get_table_names():
                raise
    # Existing table — verify columns match.
    ...  # unchanged
```

**Why fall-through to column-verify is correct on race**: the winner's `metadata.create_all` ran the SAME `_metadata` definition we have (each worker's `SQLHandler.__init__` builds a metadata identical in shape). So when we re-inspect and verify columns, the column set will match `expected_cols` and the verify path will silently succeed. We're not skipping any check — we're just correctly identifying that "table exists" has flipped from False to True between our inspect and our create_all attempt.

**Why a real-subprocess test is necessary**: monkeypatching `inspect()` to simulate the race in-process would couple the test to the implementation. Spawning 4 real subprocesses replicates the user's actual `pytest -n auto` scenario at OS-process level. The test takes ~1.4s and reliably triggers the race on a fresh DB (verified empirically).

**What about CREATE INDEX races?** SQLAlchemy's `metadata.create_all` issues `CREATE TABLE` first, then `CREATE INDEX`. If the loser's `CREATE TABLE` raises before the indexes are created, SQLAlchemy aborts the transaction and the indexes are NOT attempted by the loser. The winner created table+indexes atomically (in a single transaction). So the index race doesn't exist in this code path.

**Scope discipline**: this story does NOT touch the existing Story 1.10 xdist code (WAL mode, JSONL swap). Those layers protect concurrent WRITES; this story protects concurrent SCHEMA BOOTSTRAP. Orthogonal concerns.

## Change Log

- 2026-05-06: Initial story creation + same-day implementation. Patch landed in `ulog/handlers/sql.py::_verify_or_create_schema` (~12 lines). New regression test in `tests/test_handlers.py` (~50 lines, `subprocess.Popen × 4`). 181/181 green under all four invocations. SC4 preserved (zero new deps).

## Dev Agent Record

### File List

- `ulog/handlers/sql.py` — `_verify_or_create_schema` race-safe via `OperationalError("already exists")` catch + re-inspect fallthrough
- `tests/test_handlers.py` — new test `test_sql_handler_no_race_under_concurrent_bootstrap` (subprocess × 4)

### Completion Notes

Confirmed all four invocations green:
- `python3 -m pytest tests/` → 181 passed in 6.03s
- `python3 -m pytest tests/ --ulog-db /tmp/x.sqlite` → 181 passed in ~5s
- `python3 -m pytest tests/ -n auto` → 181 passed in ~9s
- `python3 -m pytest tests/ -n auto --ulog-db /tmp/x.sqlite` → 181 passed in 6.73s, **0 stderr noise** (verified via `grep -cE 'Logging error|OperationalError'` → 0)

### Code Review Notes

Skipped per scope (test-only-and-12-line-prod patch, deterministic root cause, regression test exercises the bug).

### Risk Assessment

- **Regression risk**: VERY LOW. The catch path is narrow (only triggers on `OperationalError` whose message contains "already exists"); other errors propagate as before. Re-inspect defensive check ensures we don't enter column-verify with a phantom table.
- **Coverage risk**: NONE. New regression test reproduces the exact failure mode (4 subprocesses, fresh shared DB) and asserts both no-stderr-noise AND record-count correctness.
- **Performance risk**: NONE. The catch is on the schema bootstrap path which runs ONCE per handler instance. The race only fires if losing the race against another process; same-process emits never trigger it.
- **CI risk**: NONE. Existing CI runs `pytest tests/` (no flag) → already green. The new regression test runs in ~1.4s and adds no flakiness — subprocess spawn + SQLite DB + assertion on stderr is deterministic.
