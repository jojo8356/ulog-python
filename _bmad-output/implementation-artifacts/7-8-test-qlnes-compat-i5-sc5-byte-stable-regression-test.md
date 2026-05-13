# Story 7.8: `tests/test_qlnes_compat.py` — I5/SC5 byte-stable regression test

Status: done

**Epic:** 7 — v0.5 release consolidation
**Implements:** SC5, I5 gate.

## Completion Notes

- `tests/test_qlnes_compat.py` pins the v0.1 baseline byte sequences
  for the qlnes + simple formatters across 5 levels.
- 9 / 9 tests green.
- Confirms `qlnes` formatter contract: INFO/DEBUG → bare msg;
  WARNING/ERROR/CRITICAL → `<prefix>: <level>: <msg>\n`.

## File List

- `tests/test_qlnes_compat.py` (NEW)
