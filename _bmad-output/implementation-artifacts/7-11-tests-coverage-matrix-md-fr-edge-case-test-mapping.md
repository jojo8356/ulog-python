# Story 7.11: `tests/coverage_matrix.md` — FR/edge-case → test mapping

Status: done

**Epic:** 7 — v0.5 release consolidation
**Implements:** SC3 secondary indicator.

## Completion Notes

- `tests/coverage_matrix.md` maps every FR (FR51-FR117) and every
  PRD §2.3 edge case to ≥1 test name.
- Organized by Epic (1-7); ~75 rows.
- Verification snippet at bottom (pytest collect-only loop)
  helps catch test renames before they silently break the matrix.

## File List

- `tests/coverage_matrix.md` (NEW)
