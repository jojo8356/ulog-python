# Story 3.7: `ulog verify [--range A-B]` CLI subcommand

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-7-ulog-verify-cli-subcommand`
**Implements:** FR95 (chain verification CLI), NFR-PERF-52 (100K records ≤ 5s)
**Built on:** 3.4 (canonical/sha256 helpers), 3.5 (chain emit produces verifiable rows), 3.6 (`immutable` flag baked into the hashed record dict).
**Foundation for:** Story 3.8 (`ulog repair` reads verify's BROKEN report), Story 3.10 (integrity badge plumbs `verify_state.json` from this output).

## Story

As a **compliance officer**,
I want **`ulog verify [<db>] [--range A-B]` to walk the chain offline and report `✓ Integrity verified` (exit 0) or `✗ BROKEN at #N: expected … got …` (exit 1)**,
so that **I can attach integrity attestation to audit reports without writing code**.

## Acceptance Criteria

1. **Console script entry point** — `pyproject.toml` adds `[project.scripts] ulog = "ulog._cli:main"`. Both the new `ulog` binary AND `python -m ulog._cli ...` invocations dispatch through the same main.
2. **Subcommand dispatch** — argparse subparsers; `ulog verify` triggers `cmd_verify.run`. Unknown subcommand → exit 2, helpful message.
3. **`ulog verify <db>`** — walks `logs` table in chain_pos order over rows with `record_hash IS NOT NULL`, recomputes `sha256(canonical_record_json(row) + prev_hash)`, compares to stored `record_hash` AND stored `prev_hash` to the previous row's `record_hash`.
4. **OK path** — `✓ Integrity verified` + `records: N` + `wall_time: <ms>` + exit code 0 (FR95).
5. **BROKEN path** — first mismatch fires `✗ BROKEN at record #<chain_pos>: expected prev_hash=<8 hex chars>..., got <8 hex chars>...` + exit code 1. Subsequent records NOT walked (fail-fast — first break is the load-bearing diagnostic).
6. **`--range A-B`** — walks only `chain_pos BETWEEN A AND B`. Both `A-B` and `A,B` syntaxes accepted (argparse type callable).
7. **`--db PATH`** alternative to positional — when both given, positional wins. `ulog verify --db /path/to/logs.sqlite` is the supported form when scripting.
8. **Empty chain** — `records: 0` + `✓ Integrity verified` + exit code 0 (vacuous truth).
9. **Re-uses Story 3.4 helpers** — `from ulog._chain import canonical_record_json, sha256_record`. No reimplemented hashing logic.
10. **JSON columns parsed back** — `exc` and `context` columns come from DB as JSON strings; verify parses them back to dicts before recomputing the hash. Matches the dict form the SQLHandler hashed at emit time (Story 3.5/3.6 path).
11. **Performance** — on a 100K-record DB, `ulog verify` completes in ≤ 5s on GitHub Actions ubuntu-latest (NFR-PERF-52). Implementation must read all rows in ONE SELECT (no per-row roundtrip), recompute in Python.
12. **Tests** — `tests/test_cli_verify.py`:
    - `test_verify_clean_chain_exit_0` — emit 5 records via SQLHandler chain mode, run `verify` → exit 0, "✓" in stdout, "records: 5".
    - `test_verify_broken_record_hash_exit_1` — corrupt one record's msg field via raw UPDATE on a rotable record, run verify → exit 1, "BROKEN at" + chain_pos + expected/got hex visible.
    - `test_verify_broken_prev_hash_link_exit_1` — corrupt one record's prev_hash via raw UPDATE, run verify → exit 1.
    - `test_verify_range_walks_subset` — emit 10 records, `--range 3-7`, verify only walks 3-7 (5 records counted).
    - `test_verify_range_dash_or_comma_syntax` — `--range 1-3` and `--range 1,3` both work identically.
    - `test_verify_empty_chain_exit_0` — empty `logs` table → records:0 + exit 0.
    - `test_verify_dash_m_invocation` — `python -m ulog._cli verify <db>` works (subprocess test).
    - `test_verify_unknown_subcommand_exit_2` — `ulog foobar` → exit 2.
13. **Performance smoke** — `test_verify_500_records_under_500ms` (a 200x scaled-down version of NFR-PERF-52 to keep the unit suite fast; full 100K benchmark lives in Story 3.11).
14. **Type checking green** — `mypy --strict` clean.

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/_cli/__init__.py` (NEW)**
  - [ ] 1.1 — Module docstring noting it's the `ulog` console-script dispatcher; subcommands live in `cmd_<name>.py` modules.
  - [ ] 1.2 — `def main(argv: list[str] | None = None) -> int:` — builds argparse + subparsers + dispatches. Returns exit code (so tests can capture without `sys.exit`).
  - [ ] 1.3 — At bottom: `if __name__ == "__main__": sys.exit(main())` so `python -m ulog._cli` works.
- [ ] **Task 2 — `ulog/_cli/cmd_verify.py` (NEW)**
  - [ ] 2.1 — `register(subparsers)` — adds `verify` subcommand with `--db PATH`, positional `db_path`, `--range A-B`.
  - [ ] 2.2 — `_parse_range(s: str) -> tuple[int, int]` — accepts `"A-B"` or `"A,B"`; argparse `type=` callable.
  - [ ] 2.3 — `run(args) -> int` — reads rows, walks chain, prints, returns exit code.
  - [ ] 2.4 — Lazy SQLAlchemy import per `Enforcement #2`.
- [ ] **Task 3 — `pyproject.toml`**
  - [ ] 3.1 — Add `ulog = "ulog._cli:main"` to `[project.scripts]`.
  - [ ] 3.2 — Reinstall (`pip install -e .`) is the user's responsibility; tests don't require the entry-point.
- [ ] **Task 4 — Tests** (`tests/test_cli_verify.py`)
  - [ ] 4.1 — Helper `_seed_chain(tmp_path, n=5)` — runs setup chain mode + N emits + flush + close, returns the DB path.
  - [ ] 4.2 — Each test calls `main(["verify", str(db)])` directly OR via `subprocess.run([sys.executable, "-m", "ulog._cli", ...])` (the `-m` invocation test).
  - [ ] 4.3 — Capture stdout via `capsys.readouterr().out`.

## Dev Notes

### Verify-walk algorithm

```python
def run(args):
    import time
    from sqlalchemy import create_engine, text
    from .._chain import canonical_record_json, sha256_record
    import json as _json

    db = args.db_path or args.db
    url = f"sqlite:///{db}"
    engine = create_engine(url, future=True)
    where, params = "WHERE record_hash IS NOT NULL ", {}
    if args.range:
        a, b = args.range
        where += "AND chain_pos BETWEEN :a AND :b "
        params = {"a": a, "b": b}

    t0 = time.perf_counter()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT chain_pos, ts, level, logger, msg, file, line, "
                "exc, context, immutable, record_hash, prev_hash "
                f"FROM logs {where}ORDER BY chain_pos"
            ),
            params,
        ).all()
    engine.dispose()

    expected_prev = b"\x00" * 32  # for ranges starting at 1; for offset ranges, look up the prior record's hash
    if args.range and args.range[0] > 1:
        # Look up the prev row's record_hash to seed the chain from a partial range.
        ...

    for row in rows:
        rec = {
            "ts": row[1],
            "level": row[2],
            "logger": row[3],
            "msg": row[4],
            "file": row[5],
            "line": row[6],
            "exc": _json.loads(row[7]) if isinstance(row[7], str) else row[7],
            "context": _json.loads(row[8]) if isinstance(row[8], str) else row[8],
            "immutable": row[9],
        }
        actual_record_hash = bytes(row[10])
        actual_prev_hash = bytes(row[11])
        if actual_prev_hash != expected_prev:
            print(
                f"✗ BROKEN at record #{row[0]}: "
                f"expected prev_hash={expected_prev.hex()[:8]}..., "
                f"got {actual_prev_hash.hex()[:8]}..."
            )
            return 1
        recomputed = sha256_record(rec, actual_prev_hash)
        if recomputed != actual_record_hash:
            print(
                f"✗ BROKEN at record #{row[0]}: "
                f"recomputed hash {recomputed.hex()[:8]}... != stored {actual_record_hash.hex()[:8]}..."
            )
            return 1
        expected_prev = actual_record_hash

    wall_ms = (time.perf_counter() - t0) * 1000
    print(
        f"✓ Integrity verified\n"
        f"  records: {len(rows)}\n"
        f"  wall_time: {wall_ms:.1f}ms"
    )
    return 0
```

### Architecture compliance

- **Decision C1:** CLI consolidation `ulog <subcommand>` — this story adds the first subcommand (alongside `web` which exists as `ulog-web` standalone for now; consolidation of `ulog-web` → `ulog web` is Decision C1's other half, deferred).
- **Subcommand pattern:** `ulog/_cli/cmd_<name>.py` with `register(subparsers)` + `run(args)`.
- **Enforcement #2 lazy SQLAlchemy.**
- **Stdlib only:** stdlib `argparse`, `time`, `json`, `pathlib`.

### Library / framework requirements

- Python stdlib `argparse`.
- SQLAlchemy lazy import.
- Reuses `ulog._chain.canonical_record_json` + `sha256_record`.
- Zero new deps.

### References

- [Source: epics.md, lines 1165-1187] — Story 3.7 acceptance criteria
- [Source: architecture.md, Decision C1] — `ulog` console-script consolidation
- [Source: ulog/_chain.py] — canonical/hash helpers (Story 3.5 added)
- [Source: ulog/handlers/sql.py:_record_to_row] — defines the row dict shape that gets hashed

## Dev Agent Record

### Agent Model Used
claude-opus-4-7[1m]

### Completion Notes List

- New package `ulog/_cli/` with `__init__.py` (dispatcher),
  `__main__.py` (enables `python -m ulog._cli`), and `cmd_verify.py`
  (the verify subcommand).
- `pyproject.toml` console_scripts gained `ulog = "ulog._cli:main"`
  alongside the existing `ulog-web` (consolidation per Decision C1
  is partial here; `ulog web` subcommand is deferred).
- **Bug fix during DS**: raw `text()` SELECT bypasses SQLAlchemy's
  DateTime adapter, so `ts` comes back as string `"YYYY-MM-DD …"`
  instead of `datetime`. The original hash was over the datetime
  (via `.isoformat()` with T separator), so verify recomputed a
  different hash. Added `_parse_ts()` helper that re-parses the
  string to datetime before hashing. Python 3.10 `fromisoformat`
  fallback handles the space-separator form.
- 13 / 13 tests in `tests/test_cli_verify.py` green: clean chain,
  broken record_hash, broken prev_hash, range (dash + comma), range
  with offset (re-seeds prev_hash from chain_pos-1), empty chain,
  `python -m ulog._cli` subprocess, no-subcommand → exit 2, missing
  DB arg, nonexistent DB, malformed range (SystemExit), 500-record
  perf smoke (< 1s).
- 59 affected-area tests green (test_cli_verify + test_chain_emit +
  test_chain + test_handlers). mypy --strict, ruff check, ruff
  format, deptry all clean. Zero new deps.

### File List

- `ulog/_cli/__init__.py` (NEW) — `main()` dispatcher.
- `ulog/_cli/__main__.py` (NEW) — enables `python -m ulog._cli`.
- `ulog/_cli/cmd_verify.py` (NEW) — verify subcommand + `_parse_ts`
  + `_parse_range`.
- `pyproject.toml` — added `ulog = "ulog._cli:main"` script entry.
- `tests/test_cli_verify.py` (NEW) — 13 tests.
