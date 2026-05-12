# Story 3.8: `ulog repair --confirm` CLI subcommand

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-8-ulog-repair-confirm-cli-subcommand`
**Implements:** FR97 (`ulog repair`), NFR-REL-52 (idempotent on healthy chain), invariant I4 (cannot remove immutable rows).
**Built on:** 3.4-3.7 (chain + verify).

## Story

As a **compliance officer responding to `verify` returning BROKEN at #N**,
I want **`ulog repair --confirm` to truncate the chain at the last valid record and archive orphans into a sidecar JSONL**,
so that **the live DB regains write capability while broken records are preserved off-chain for audit**.

## Acceptance Criteria

1. **`ulog repair <db>` (no --confirm)** — refuses with `"Use --confirm to proceed; this is destructive of the live chain."` + exit code 2.
2. **`ulog repair --confirm <db>` on a healthy chain** — no-op. Reports `✓ Chain is healthy — nothing to repair.` + exit code 0. Idempotent (NFR-REL-52).
3. **`ulog repair --confirm <db>` on a broken chain** — internally runs the verify walk to find the first broken `chain_pos = N`. All rows with `chain_pos >= N` are:
   - Written to `<db>.chain_break_<UTC-ISO>.log` (one JSON object per line — same shape as JSONLineHandler's output for compatibility with the viewer).
   - DELETEd from the live DB.
   - Reports `✓ Repaired: archived <count> orphans to <sidecar_path>` + exit code 0.
4. **Immutable-orphan refusal** — if any orphan row has `immutable=1`, repair REFUSES with `"✗ Cannot repair: immutable orphan at #N. Invariant I4 forbids removal. Manual forensic review required."` + exit code 1. No sidecar is written, no rows deleted.
5. **Idempotency after success** — running `repair --confirm` again on the same (now-healed) DB returns the AC2 healthy-chain no-op.
6. **Sidecar JSONL format** — each line is `json.dumps(row_dict)`. `row_dict` keys: `chain_pos`, `ts` (ISO string), `level`, `logger`, `msg`, `file`, `line`, `exc`, `context`, `immutable`, `record_hash` (hex), `prev_hash` (hex). Bytes columns converted to hex for JSON safety; downstream JSONL viewer can decode.
7. **Re-uses verify walk** — call `cmd_verify.run` internally OR factor the walk into a shared helper. Pragmatic: import `_parse_ts` + `sha256_record` + walk logic in `cmd_repair`. **Decision**: keep the walk inline in `cmd_repair` (it's <40 lines), avoid the test pollution of subprocess-style integration.
8. **Tests** — `tests/test_cli_repair.py`:
   - `test_repair_without_confirm_refuses` — exit 2 + "--confirm" in stderr.
   - `test_repair_on_healthy_chain_is_noop` — exit 0 + "healthy" in stdout + no sidecar created.
   - `test_repair_broken_chain_archives_and_deletes` — emit 5, corrupt row 3, repair → sidecar exists with 3 JSON lines (rows 3/4/5), live DB has only rows 1-2.
   - `test_repair_idempotent_after_success` — run repair twice; second call is healthy-chain no-op.
   - `test_repair_refuses_immutable_orphan` — emit 5 records with immutable_when=lambda r: chain_pos==4 (effectively), then corrupt row 3 → repair refuses with exit 1, message mentions I4, no sidecar, no deletes.
     Implementation note: pytest can't easily target chain_pos in immutable_when; use `lambda r: r.msg == "rec3"` for one INFO record then ensure it has chain_pos=4 by emitting 4 records total. Simpler: emit 1 normal then 1 ERROR (immutable=1) under chain mode, corrupt the normal one, attempt repair.
   - `test_repair_sidecar_jsonl_format` — sidecar lines parse cleanly with `json.loads`, contain expected keys + hex hashes.
   - `test_repair_python_m_invocation` — `python -m ulog._cli repair --confirm <db>` works (subprocess).

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/_cli/cmd_repair.py` (NEW)**
  - [ ] 1.1 — Module docstring describing Story 3.8 + FR97 + I4 immutable refusal.
  - [ ] 1.2 — `register(subparsers)` adds `repair` subcommand with `--confirm` flag, positional `db_path`, `--db` alternative.
  - [ ] 1.3 — `_walk_chain_for_break(engine) -> int | None` — returns the chain_pos of the first broken record, or None if healthy. Reuses `sha256_record` + `_parse_ts`.
  - [ ] 1.4 — `run(args)` — orchestrates: walk → if healthy → return 0; if broken → check immutable → write sidecar → DELETE → return 0.
- [ ] **Task 2 — Register in dispatcher**
  - [ ] 2.1 — `ulog/_cli/__init__.py` — `from . import cmd_repair` and `cmd_repair.register(subparsers)`.
- [ ] **Task 3 — Tests** (`tests/test_cli_repair.py`)
  - [ ] 3.1 — Reuse `_seed_chain` style helper from test_cli_verify.
  - [ ] 3.2 — Tests per AC8.
- [ ] **Task 4 — Validation**
  - [ ] 4.1 — pytest, mypy, ruff, deptry green.

## Dev Notes

### Sidecar naming + format

```
<db_dir>/<db_stem>.chain_break_<UTC_ISO_no_colons>.log
e.g. logs.sqlite → logs.chain_break_2026-05-12T12-34-56Z.log
```

`<UTC_ISO_no_colons>`: `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")` — colons replaced with hyphens (Windows-safe filename).

Each line: `json.dumps({"chain_pos": ..., "ts": <iso>, "level": ..., "msg": ..., "file": ..., "line": ..., "exc": <obj|None>, "context": <obj|None>, "immutable": 0|1, "record_hash": "<hex>", "prev_hash": "<hex>"})`.

### Walk algorithm (compact, inline)

Identical to `cmd_verify` but returns `chain_pos` of first failure instead of printing+exiting. Skip rows with `record_hash IS NULL` (pre-chain backfilled per Gap G1).

### References

- [Source: epics.md, lines 1191-1209] — Story 3.8 acceptance criteria
- [Source: architecture.md, line 1240] — I4 (repair archives, never deletes immutable rows)
- [Source: ulog/_cli/cmd_verify.py] — walk algorithm to mirror

## Dev Agent Record

### Completion Notes List

- `ulog/_cli/cmd_repair.py` — `register/run` + private helpers
  `_find_first_break(conn)`, `_sidecar_path(db)`, `_row_to_jsonl(row)`.
  Walk algorithm mirrors `cmd_verify.run` but returns the chain_pos
  of the first failure (or None for healthy) instead of printing.
- Sidecar naming: `<db_stem>.chain_break_<UTC-no-colons>.log` (Windows-
  safe — colons replaced with hyphens). Each line is JSON; bytes
  columns hex-encoded for JSON safety.
- Immutable-orphan path enforces invariant I4: if any orphan has
  `immutable=1`, repair refuses with exit 1 + clear stderr message
  + "I4" tag for grep. No sidecar, no deletes.
- 9 / 9 tests in `tests/test_cli_repair.py` green: no-confirm refusal,
  missing db, nonexistent db, healthy-chain no-op, idempotent after
  success, broken-chain archive+delete, sidecar JSONL format,
  immutable-orphan refusal, `python -m ulog._cli repair`.
- 72 affected-area tests green. mypy --strict, ruff check, ruff
  format (after auto-fix), deptry all clean. Zero new deps.

### File List

- `ulog/_cli/cmd_repair.py` (NEW)
- `ulog/_cli/__init__.py` — imported + registered cmd_repair
- `tests/test_cli_repair.py` (NEW) — 9 tests
