# Story 9.6: v0.9 Resources sidebar panel

Status: done

**Epic:** 9 — BMAD catch-up ledger (v0.7 → v0.9)
**PRD:** `docs/prds/PRD-v0.9-resource-validity.md`
**Shipped as:** v0.9.0 phase 2

## Scope Recorded

- Viewer Resources sidebar panel.
- Panel enabled by `ULOG_RESOURCES_DIR`.
- Resource scan results cached for viewer lifetime.
- Broken/OK resource counts rendered in the sidebar.
- Panel hidden when the environment variable is unset.

## Implementation Evidence

- Commit: `d14b6a1` — `feat(v0.9-ui): Resources sidebar panel (phase 2)`
- Files:
  - resource scan/cache helpers under `ulog/web/`
  - sidebar template integration

## Regression Tests

- `tests/test_resources_sidebar.py`

## Notes

This artifact regularizes already-shipped work. No production code was changed while creating this BMAD record.
