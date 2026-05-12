# Story 3.10: Integrity badge data plumbing — `<db>.verify_state.json` sidecar

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-10-integrity-badge-data-plumbing-verify-state-json-sidecar`
**Implements:** Decision D2 (verify result cached to sidecar JSON for cheap UI badge reads).
**Built on:** 3.7 (`ulog verify` runs the walk).

## Story

As a **backend for the UI integrity badge**,
I want **`ulog verify` to write its result to `<db>.verify_state.json`**,
so that **the viewer can read the cached status cheaply on every page load (no re-walk)**.

## Acceptance Criteria

1. **OK path** — after successful walk, `<db>.verify_state.json` is written with: `verified_up_to_chain_pos: <int>`, `last_check_ts: <ISO>`, `status: "OK"`, `broken_at: null`, `walk_time_s: <float>`.
2. **BROKEN path** — `status: "BROKEN"`, `broken_at: <chain_pos>`, `verified_up_to_chain_pos: <last_good_pos>` (the chain_pos just before the break, or 0 if the break is at chain_pos=1).
3. **Missing sidecar gracefully degrades** — when the viewer reads a missing `verify_state.json`, it does NOT crash; a helper `read_verify_state(db_path) -> dict | None` returns `None`.
4. **Sidecar location** — same directory as the DB; filename = `<db_stem>.verify_state.json` (e.g., `logs.sqlite` → `logs.verify_state.json`).
5. **Range walks DO NOT write the sidecar** — `ulog verify --range A-B` is partial; writing it would mislead the UI badge into thinking the whole chain was verified. Only full-chain walks write.
6. **JSON is atomic-ish** — write to a temp file in the same directory, then `os.replace` to the final path (avoids torn-write on crash). Stdlib only.
7. **Tests** — `tests/test_verify_state_sidecar.py`:
   - `test_verify_writes_ok_sidecar_on_healthy_chain`
   - `test_verify_writes_broken_sidecar_on_break`
   - `test_verify_range_does_not_write_sidecar` (AC5)
   - `test_read_verify_state_returns_none_when_missing`
   - `test_verify_state_json_keys_present`
   - `test_verify_state_sidecar_atomic_write` (verify temp file is gone after success)

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/_verify_state.py`** (NEW)
  - [ ] `STATE_VERSION = 1` constant.
  - [ ] `write_verify_state(db_path: Path, payload: dict) -> None` — atomic-ish.
  - [ ] `read_verify_state(db_path: Path) -> dict | None`.
- [ ] **Task 2 — `cmd_verify.run` writes sidecar on full-chain walks**
  - [ ] Skip write when `--range` is set.
  - [ ] On OK: write with `status="OK"`, `verified_up_to_chain_pos=last_pos`, `broken_at=None`.
  - [ ] On BROKEN: write with `status="BROKEN"`, `broken_at=<pos>`, `verified_up_to_chain_pos=<pos-1>`.
- [ ] **Task 3 — Tests**.
- [ ] **Task 4 — Validation**.

## Dev Notes

```python
# ulog/_verify_state.py
import json, os
from pathlib import Path

STATE_VERSION = 1

def sidecar_path(db_path: Path) -> Path:
    return db_path.with_suffix(".verify_state.json")

def write_verify_state(db_path: Path, payload: dict) -> None:
    target = sidecar_path(db_path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps({"version": STATE_VERSION, **payload}, indent=2), encoding="utf-8")
    os.replace(tmp, target)

def read_verify_state(db_path: Path) -> dict | None:
    target = sidecar_path(db_path)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))
```

In `cmd_verify.run`, after the loop, if not `--range`, call `write_verify_state`.

## References

- [Source: epics.md, lines 1239-1257] — Story 3.10
- [Source: architecture.md, Decision D2] — verify_state sidecar

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m]

### Completion Notes List

- New module `ulog/_verify_state.py` (~40 lines) with
  `sidecar_path`, `write_verify_state`, `read_verify_state` and a
  `STATE_VERSION = 1` constant.
- Atomic-ish write: temp file in the same directory + `os.replace`
  to the final path (avoids torn writes on crash). Stdlib only.
- `cmd_verify.run` now writes the sidecar on FULL-chain walks only
  (skip when `--range` is set per AC5) — added helper
  `_maybe_write_state` to keep the OK / BROKEN branches DRY. Last
  good chain_pos tracked across the walk so BROKEN reports include
  `verified_up_to_chain_pos` correctly.
- Sidecar JSON payload: `{version, status, broken_at,
  verified_up_to_chain_pos, last_check_ts, walk_time_s}`.
- 9 / 9 tests in `tests/test_verify_state_sidecar.py` green: missing
  → None, OK write, BROKEN write, range NO write, key schema check,
  atomic write (no .tmp leftover), overwrite on re-run, sidecar
  path helper, valid JSON. mypy strict (one explicit cast for
  `json.loads`), ruff, format clean. Zero new deps.

### File List

- `ulog/_verify_state.py` (NEW)
- `ulog/_cli/cmd_verify.py` — added `_maybe_write_state` + write
  on OK + write on each BROKEN branch + `last_good_pos` tracking.
- `tests/test_verify_state_sidecar.py` (NEW) — 9 tests.
