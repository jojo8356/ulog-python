# Story 6.10: PRD-v0.5 §2.3 edge case — OTel SDK absent

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-10-prd-v0-5-edge-case-otel-sdk-absent`
**Implements:** FR109 no-op silent fallback (Gap G4).
**Built on:** Story 6.1.

## Story

When neither `_OTEL_TRACE_CONTEXT` nor `traceparent` env is set, ulog
must silently emit records without trace_id/span_id — no warning,
no error, no mention of OTel anywhere in the user-facing surface.

## Coverage

ACs are covered by Story 6.1's existing tests:

| AC | Test |
|---|---|
| Records have no trace_id when no source set | `test_record_emitted_without_otel_context_has_no_trace_id` |
| `current_trace_context()` returns None | `test_no_otel_context_returns_none` |
| No `import opentelemetry` anywhere | `test_no_opentelemetry_import_anywhere` |
| `ulog --help` doesn't mention OTel | Manual verification (covered by `test_help_does_not_mention_otel` below) |

## Dev Agent Record

### Completion Notes List

- All ACs covered by Story 6.1's test suite + one additional grep
  test for the `ulog --help` surface.
- No new module code; this story is the "edge case acceptance" wrapper.

### File List

- `tests/test_otel_bind.py` — added `test_help_does_not_mention_otel`.
