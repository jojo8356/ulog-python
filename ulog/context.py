"""Context-variable binding for structured logging (FR4, FR5).

Bound key/value pairs propagate through function calls in the same
thread/async-task via `contextvars.ContextVar`. The JSON formatter
(and verbose, optionally) reads the current bound dict and merges it
into every log record emitted from within the context.

Examples
--------

    import ulog
    ulog.setup(format='json')
    log = ulog.get_logger(__name__)

    ulog.bind(request_id="abc-123")
    log.info("step 1")    # JSON includes request_id="abc-123"
    log.info("step 2")    # same

    # Block-scoped binding via context manager:
    with ulog.context(rom_sha="deadbeef"):
        log.info("rendering")  # rom_sha and request_id both present

    log.info("step 3")    # request_id only; rom_sha unbound after the block

    ulog.clear()          # unbinds everything in this context
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from typing import Any

# Single ContextVar holding a snapshot dict. Each `bind` replaces it
# with a NEW dict (immutable-style) so concurrent tasks see consistent
# state — `contextvars.copy_context().run(...)` semantics are preserved.
# No `default=`: a shared mutable default on a ContextVar would be a
# footgun across contexts. We pass `{}` at each `.get()` site instead,
# so a fresh empty dict is materialized only when needed.
_bound: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("ulog_bound")


def bind(**fields: Any) -> None:
    """Add or update key/value pairs on the current context's bound dict.

    Existing keys are overwritten by the new values; other keys are
    preserved. Mutation is via a fresh dict copy, so concurrent
    tasks don't see partial updates.
    """
    if not fields:
        return
    current = _bound.get({})
    merged = {**current, **fields}
    _bound.set(merged)


def unbind(*keys: str) -> None:
    """Remove the given keys from the bound dict, if present."""
    if not keys:
        return
    current = _bound.get({})
    remaining = {k: v for k, v in current.items() if k not in keys}
    _bound.set(remaining)


def clear() -> None:
    """Drop every bound key/value in the current context."""
    _bound.set({})


def get_bound() -> dict[str, Any]:
    """Return a copy of the currently bound fields. Read-only."""
    return dict(_bound.get({}))


@contextlib.contextmanager
def context(**fields: Any) -> Iterator[None]:
    """Block-scoped `bind`. Restores the previous bound dict on exit
    (including exception paths)."""
    token = _bound.set({**_bound.get({}), **fields})
    try:
        yield
    finally:
        _bound.reset(token)
