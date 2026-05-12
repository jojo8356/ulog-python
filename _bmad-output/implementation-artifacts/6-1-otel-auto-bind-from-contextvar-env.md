# Story 6.1: OTel auto-bind from contextvar / env

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-1-otel-auto-bind-from-contextvar-env`
**Implements:** FR109, NFR-DEP-50, Gap G4.
**Foundation for:** Story 6.2 (`ulog trace <id>` CLI), Story 6.10 (no-OTel edge).

## Story

As a **platform engineer running services with OTel**,
I want **ulog to auto-attach `trace_id` and `span_id` to every record when an OTel context is present**,
so that I get **cross-service correlation** for free.

## Acceptance Criteria

1. When the contextvar `ulog._otel._OTEL_TRACE_CONTEXT` is set with `{"trace_id": "...", "span_id": "..."}` (a dict), every emit attaches both fields into the record's `context`.
2. When `_OTEL_TRACE_CONTEXT` is unset BUT the `traceparent` env var is set with a W3C-format string (`00-<32hex>-<16hex>-<2hex>`), the `trace_id` is parsed from it and attached.
3. When neither is set, no fields are attached, no warning printed (silent no-op).
4. NO `import opentelemetry` anywhere in `ulog/` — stdlib `contextvars` + `os.environ` only (NFR-DEP-50).
5. Helper `ulog._otel.set_trace_context(trace_id, span_id)` exposed as the documented hand-bind API.
6. `_record_to_row` in `SQLHandler` merges the trace fields into the record's `context` dict (alongside existing `bind()` keys).
7. Tests in `tests/test_otel_bind.py`:
   - `test_no_otel_context_no_fields_attached`
   - `test_contextvar_set_attaches_trace_id_and_span_id`
   - `test_traceparent_env_parsed_when_contextvar_unset`
   - `test_contextvar_wins_over_traceparent`
   - `test_invalid_traceparent_silent_no_op`
   - `test_no_opentelemetry_import_anywhere` (grep regression).

## Dev Notes

`traceparent` format (W3C Trace Context):
- `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- Components: version `-` trace-id (32 hex) `-` parent-id (16 hex) `-` flags (2 hex).
- We extract only `trace_id` from env path; `span_id` available only via contextvar.

### Snippet

```python
# ulog/_otel.py
from __future__ import annotations
import os
import re
from contextvars import ContextVar
from typing import Any

_OTEL_TRACE_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar(
    "_ulog_otel_trace_context", default=None
)

_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def set_trace_context(trace_id: str, span_id: str) -> None:
    _OTEL_TRACE_CONTEXT.set({"trace_id": trace_id, "span_id": span_id})


def current_trace_context() -> dict[str, str] | None:
    ctx = _OTEL_TRACE_CONTEXT.get()
    if ctx is not None:
        return ctx
    tp = os.environ.get("traceparent") or os.environ.get("TRACEPARENT")
    if not tp:
        return None
    m = _TRACEPARENT_RE.match(tp.strip())
    if not m:
        return None
    return {"trace_id": m.group(1), "span_id": m.group(2)}
```

### Files

- `ulog/_otel.py` (NEW) ~ 60 LOC.
- `ulog/handlers/sql.py` — `_record_to_row` merges `current_trace_context()` into `bound`.
- `tests/test_otel_bind.py` (NEW) ~ 100 LOC.

## Dev Agent Record

### Completion Notes List

- `ulog/_otel.py` (NEW, ~60 LOC). Two-source `current_trace_context()`:
  contextvar wins, W3C `traceparent` env (lowercase OR uppercase)
  fallback. Stdlib only — NO `import opentelemetry`.
- `SQLHandler._record_to_row` merges trace_id/span_id into `bound`
  via `setdefault` (so user `bind(trace_id='...')` overrides
  auto-bind — verified by test_user_bind_overrides_otel_trace_id).
- 11 / 11 tests in `tests/test_otel_bind.py` green incl. the NFR-DEP-50
  grep regression (`^\s*(import|from) opentelemetry` matches only
  actual code lines, not docstring mentions).
- 37 affected-area tests green (test_otel_bind + test_handlers).
- mypy --strict / ruff check / ruff format clean.

### File List

- `ulog/_otel.py` (NEW)
- `ulog/handlers/sql.py` — `_record_to_row` merges OTel context.
- `tests/test_otel_bind.py` (NEW) — 11 tests + grep regression.
