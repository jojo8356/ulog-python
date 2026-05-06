"""ulog.testing.test_event — programmatic test-event API (PRD-v0.3 §5.2, Story 1.9).

Provides the ``test_event(name)`` context manager for recording test
lifecycle events from non-pytest runners (custom test loops, asyncio
drivers, benchmark harnesses, etc.). Emits the same record shape as
the pytest plugin's ``pytest_runtest_protocol`` hookwrapper does
(Story 1.2).

Usage:

    from ulog.testing import test_event

    with test_event("my_custom_test") as ev:
        log.info("step 1")  # propagates test_id via Story 1.4 bind
        ev.outcome("passed", duration_s=0.42)

If the user does NOT call ``ev.outcome(...)`` before the block exits:
- clean exit  → auto-emits ``outcome="passed"`` with measured duration
- exception   → auto-emits ``outcome="errored"`` + a separate traceback
                ERROR record, then re-raises (the manager does NOT swallow
                exceptions)

Production caveat: the ``except BaseException`` catch ensures
``KeyboardInterrupt`` and ``SystemExit`` also produce a traceback ERROR
record before re-raise. With ``sql_batch_size > 1`` those records may
not flush before the interpreter exits — production users running with
``test_event`` should configure ``ulog.setup(..., sql_batch_size=1)``
for synchronous flushing OR rely on the SQL handler's atexit hook.

Nesting: ``with test_event("outer"): with test_event("inner"): ...`` works
correctly. The inner block uses ``ulog.context(test_id=...)`` semantics
(via ContextVar token reset) so the outer ``test_id`` is restored on
inner exit. Records emitted between inner exit and outer exit carry the
outer ``test_id``; records emitted after outer exit carry no ``test_id``.
"""
from __future__ import annotations

import logging
import time
import traceback
from contextlib import contextmanager
from typing import Any, Iterator

# Lazy import — `ulog.testing` is part of `ulog`, so direct import at
# module top would create a partial-import edge if `ulog/__init__.py`
# itself reaches into this submodule. Keep `ulog` deferred to first use.
def _ulog() -> Any:
    import ulog
    return ulog


class _TestEventHandle:
    """Object exposed via ``with test_event(name) as ev``.

    Records the user's explicit outcome call (if any) so the
    context-manager exit can decide whether to auto-emit.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._outcome_emitted = False

    def outcome(
        self,
        outcome: str,
        duration_s: float,
        phase: str = "call",
    ) -> None:
        """Emit the body-verdict outcome record explicitly.

        Mirrors Story 1.2's ``_emit_outcome_records`` body shape:

        - ``level=ERROR if outcome in (failed, errored) else INFO``
        - ``msg='test {outcome}'``
        - ``extra={'outcome': outcome, 'duration_s': duration_s, 'phase': phase}``

        After this call, the context-manager exit will NOT auto-emit
        another outcome record. An explicit outcome ALWAYS wins, even if
        the block subsequently raises — the user's verdict is preserved
        and the traceback ERROR record is emitted separately.

        Subsequent calls to ``outcome()`` are silently ignored — the
        first explicit verdict wins (review patch P7).
        """
        if self._outcome_emitted:
            return  # idempotent — first call wins
        log = _ulog().get_logger("ulog.test")
        level = (
            logging.ERROR
            if outcome in ("failed", "errored")
            else logging.INFO
        )
        log.log(
            level,
            f"test {outcome}",
            extra={
                "outcome": outcome,
                "duration_s": duration_s,
                "phase": phase,
            },
        )
        self._outcome_emitted = True


@contextmanager
def test_event(name: str) -> Iterator[_TestEventHandle]:
    """Context manager for recording test lifecycle events programmatically.

    Emits ``test started`` on enter, scopes ``test_id=name`` to the block
    via ``ulog.context()`` (so app records inside inherit it AND nested
    ``test_event`` blocks restore the outer ``test_id`` on exit — review
    patch P6), and on exit:

    - if the user called ``ev.outcome(...)`` explicitly: nothing extra
      is emitted;
    - if the block raised AND no explicit outcome: emits ``test errored``
      outcome + a separate ERROR record with the traceback, then re-raises;
    - if the block raised AND the user called ``ev.outcome(...)``: the
      explicit outcome wins (no extra outcome record); the traceback ERROR
      is still emitted; the exception still propagates;
    - else (no exception, no explicit outcome): emits ``test passed``
      outcome with measured duration.
    """
    if not name:
        raise ValueError(
            "test_event(name) requires a non-empty test_id; got empty string"
        )

    ulog = _ulog()
    log = ulog.get_logger("ulog.test")
    ev = _TestEventHandle(name)
    # Use `ulog.context()` (ContextVar token-based) instead of
    # bind/unbind. Nested test_event blocks restore the outer test_id
    # correctly on inner exit (review patch P6).
    with ulog.context(test_id=name):
        log.info("test started")
        start = time.perf_counter()
        try:
            yield ev
        except BaseException as exc:
            # Compute duration FIRST, before traceback formatting (deep
            # stacks can take ms and would bias the measure).
            duration_s = time.perf_counter() - start

            # Auto-emit errored outcome ONLY if the user didn't call
            # `ev.outcome(...)` explicitly. Explicit outcome wins (AC4).
            if not ev._outcome_emitted:
                log.error(
                    "test errored",
                    extra={
                        "outcome": "errored",
                        "duration_s": duration_s,
                        "phase": "call",
                    },
                )

            # Always emit the traceback ERROR record on exception.
            # Use `format_exception(exc)` 1-arg form (Python 3.10+) so
            # `__cause__` / `__context__` chains are captured correctly
            # by `TracebackException.from_exception` (review patch P1).
            raw = traceback.format_exception(exc)
            tb_lines = [
                line for entry in raw
                for line in entry.rstrip("\n").splitlines()
            ]
            log.error(
                f"{type(exc).__name__}: {exc}",
                extra={
                    "exc": {
                        "type": type(exc).__name__,
                        "msg": str(exc),
                        "tb": tb_lines,
                    },
                },
            )
            raise
        else:
            duration_s = time.perf_counter() - start
            if not ev._outcome_emitted:
                log.info(
                    "test passed",
                    extra={
                        "outcome": "passed",
                        "duration_s": duration_s,
                        "phase": "call",
                    },
                )


# Tell pytest NOT to collect this function as a test. The name starts with
# `test_` (matching pytest's default `python_functions = "test_*"` pattern)
# so any test file that does `from ulog.testing import test_event` would
# otherwise see it collected as a top-level test in that file.
test_event.__test__ = False  # type: ignore[attr-defined]
