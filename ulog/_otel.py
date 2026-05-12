"""OTel auto-bind without depending on the OpenTelemetry SDK (Story 6.1).

Two paths feed the trace context:

1. **Contextvar** `_OTEL_TRACE_CONTEXT` — set by user code (or an
   OTel integration adapter) via `set_trace_context(trace_id, span_id)`.
   Wins over the env path when both are set.
2. **W3C `traceparent` env var** — parsed lazily on each record. Used
   when ULog runs in an environment where an upstream tool exported
   the trace context but no Python-side OTel SDK is wired.

When neither is set, `current_trace_context()` returns `None` and the
SQL handler attaches NO fields (Gap G4 — silent no-op).

NFR-DEP-50: NO `import opentelemetry` anywhere. Stdlib only
(`contextvars`, `os`, `re`).
"""

from __future__ import annotations

import os
import re
from contextvars import ContextVar

# Public-by-convention name (underscore prefix because the read path
# is `current_trace_context()`, not direct contextvar access).
_OTEL_TRACE_CONTEXT: ContextVar[dict[str, str] | None] = ContextVar(
    "_ulog_otel_trace_context", default=None
)

# W3C Trace Context: `<version>-<trace-id>-<parent-id>-<flags>`
# Version is fixed `00` today; trace-id is 32 hex; parent-id is 16 hex;
# flags is 2 hex. See https://www.w3.org/TR/trace-context/
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def set_trace_context(trace_id: str, span_id: str) -> None:
    """Hand-bind a trace context (typically wrapping an OTel SDK call)."""
    _OTEL_TRACE_CONTEXT.set({"trace_id": trace_id, "span_id": span_id})


def clear_trace_context() -> None:
    """Reset the contextvar to None — useful at test boundaries."""
    _OTEL_TRACE_CONTEXT.set(None)


def current_trace_context() -> dict[str, str] | None:
    """Return the active trace context dict, or None when no source set.

    Resolution order:
    1. The contextvar (user-set; wins).
    2. The W3C `traceparent` env var (lowercase or uppercase — the
       spec specifies lowercase but tools differ).
    """
    ctx = _OTEL_TRACE_CONTEXT.get()
    if ctx is not None:
        return ctx
    # W3C spec is lowercase (`traceparent`); some tools export uppercase.
    tp = os.environ.get("traceparent") or os.environ.get("TRACEPARENT")  # noqa: SIM112
    if not tp:
        return None
    m = _TRACEPARENT_RE.match(tp.strip())
    if not m:
        return None
    return {"trace_id": m.group(1), "span_id": m.group(2)}
