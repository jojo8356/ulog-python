"""Context manager + ReplaySession (Story 4.9).

`replay_records(records)` re-emits a frozen list through the logging
pipeline with `_REPLAY_ACTIVE=True` so all records pick up
`is_replay=1` at insert time (Story 4.2). The captured records are
exposed as `session.matches(predicate)` / `session.captured` for
assertions.

This is the load-bearing API for Story 4.3's generated tests.
Importable name `replay_records` is locked since v0.3 (Story 1.9
stub) — Gap G5.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class CapturedRecord:
    """Frozen-view wrapper exposing both dict-access and `.extras` alias.

    `r["msg"]` and `r.get("level")` work as dict-like access; the
    `.extras` property aliases `r["context"]` for the generated-test
    idiom `assert not session.matches(lambda r: r.extras.get("db_timeout"))`.
    """

    raw: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    @property
    def extras(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self.raw.get("context") or {}))


@dataclass
class ReplaySession:
    """Records captured during a `replay_records(...)` body."""

    _captured: list[CapturedRecord] = field(default_factory=list)

    @property
    def captured(self) -> tuple[CapturedRecord, ...]:
        return tuple(self._captured)

    def matches(self, predicate: Callable[[CapturedRecord], bool]) -> bool:
        """True iff any captured record satisfies the predicate."""
        return any(predicate(r) for r in self._captured)


@contextmanager
def replay_records(records: Sequence[Mapping[str, Any]]) -> Iterator[ReplaySession]:
    """Replay a frozen list of records through the logging pipeline.

    See Gap G5 + FR100 for the contract. Inside the body, configured
    handlers (SQL / JSONL / CSV / stream) receive each record as if
    re-emitted live; `_REPLAY_ACTIVE` is set so the SQL handler
    stamps `is_replay=1` on chain inserts (Story 4.2 / FR99).

    Args:
        records: frozen list of record dicts (e.g., from
            `replay_to_pytest`-generated `INCIDENT_RECORDS = [...]`).

    Yields:
        ReplaySession with `.captured` (tuple of `CapturedRecord`) and
        `.matches(predicate) -> bool` for assertions.
    """
    from ..replay import _REPLAY_ACTIVE

    session = ReplaySession()
    token = _REPLAY_ACTIVE.set(True)
    try:
        for r in records:
            level_name = str(r.get("level") or "INFO").upper()
            level_int = getattr(logging, level_name, logging.INFO)
            logger = logging.getLogger(r.get("logger") or "ulog.testing")
            ctx = r.get("context") or {}
            extra = dict(ctx) if isinstance(ctx, Mapping) else {}
            logger.log(level_int, r.get("msg") or "", extra=extra)
            session._captured.append(CapturedRecord(MappingProxyType(dict(r))))
        yield session
    finally:
        _REPLAY_ACTIVE.reset(token)
