# Story 4.9: `replay_records` context manager in `ulog/testing/`

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-9-replay-records-context-manager-in-ulog-testing`
**Implements:** Gap G5 (stable API for `replay_to_pytest` generated tests).
**Built on:** Story 4.1 (`replay()` semantic), Story 4.2 (`_REPLAY_ACTIVE` contextvar + `is_replay` flag), v0.3 Story 1.9 (stub already publishes the importable name).
**Foundation for:** Story 4.3 (`replay_to_pytest` generator emits files that USE this context manager).

## Story

As a **generated regression test**,
I want **`from ulog.testing import replay_records` to import a context manager that replays a frozen list of records and tracks them for assertions**,
so that **the generated tests have a stable, simple API** that survives source-tree refactors (Gap G5 lock).

## Acceptance Criteria

1. **`replay_records(records: Sequence[Mapping[str, Any]]) -> Iterator[ReplaySession]`** as a context manager (via `@contextlib.contextmanager`).
2. **Inside the `with` body, `ulog.is_replaying()` returns True** (reuses `_REPLAY_ACTIVE` from Story 4.2).
3. **Each record in `records` is RE-EMITTED through the logging pipeline** (so configured handlers — SQL, JSONL, CSV, stream — see it). The re-emit uses the record's `level` + `logger` + `msg` + `context` (as `extra=...`). On the SQL handler, the re-emitted record lands with `is_replay=1` (Story 4.2 wiring).
4. **`session.matches(predicate)` returns True iff ANY of the input `records` satisfies the predicate.** The predicate receives a frozen view of each record exposing `r["…"]` AND `r.extras.get("…")` (alias for `r["context"]`).
5. **`session.captured` exposes a tuple of frozen views** for direct iteration / counting.
6. **Token-reset on exit, even on exception** — `_REPLAY_ACTIVE` always restores its prior value when the body exits (success or raise).
7. **The stub raise from v0.3** (`NotImplementedError(...)`) is replaced with the real implementation.
8. **Public symbol `ReplaySession`** is exported from `ulog.testing` alongside `replay_records`. `TestSession` stays as v0.3 stub (Story 4.9 doesn't require it).
9. **Tests** — `tests/test_replay_records.py` (NEW):
    - `test_replay_records_sets_is_replaying_inside_body`
    - `test_replay_records_resets_after_body`
    - `test_replay_records_resets_on_exception`
    - `test_replay_records_emits_each_record_via_logging_pipeline`
    - `test_emitted_records_land_with_is_replay_1_in_sql_handler`
    - `test_session_matches_returns_true_when_any_record_matches`
    - `test_session_matches_returns_false_when_none_match`
    - `test_session_matches_uses_extras_alias_for_context` (AC4 literal: `r.extras.get("...")`)
    - `test_session_captured_is_frozen_view`
    - `test_replay_records_with_empty_list_yields_session_with_no_captures`
    - `test_replay_records_stub_no_longer_raises` (regression on the v0.3 NotImplementedError)

## Tasks / Subtasks

- [ ] **Task 1 — Replace stub in `ulog/testing/__init__.py`**
  - [ ] 1.1 — Drop the `NotImplementedError`-raising stub.
  - [ ] 1.2 — Add `from ._replay_records import ReplaySession, replay_records` re-exports.
  - [ ] 1.3 — Extend `__all__` to include `ReplaySession`.
- [ ] **Task 2 — `ulog/testing/_replay_records.py` (NEW)**
  - [ ] 2.1 — `CapturedRecord` dataclass (frozen): wraps a `MappingProxyType`, exposes `__getitem__` + `.get()` + `.extras` property.
  - [ ] 2.2 — `ReplaySession` dataclass: `_captured: list[CapturedRecord]`, `.captured` property returning a tuple, `.matches(predicate) -> bool`.
  - [ ] 2.3 — `@contextmanager def replay_records(records)` — sets `_REPLAY_ACTIVE` via `Token`, re-emits each record through `logging.getLogger(r.get("logger", "ulog.testing")).log(level, msg, extra=...)`, appends to `session._captured`, yields session, resets in `finally`.
  - [ ] 2.4 — Level normalisation: `r.get("level", "INFO")` → `getattr(logging, level_name, logging.INFO)`.
- [ ] **Task 3 — Tests in `tests/test_replay_records.py` (NEW)**
  - [ ] 3.1 — 11 tests per AC9.
- [ ] **Task 4 — Validation**
  - [ ] 4.1 — pytest tests/ — full suite green.
  - [ ] 4.2 — mypy / ruff / deptry clean.

## Dev Notes

### Snippet — `ulog/testing/_replay_records.py`

```python
"""Context manager + ReplaySession (Story 4.9).

`replay_records(records)` re-emits a frozen list through the logging
pipeline with `_REPLAY_ACTIVE=True` so all records pick up
`is_replay=1` at insert time (Story 4.2). The captured records are
exposed as `session.matches(predicate)` / `session.captured` for
assertions.

This is the load-bearing API for Story 4.3's generated tests.
Importable name `replay_records` is locked since v0.3 (Story 1.9
stub).
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
    """Frozen-view wrapper exposing both dict-access and `.extras` alias."""

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
        return any(predicate(r) for r in self._captured)


@contextmanager
def replay_records(records: Sequence[Mapping[str, Any]]) -> Iterator[ReplaySession]:
    """Replay a frozen list of records through the logging pipeline.

    See Gap G5 + FR100 for the contract. Inside the body, configured
    handlers (SQL / JSONL / CSV / stream) receive each record as if
    re-emitted live; `_REPLAY_ACTIVE` is set so the SQL handler
    stamps `is_replay=1` on chain inserts (Story 4.2 / FR99).
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
```

### Architecture compliance

- **Gap G5 lock:** `replay_records(records: Sequence[Mapping]) -> ReplaySession` — signature stable across v0.3/v0.5.
- **Decision C3 (frozen views):** captured records are wrapped in `MappingProxyType` so test code can't mutate them.
- **Stdlib only:** `logging`, `contextlib.contextmanager`, `dataclasses`, `types.MappingProxyType`, `collections.abc`.

### Test patterns

```python
def test_emitted_records_land_with_is_replay_1_in_sql_handler(tmp_path):
    """The SQLHandler must see is_replay=1 on every re-emitted record."""
    from sqlalchemy import create_engine, text
    import ulog
    from ulog.testing import replay_records

    db = tmp_path / "rec.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)

    records = [
        {"level": "ERROR", "logger": "svc", "msg": "boom", "context": {"k": 1}},
        {"level": "INFO", "logger": "svc", "msg": "ok", "context": {}},
    ]
    with replay_records(records) as session:
        assert ulog.is_replaying()
        assert session.captured  # both rows captured

    # Flush + assert.
    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT msg, is_replay FROM logs ORDER BY id")).all()
    engine.dispose()
    assert rows == [("boom", 1), ("ok", 1)]
```

### References

- [Source: epics.md, lines 1491-1506] — Story 4.9 AC
- [Source: architecture.md Gap G5] — stable signature lock
- [Source: ulog/testing/__init__.py:replay_records (v0.3 stub)] — replaced
- [Source: ulog/replay.py:_REPLAY_ACTIVE] — contextvar reused
- [Python `contextlib.contextmanager`] — chosen primitive

## Dev Agent Record

### Completion Notes List

- New module `ulog/testing/_replay_records.py` with:
  - `CapturedRecord` frozen-dataclass wrapping a `MappingProxyType`,
    exposing `r["key"]`, `r.get(...)`, and the `.extras` alias for
    `r["context"]` (AC4 literal `r.extras.get("...")` works as
    documented).
  - `ReplaySession` dataclass with `_captured: list`, `.captured`
    property returning a tuple, and `.matches(predicate)`.
  - `@contextmanager def replay_records(records)` — sets
    `_REPLAY_ACTIVE` via Token, re-emits each record via the
    standard `logging.getLogger(...).log(...)` API with `extra=...`,
    appends a `CapturedRecord` to the session, yields the session,
    resets in `finally`.
- v0.3 stub in `ulog/testing/__init__.py:replay_records` REPLACED
  with a re-export from `_replay_records`. `TestSession` stays as
  v0.3 stub (Story 4.9 doesn't require it).
- 12 / 12 tests in `tests/test_replay_records.py` green:
  contextvar set inside body, reset after body, reset on exception,
  emission via logging pipeline (caplog), SQL handler stamps
  is_replay=1 on chain inserts, `.matches()` true/false paths,
  `.extras` alias works, frozen view (mutation raises), empty list
  edge case, stub regression (no longer raises NotImplementedError),
  missing-keys defaults.
- 181 affected-area tests green across the entire replay + chain
  + handlers + cli + qa stack.
- mypy --strict / ruff check / ruff format / deptry all clean.

### File List

- `ulog/testing/_replay_records.py` (NEW) — `CapturedRecord`,
  `ReplaySession`, `replay_records` context manager.
- `ulog/testing/__init__.py` — stub replaced with re-exports;
  `CapturedRecord` + `ReplaySession` added to `__all__`.
- `tests/test_replay_records.py` (NEW) — 12 tests.
