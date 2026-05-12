# Story 5.6: PRD-v0.5 §2.3 edge cases — resolve unknown / already-resolved

Status: done

**Epic:** 5 — v0.5 Incident lifecycle
**Story key:** `5-6-prd-v0-5-edge-cases-resolve-unknown-already-resolved`

## Story

As a release manager,
I want both incident edge cases covered by ≥1 test,
so that surprising user inputs don't silently corrupt the chain.

## Acceptance Criteria

1. `resolve(unknown_hash)` → `LookupError`, no record emitted.
2. `resolve(h)` twice in sequence → two RESOLVED rows in the chain;
   latest wins per state walk.

## Dev Agent Record

### Completion Notes List

- `test_resolve_unknown_raises_no_record_emitted` (5.1 + 5.6).
- `test_resolve_twice_emits_two_records` (5.2 + 5.6).
- Both in `tests/test_incidents.py`.

### File List

- `tests/test_incidents.py`
