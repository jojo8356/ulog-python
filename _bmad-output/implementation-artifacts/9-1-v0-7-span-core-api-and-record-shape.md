# Story 9.1: v0.7 span core API and SQL record shape

Status: done

**Epic:** 9 — BMAD catch-up ledger (v0.7 → v0.9)
**PRD:** `docs/prds/PRD-v0.7-test-execution-stack.md`
**Shipped as:** v0.7.0

## Scope Recorded

- `ulog.span(name)` context manager.
- `ulog.current_span_id()`.
- Span records emitted on `logger='ulog.span'`.
- Context payload includes `span_id`, `parent_span_id`, `span_name`, `span_ms`, and `span_status`.
- Nested spans form a parent-child tree via contextvars.

## Implementation Evidence

- Commit: `32c222b` — `feat(v0.7): span-based execution timeline (phase 1)`
- Files:
  - `ulog/spans.py`
  - `ulog/__init__.py`
  - `ulog/handlers/sql.py`

## Regression Tests

- `tests/test_spans.py`

## Notes

This artifact regularizes already-shipped work. No production code was changed while creating this BMAD record.
