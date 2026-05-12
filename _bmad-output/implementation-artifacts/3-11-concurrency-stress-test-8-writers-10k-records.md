# Story 3.11: Concurrency stress test (8 writers × 10K records)

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-11-concurrency-stress-test-8-writers-10k-records`
**Implements:** NFR-REL-50 (chain unbroken under 8-writer × 10K-record load).
**Built on:** 3.4 (`SQLiteChainWriter` with BEGIN IMMEDIATE), 3.5 (`SQLHandler` chain mode + WAL pragma), 3.7 (`ulog verify` walks the chain end-to-end).

## Story

As a **release manager preparing the v0.5.0 tag**,
I want **a stress test that spawns 8 concurrent writer subprocesses each emitting 10K records to a shared SQLite DB**,
so that **chain integrity is empirically validated under real multi-process contention** before tagging.

## Acceptance Criteria

1. **8 subprocesses × 10K records** — total 80K rows persisted to a shared SQLite DB in chain mode. No "database is locked" stderr noise from any worker (BEGIN IMMEDIATE serialises cleanly).
2. **Chain is unbroken** — `ulog verify` after the run returns OK with `records: 80000`.
3. **Marker** — test is decorated `@pytest.mark.slow` so the fast suite skips it by default. CI/release-gate runs `pytest -m slow`.
4. **Wall time tolerance** — completes in ≤ 60 s on Linux developer machine (CI may need 2× headroom — left as a soft target).
5. **Self-contained** — uses `subprocess.run` with `sys.executable` to spawn workers; each worker runs a tiny inline script. No external runner.
6. **No regression in fast suite** — fast suite still passes; the slow test only fires with `-m slow`.

## Tasks / Subtasks

- [ ] **Task 1 — `tests/test_chain_concurrency.py` (NEW)**
  - [ ] 1.1 — `@pytest.mark.slow` decorator on the single test.
  - [ ] 1.2 — Spawn 8 subprocesses, each running `python -c "import ulog; ulog.setup(integrity='hash-chain', ...); log = ulog.get_logger(); for i in range(10000): log.info('w%d-%d', worker_id, i); for h in logging.getLogger().handlers: h.flush()"`.
  - [ ] 1.3 — Wait for all to complete, assert all exit 0.
  - [ ] 1.4 — Run `ulog verify <db>` via `main(...)`, assert exit 0 + records=80000.
- [ ] **Task 2 — Register the `slow` marker** in `pyproject.toml` so pytest doesn't warn.

## Dev Notes

### Worker script (inline)

```python
import logging, sys
import ulog

worker_id = int(sys.argv[1])
db_url = sys.argv[2]
ulog.setup(integrity='hash-chain', handlers=['sql'], sql_url=db_url, sql_batch_size=1)
log = ulog.get_logger()
for i in range(10000):
    log.info("w%d-%d", worker_id, i)
for h in logging.getLogger().handlers:
    h.flush()
```

### Verification

Use the `ulog._cli.main` entry directly: `rc = main(["verify", str(db)])` + parse stdout for `records: 80000`.

### Pytest marker registration

In `pyproject.toml` `[tool.pytest.ini_options]`:
```toml
markers = ["slow: long-running tests (run with `-m slow`)"]
```

## References

- [Source: epics.md, lines 1261-1275] — Story 3.11 AC
- [Source: ulog/_chain.py] — `SQLiteChainWriter` BEGIN IMMEDIATE wiring
- [Source: tests/test_chain_emit.py::test_chain_concurrent_emit_serialised] — single-process 4-thread analogue

## Dev Agent Record

### Completion Notes List

- **Bug surfaced and fixed**: the original `SQLHandler._chain_append`
  used `get_last_hash()` + `append()` as two separate transactions.
  Under 8 concurrent procs, two workers could read the same
  `prev_hash` before either INSERTed → diverging chains, BROKEN at
  ~record 272 in the first stress run.
  Fix: new `SQLiteChainWriter.append_atomic(record, hash_fn)` does
  get-prev-hash + compute + INSERT inside ONE `BEGIN IMMEDIATE` txn.
  `_chain_append` now calls `append_atomic(row, sha256_record)`. The
  original `append()` stays for the Protocol contract / verify tests.
- 8 subprocesses × 10K records → 80K rows persisted, chain OK end-
  to-end. Wall time ~91s on dev machine.
- Test marked `@pytest.mark.slow` + `markers` registered in
  `pyproject.toml`. Fast suite excludes by default (use `-m slow`).
- 46 existing chain tests (test_chain + test_chain_emit + test_handlers)
  still green — append_atomic refactor backwards-compat. mypy strict,
  ruff check, ruff format, deptry all clean.

### File List

- `ulog/_chain.py` — added `SQLiteChainWriter.append_atomic`.
- `ulog/handlers/sql.py` — `_chain_append` uses `append_atomic`.
- `pyproject.toml` — registered `slow` marker.
- `tests/test_chain_concurrency.py` (NEW) — 1 stress test, slow-marked.
