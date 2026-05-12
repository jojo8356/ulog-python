# Story 3.12: PRD-v0.5 §2.3 edge cases for storage/chain (5 of 8)

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-12-prd-v0-5-storage-chain-edge-cases`
**Implements:** PRD-v0.5 §2.3 edge cases (5/8), correction of Story 3.6's `immutable_when` fail-safe direction (architecture says immutable=1, my Story 3.6 impl said =0 — fixed here).
**Built on:** 3.6 (immutable_when wiring), 3.7 (verify + sidecar), 3.8 (repair), 3.9 (purge), 3.10 (sidecar).

## Story

As a **release manager**,
I want **each of 5 PRD-v0.5 §2.3 storage/chain edge cases covered by ≥1 test**,
so that **exotic conditions don't cause silent corruption** before tagging v0.5.0.

## Acceptance Criteria

1. **Broken chain blocks subsequent writes** — Given verify wrote `status: "BROKEN"` to `<db>.verify_state.json`, when `ulog.setup(integrity='hash-chain', sql_url=<db>)` runs next, the SQLHandler raises `SchemaError` with a message pointing the user at `ulog repair --confirm`. Lifted once repair clears the sidecar.
2. **immutable_when raise → treated as immutable** — Given an `immutable_when` callable that raises, when emit runs, the row is persisted with `immutable=1` (fail-safe per Decision B5) AND a one-shot stderr message is printed via `print(..., file=sys.stderr)` (NOT `warnings.warn` — Story 3.6 used the latter, this story corrects).
3. **Hash collision / tampered hash** — Given the DB stores a row whose `record_hash` doesn't match `sha256(canonical_record_json(row) + prev_hash)`, when `ulog verify` walks it, it reports BROKEN at that chain_pos. (Logic check — true hash collision is mathematically infeasible; this AC is satisfied by tampered-hash detection which is the same mechanism.)
4. **min_retention_days violation** — Given `min_retention_days=N` set via `ulog.setup`, when `ulog purge --before <within-N-days>` runs, it exits non-zero with a summary. Regression coverage on top of Story 3.9.
5. **`ulog repair --confirm` clears the verify_state sidecar** — Given a previous BROKEN verify wrote the sidecar, when repair succeeds, the sidecar is removed (so subsequent SQLHandler bootstraps don't see stale BROKEN).
6. **8 concurrent writers** — explicitly out-of-scope here; covered by Story 3.11.

## Tasks / Subtasks

- [ ] **Task 1 — Fix Story 3.6 immutable_when fail-safe**
  - [ ] 1.1 — In `ulog/handlers/sql.py:_record_to_row`, change the `except Exception` branch: set `immutable_flag = 1` (was 0), report via `print(..., file=sys.stderr)` (was `warnings.warn`).
  - [ ] 1.2 — Drop the `import warnings` if no longer used elsewhere.
  - [ ] 1.3 — Add `import sys` to module top.
  - [ ] 1.4 — Update `tests/test_setup_v05_params.py::test_immutable_when_callable_raising_falls_back_safe` to assert `immutable=1` (was 0) and that the stderr message appears via capsys (was via `warnings.catch_warnings`).
- [ ] **Task 2 — Block writes on BROKEN chain (AC1)**
  - [ ] 2.1 — In `ulog/handlers/sql.py:__init__`, when `chain_mode=True` and the URL is SQLite, check `read_verify_state(db_path)`. If status=="BROKEN", raise `SchemaError`.
  - [ ] 2.2 — Extract `db_path` from `sql_url` via stripping the `sqlite:///` prefix.
- [ ] **Task 3 — repair clears the sidecar (AC5)**
  - [ ] 3.1 — In `ulog/_cli/cmd_repair.run`, after successful archive+delete, call `sidecar_path(db).unlink(missing_ok=True)`.
  - [ ] 3.2 — Also clear on the healthy-chain no-op path: if a stale BROKEN sidecar exists for a now-healthy DB, repair should also clean it. Actually NO — verify will rewrite it correctly on next run; leave as is. The unlink only fires after archive+delete.
- [ ] **Task 4 — Tests** — new file `tests/test_chain_edge_cases.py`.

## Dev Notes

### Implementation snippet — SQLHandler chain init

```python
if self._chain_mode:
    if self._engine.dialect.name == "sqlite":
        with self._engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        # AC1 — block writes if a previous verify reported BROKEN.
        from .._verify_state import read_verify_state
        db_path = Path(self._url.replace("sqlite:///", "", 1))
        state = read_verify_state(db_path)
        if state and state.get("status") == "BROKEN":
            raise SchemaError(
                f"chain integrity is BROKEN at #{state.get('broken_at')}. "
                "Run `ulog repair --confirm` to resolve before re-opening "
                "the handler in chain mode."
            )
    from .._chain import SQLiteChainWriter
    self._chain_writer = SQLiteChainWriter(self._engine, self._table_name)
```

### immutable_when corrected snippet

```python
import sys
# (replace warnings.warn block with):
except Exception as exc:  # noqa: BLE001 intentional fail-safe
    if not self._immutable_when_warned:
        print(
            f"ulog: immutable_when callable raised "
            f"{type(exc).__name__}: {exc!r}; treating as immutable=1 "
            "(Decision B5 fail-safe)",
            file=sys.stderr,
        )
        self._immutable_when_warned = True
    immutable_flag = 1  # fail-safe (Decision B5)
```

## References

- [Source: epics.md, lines 1279-1303] — Story 3.12 AC
- [Source: architecture.md, lines 686-691] — Decision B5 fail-safe
- [Source: ulog/_verify_state.py] — read_verify_state + sidecar_path

## Dev Agent Record

### Completion Notes List

- **Story 3.6 fail-safe corrected**: `immutable_when` raise now sets
  `immutable=1` (was 0) + stderr `print` (was `warnings.warn`). Aligns
  with Decision B5 — preserve forensic evidence rather than risk
  silently making a record mutable. Story 3.6 test
  `test_immutable_when_callable_raising_falls_back_safe` updated to
  assert the new behaviour (and removed the now-unused `warnings`
  import).
- `SQLHandler.__init__` chain-mode block now reads `<db>.verify_state.json`
  via `_verify_state.read_verify_state`. If `status=="BROKEN"` →
  `SchemaError` with the repair instruction. Lifts once repair clears
  the sidecar.
- `cmd_repair.run` now deletes the verify_state sidecar after
  successful archive+delete (`unlink(missing_ok=True)`).
- 5 new tests in `tests/test_chain_edge_cases.py`:
  AC1 broken-state-blocks-chain-setup (+ negative test for non-chain),
  AC2 immutable_when-raise fail-safe (immutable=1 + stderr + one-shot),
  AC3 tampered-record_hash detected as BROKEN, AC4 retention floor
  regression, AC5 repair clears sidecar + chain setup succeeds again.
- 108 affected-area tests green across the whole Epic 3 stack.
  mypy --strict, ruff check, ruff format clean.

### File List

- `ulog/handlers/sql.py` — `_record_to_row` fail-safe direction fix;
  `__init__` reads verify_state sidecar in chain mode.
- `ulog/_cli/cmd_repair.py` — unlinks sidecar after successful repair.
- `tests/test_setup_v05_params.py` — corrected fail-safe assertion.
- `tests/test_chain_edge_cases.py` (NEW) — 5 edge case tests.
