"""Fleet probes (PRD-v0.10) — synthetic monitoring on top of the v0.3
pytest plugin.

`@probe(target=URL, parents=[...])` decorates a pytest function so the
ulog record emitted at its completion carries:
  - context.target  : the URL/host being probed
  - context.parents : list of upstream targets this one depends on
  - context.latency_ms : measured duration of the probe body
  - context.fleet : "1" (marker for the sidebar filter)

Probes use the same pytest collection / runner as regular tests — no
new infrastructure. The fleet sidebar (separate from the Tests
sidebar) aggregates by target into a tree.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

import ulog


def probe(
    *,
    target: str,
    parents: list[str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: tag a pytest function as a fleet probe.

    The decorated function receives the original signature; on exit
    (success OR fail), an INFO record is emitted with the probe
    metadata + measured latency.
    """
    parents_list: list[str] = list(parents or [])

    def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            err: BaseException | None = None
            try:
                return fn(*args, **kwargs)
            except BaseException as e:
                err = e
                raise
            finally:
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                with ulog.context(
                    fleet="1",
                    target=target,
                    parents=parents_list,
                    latency_ms=latency_ms,
                    probe_status="fail" if err else "ok",
                ):
                    ulog.get_logger("ulog.fleet").info(
                        f"probe {target} {'fail' if err else 'ok'} ({latency_ms}ms)"
                    )

        # Mark the function so the optional `ulog fleet run` CLI can find it.
        _wrapped._ulog_fleet_target = target  # type: ignore[attr-defined]
        _wrapped._ulog_fleet_parents = parents_list  # type: ignore[attr-defined]
        return _wrapped

    return _decorator
