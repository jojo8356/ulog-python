# Story 4.10: PRD-v0.5 §2.3 edge case — replay write attempt

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-10-prd-v0-5-edge-case-replay-write-attempt`
**Implements:** NFR-REL-51 (replay records do NOT advance the chain).
**Built on:** Story 4.2 (`_REPLAY_ACTIVE` contextvar + `is_replay` column).

## Story

When records are emitted DURING a `replay()` body in chain mode, they must be persisted with `is_replay=True` BUT MUST NOT advance the chain (`record_hash`/`prev_hash` stay NULL).

## Acceptance Criteria

1. **`SQLHandler.emit`**: when `chain_mode=True` AND `is_replaying()`, the record goes through the buffered/non-chain path (NOT the chain writer).
2. **Schema effect**: replay-emitted record lands with `chain_pos=0`, `record_hash=NULL`, `prev_hash=NULL`, `is_replay=1`.
3. **Chain integrity preserved**: pre-existing chain (chain_pos 1..N) is unaffected. `ulog verify` continues to pass (replay records skipped by the `WHERE record_hash IS NOT NULL` filter).
4. **Story 4.2 test updated**: the `test_record_inside_replay_chain_mode_persists_is_replay_1` test was asserting the replay record advances chain_pos — that's wrong post-4.10. Re-asserts the new contract.
5. **Tests** — new + updated:
   - `test_replay_emitted_record_does_not_advance_chain` (chain_pos stays 0, hashes NULL).
   - `test_verify_skips_replay_records` (verify still OK after replay).
   - `test_chain_pos_max_unchanged_after_replay` (no new chain entries).

## Tasks / Subtasks

- [ ] One-line change in `SQLHandler.emit`: branch on `is_replay`.
- [ ] Update Story 4.2 test.
- [ ] 3 new tests in `tests/test_replay_state.py`.

## Dev Agent Record

### Completion Notes List

- One-line branch change in `SQLHandler.emit`: when
  `chain_mode AND row["is_replay"] == 0` → chain writer;
  otherwise (non-chain mode OR is_replay=1) → buffered path.
- Replay-emitted records land with `chain_pos=0` (server
  default), `record_hash=NULL`, `prev_hash=NULL`, `is_replay=1`.
- Chain integrity preserved: `ulog verify` filters
  `WHERE record_hash IS NOT NULL` so it skips replay records.
- Story 4.2's test `test_record_inside_replay_chain_mode_persists_is_replay_1`
  renamed + updated to assert the new contract (chain NOT advanced).
- 2 new tests in `test_replay_state.py`:
  `test_chain_pos_max_unchanged_after_replay` (no chain
  advance), `test_verify_skips_replay_records` (verify still
  passes after replay pollution).
- 620 / 620 full-suite tests green (excl. slow + qa_perf).
- mypy --strict / ruff / format / deptry all clean.

### File List

- `ulog/handlers/sql.py` — `emit()` branch on `is_replay`.
- `tests/test_replay_state.py` — Story 4.2 test renamed +
  contract updated; 2 new Story 4.10 tests appended.
