"""Span-based execution timeline (PRD-v0.7).

`with ulog.span("setup_db"):` measures the elapsed wall time of the
block and emits an INFO record with:

    context.span_id      : random 8-hex per span
    context.parent_span_id : the enclosing span's id (None at top level)
    context.span_name    : the user-given name
    context.span_ms      : measured duration in milliseconds

Spans nest via a contextvar so async tasks / threads see consistent
parents. The viewer reconstructs the tree from `parent_span_id` to
render a waterfall view (UI ship: future PRD).
"""

from __future__ import annotations

import contextlib
import contextvars
import secrets
import time
from collections.abc import Iterator

import ulog

_CURRENT_SPAN_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_ulog_current_span_id", default=None
)


def current_span_id() -> str | None:
    """Return the currently-active span id (or None at the top level)."""
    return _CURRENT_SPAN_ID.get()


@contextlib.contextmanager
def span(name: str) -> Iterator[str]:
    """Context-manager span. Yields the span_id of the new span.

    Example:
        with ulog.span("fixture.setup_repo"):
            git_init()
            with ulog.span("git_commit"):
                run("git commit -m x")
    """
    sid = secrets.token_hex(4)
    parent = _CURRENT_SPAN_ID.get()
    token = _CURRENT_SPAN_ID.set(sid)
    t0 = time.perf_counter()
    err: BaseException | None = None
    try:
        yield sid
    except BaseException as e:
        err = e
        raise
    finally:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
        _CURRENT_SPAN_ID.reset(token)
        with ulog.context(
            span_id=sid,
            parent_span_id=parent,
            span_name=name,
            span_ms=elapsed_ms,
            span_status="fail" if err else "ok",
        ):
            ulog.get_logger("ulog.span").info(f"span {name} {elapsed_ms}ms")
