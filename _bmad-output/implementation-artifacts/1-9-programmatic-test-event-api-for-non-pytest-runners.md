# Story 1.9: Programmatic `test_event()` API for non-pytest runners

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**Epic:** 1 — v0.3 Test integration
**Story key:** `1-9-programmatic-test-event-api-for-non-pytest-runners`
**Implements:** PRD-v0.3 §5.2 (programmatic API) + Gap G5 stable-signature anchor (architecture.md)
**Source:** `docs/prds/PRD-v0.3-test-integration.md` §5.2, `_bmad-output/planning-artifacts/architecture.md` Decision C2 + step-06 sub-package layout, `_bmad-output/planning-artifacts/epics.md` Story 1.9
**Built on:** Story 1.2 (record shape: `test started` + outcome + optional traceback ERROR), Story 1.3 (`_make_test_id` contract), Story 1.4 (bound-context propagation — `test_event` must wire the same `ulog.bind(test_id=...)` mechanism for app-record propagation)
**Foundation for:** Story 4.3 (`replay_to_pytest` synthesizes calls to `replay_records`, which Story 1.9 declares as a stable-import name; full implementation is v0.5)

---

## Story

As a **developer running tests via a custom runner (not pytest)** — e.g. a CI integration test, a hand-rolled test loop, an asyncio test driver, or a benchmark harness,
I want **a programmatic `test_event(name)` context manager exported from `ulog.testing`**,
so that **I can record test lifecycle events from any test framework — same record shape as the pytest plugin produces — without depending on pytest hooks**.

## Acceptance Criteria

### AC1 — `with test_event(name) as ev: ev.outcome(...)` emits the same record shape as the pytest plugin (PRD §5.2)

**Given** `from ulog.testing import test_event` and a configured ulog setup with the SQL handler
**When** the user writes:

```python
with test_event("custom_test_42") as ev:
    ulog.get_logger("myapp").info("step 1")  # propagates test_id via bind
    ev.outcome("passed", duration_s=0.42)
```

**Then** the SQL log table receives the SAME record sequence as a pytest test would produce (Story 1.2 contract), specifically:
  1. `logger='ulog.test'`, `level='INFO'`, `msg='test started'`, `context.test_id='custom_test_42'`
  2. `logger='myapp'`, `level='INFO'`, `msg='step 1'`, `context.test_id='custom_test_42'` (Story 1.4 propagation)
  3. `logger='ulog.test'`, `level='INFO'`, `msg='test passed'`, `context={"test_id": "custom_test_42", "outcome": "passed", "duration_s": 0.42, "phase": "call"}`

### AC2 — Auto-emit on context exit when user did NOT call `ev.outcome(...)` and no exception was raised

**Given** the user uses `test_event` without calling `ev.outcome(...)`:

```python
with test_event("happy_path") as ev:
    log.info("did some work")
    # no ev.outcome(...) call
```

**When** the context exits cleanly (no exception)
**Then** the API auto-emits an outcome record: `msg='test passed'`, `context.outcome='passed'`, `context.duration_s=<measured>` (the elapsed time from `__enter__` to `__exit__`), `context.phase='call'`.

### AC3 — Auto-emit `outcome='errored'` with exception info on exception

**Given** the block inside `test_event` raises:

```python
with test_event("oh_no") as ev:
    raise ValueError("boom")
```

**When** the context exits with an exception
**Then** the API:
  1. Emits an outcome record: `level='ERROR'`, `msg='test errored'`, `context.outcome='errored'`, `context.duration_s=<measured>`, `context.phase='call'`
  2. Emits a separate ERROR record with the traceback: `level='ERROR'`, `msg='ValueError: boom'`, `context.exc={"type": "ValueError", "msg": "boom", "tb": [...]}`

The exception is then re-raised (the context manager does NOT swallow it).

### AC4 — Explicit `ev.outcome(...)` call wins over auto-emit (no double-emit)

**Given** the user calls `ev.outcome("failed", duration_s=0.1)` inside the block AND the block then exits cleanly
**When** the context manager's `__exit__` runs
**Then** EXACTLY ONE outcome record is emitted (the one from the explicit `ev.outcome` call). The auto-emit path short-circuits because `ev._outcome_emitted` was set to True by the explicit call.

### AC5 — `ev.outcome(...)` accepts the same outcome strings as the pytest plugin

**Given** the user calls `ev.outcome("passed" | "failed" | "skipped" | "errored", duration_s=<float>)`
**When** the call is made
**Then** the outcome record carries the exact `outcome` string passed in (no normalization). The level is `ERROR` for `failed`/`errored` and `INFO` for `passed`/`skipped` — same mapping Story 1.2 uses.

### AC6 — `test_id` propagates to app-code records emitted DURING the context (Story 1.4 contract)

**Given** an active `with test_event("X") as ev:` block
**When** any application code inside emits via stdlib `logging` (e.g. `logging.getLogger("myapp").info(...)`)
**Then** the resulting record's `context` carries `test_id="X"` — exactly as Story 1.4 verified for pytest-driven tests. Same `ulog.bind(test_id=...)` / `ulog.unbind` mechanism.

After the context exits, subsequent `myapp` records do NOT carry `test_id` (unbind happens on `__exit__`).

### AC7 — Stable-signature anchor: `test_event`, `replay_records`, `TestSession` all importable (Gap G5)

**Given** `ulog[testing]` is installed
**When** the user writes:

```python
from ulog.testing import test_event, replay_records, TestSession
```

**Then** all three names resolve without ImportError. For v0.3:
  - `test_event` — fully implemented (this story)
  - `replay_records` — STUB (raises `NotImplementedError("replay_records is implemented in v0.5 — Story 4.9")` if called, but importable as a callable name; full impl is Story 4.9 / v0.5)
  - `TestSession` — STUB dataclass with the documented v0.5 fields (placeholder; `__post_init__` allowed to raise `NotImplementedError` if the user actually instantiates and uses it). Importable as a class name.

This locks the import surface for v0.3 publication so v0.5 can extend without breaking client code.

### AC8 — `__all__` updated in `ulog/testing/__init__.py`

**Given** `from ulog.testing import *`
**When** evaluated
**Then** `test_event`, `replay_records`, `TestSession` are imported. The module's `__all__` list is updated from `[]` (current placeholder) to `["test_event", "replay_records", "TestSession"]`.

### AC9 — Frozen-invariant + regression-gate compliance

**Given** Story 1.9's changes
**When** the standard regression checks run
**Then**:
  - `dependencies = []` in `pyproject.toml` is unchanged.
  - `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/` ALL UNCHANGED.
  - `ulog/testing/pytest_plugin.py` UNCHANGED — Story 1.9 lives in a NEW module `ulog/testing/test_event.py` (or directly in `ulog/testing/__init__.py`; implementer's choice but the file boundary matters for testability).
  - All 152 existing tests still pass.

---

## Tasks / Subtasks

- [ ] **Task 1** — Implement `test_event` context manager (AC1, AC2, AC3, AC4, AC5, AC6)
  - [ ] 1.1 Create `ulog/testing/test_event.py` (NEW file) with the following structure:

    ```python
    """ulog.testing.test_event — programmatic test-event API (PRD-v0.3 §5.2).

    Provides the `test_event(name)` context manager for recording test
    lifecycle events from non-pytest runners (custom test loops, asyncio
    drivers, etc.). Emits the same record shape as the pytest plugin's
    `pytest_runtest_protocol` hookwrapper does (Story 1.2).
    """
    from __future__ import annotations

    import logging
    import time
    import traceback
    from contextlib import contextmanager
    from typing import Iterator


    class _TestEventHandle:
        """Object exposed via `with test_event(name) as ev`. Records the user's
        explicit outcome call (if any) so the context-manager exit can
        decide whether to auto-emit."""

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

            Mirrors Story 1.2's `_emit_outcome_records` body shape:
            - `level=ERROR if outcome in (failed, errored) else INFO`
            - `msg='test {outcome}'`
            - `extra={'outcome': outcome, 'duration_s': duration_s, 'phase': phase}`

            After this call, the context-manager exit will NOT auto-emit
            another outcome record (AC4).
            """
            import ulog
            log = ulog.get_logger("ulog.test")
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

        Emits ``test started`` on enter, binds ``test_id=name`` for the
        duration so app records inside inherit it (Story 1.4 propagation),
        and on exit:
          - if the user called ``ev.outcome(...)`` explicitly: nothing extra
            is emitted (just unbinds);
          - if the block raised: emits ``test errored`` outcome + a separate
            ERROR record with the traceback, then re-raises;
          - else (no explicit outcome, no exception): emits ``test passed``
            outcome with measured duration.
        """
        import ulog
        log = ulog.get_logger("ulog.test")
        ev = _TestEventHandle(name)
        ulog.bind(test_id=name)
        log.info("test started")
        start = time.perf_counter()
        try:
            yield ev
        except BaseException as exc:
            duration_s = time.perf_counter() - start
            # Auto-emit errored outcome (skip if user already explicitly
            # emitted one — though that's unusual when the block raises).
            if not ev._outcome_emitted:
                log.error(
                    "test errored",
                    extra={
                        "outcome": "errored",
                        "duration_s": duration_s,
                        "phase": "call",
                    },
                )
            # Always emit the traceback ERROR record on exception (matches
            # Story 1.2's separate-record contract for failures).
            tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
            log.error(
                f"{type(exc).__name__}: {exc}",
                extra={
                    "exc": {
                        "type": type(exc).__name__,
                        "msg": str(exc),
                        "tb": [line.rstrip("\n") for line in tb_lines],
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
        finally:
            ulog.unbind("test_id")
    ```

  - [ ] 1.2 The implementation uses `time.perf_counter()` for duration (consistent with `pytest`'s `report.duration` semantics — wall-clock seconds with monotonic source).

  - [ ] 1.3 The bind/unbind ordering matches Story 1.2's pattern: bind BEFORE `log.info("test started")` so the started record carries `test_id`; unbind AFTER all outcome emits in the `finally` so outcome records also carry `test_id` (AC6).

- [ ] **Task 2** — Add `replay_records` and `TestSession` stable-signature stubs (AC7)
  - [ ] 2.1 In `ulog/testing/__init__.py`, replace the current empty `__all__: list[str] = []` with:

    ```python
    """ulog.testing — pytest plugin and programmatic test-event APIs.

    Sub-package home for v0.3 test integration and v0.5 replay tooling:
    - ``pytest_plugin`` module — auto-discovered via ``[project.entry-points.pytest11]``.
    - ``test_event`` (Story 1.9) — programmatic API for non-pytest runners.
    - ``replay_records`` (Story 4.9 / v0.5) — STUB in v0.3; importable name only.
    - ``TestSession`` (v0.5) — STUB dataclass; importable name only.

    The sub-package is loaded only when the ``[testing]`` extra is installed.
    """
    from __future__ import annotations

    from dataclasses import dataclass, field
    from typing import Any, Iterator, Mapping, Sequence

    from .test_event import test_event

    __all__ = ["test_event", "replay_records", "TestSession"]


    def replay_records(
        records: "Sequence[Mapping[str, Any]]",
    ) -> "Iterator[Any]":
        """STUB — full implementation in v0.5 (Story 4.9).

        The signature is locked here per architecture.md Gap G5: code that
        will be generated by ``replay_to_pytest()`` (v0.5) imports
        ``replay_records`` from this module. v0.3 publishes the importable
        name; calling it raises NotImplementedError.
        """
        raise NotImplementedError(
            "replay_records is implemented in v0.5 (Story 4.9). "
            "v0.3 publishes the importable name to lock the API surface "
            "per architecture.md Gap G5."
        )


    @dataclass
    class TestSession:
        """STUB dataclass — full implementation in v0.5.

        The shape is locked here per architecture.md to allow v0.3 client
        code to ``from ulog.testing import TestSession`` without
        ImportError. Field defaults are provisional and may change in v0.5.
        """
        name: str = ""
        records: list[Any] = field(default_factory=list)

        def __post_init__(self) -> None:
            # Allow construction (some frameworks may build empty sessions
            # for type-checking purposes); flag as work-in-progress.
            pass
    ```

  - [ ] 2.2 The `replay_records` stub must raise `NotImplementedError` (not `RuntimeError` or generic `Exception`) — that's the documented Python idiom for "implement in subclass / future version".

  - [ ] 2.3 `TestSession` is a `@dataclass` with placeholder fields. v0.5 (Story 4.9) will extend it; v0.3 just locks the import surface.

- [ ] **Task 3** — Tests for `test_event` (AC1-AC6)
  - [ ] 3.1 Add a new test file `tests/test_test_event.py`:

    ```python
    """Tests for ulog.testing.test_event (Story 1.9, FR PRD-v0.3 §5.2)."""
    from __future__ import annotations

    import json
    import logging
    import sqlite3
    from pathlib import Path

    import pytest

    import ulog
    from ulog.testing import test_event


    @pytest.fixture(autouse=True)
    def _isolate():
        yield
        for h in list(logging.getLogger().handlers):
            if getattr(h, "_ulog_managed", False):
                try:
                    h.close()
                except Exception:
                    pass
                logging.getLogger().removeHandler(h)
        ulog.clear()


    @pytest.fixture
    def configured_db(tmp_path) -> Path:
        """Configure ulog with SQL handler and return the DB path."""
        db = tmp_path / "tev.sqlite"
        ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
        return db


    def _read_records(db: Path) -> list[dict]:
        conn = sqlite3.connect(str(db))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM logs ORDER BY id ASC")
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()
    ```

  - [ ] 3.2 Add `test_test_event_explicit_outcome_emits_three_records` (AC1):
    ```python
    def test_test_event_explicit_outcome_emits_three_records(configured_db):
        log = ulog.get_logger("myapp")
        with test_event("custom_test_42") as ev:
            log.info("step 1")
            ev.outcome("passed", duration_s=0.42)
        for h in logging.getLogger().handlers:
            h.flush()

        records = _read_records(configured_db)
        assert len(records) == 3, [r["msg"] for r in records]
        # Order: started, app log, outcome
        assert records[0]["msg"] == "test started"
        assert records[0]["logger"] == "ulog.test"
        assert records[1]["msg"] == "step 1"
        assert records[1]["logger"] == "myapp"
        assert records[2]["msg"] == "test passed"
        assert records[2]["logger"] == "ulog.test"

        # All carry the same test_id via Story 1.4 propagation
        for r in records:
            ctx = json.loads(r["context"])
            assert ctx["test_id"] == "custom_test_42", r

        # Outcome record's specific fields
        ctx_outcome = json.loads(records[2]["context"])
        assert ctx_outcome["outcome"] == "passed"
        assert ctx_outcome["duration_s"] == 0.42
        assert ctx_outcome["phase"] == "call"
    ```

  - [ ] 3.3 Add `test_test_event_no_outcome_no_exception_auto_passed` (AC2):
    Block exits without `ev.outcome` and without exception → 2 records emitted (started + passed). Outcome record's `duration_s > 0` (not 0.0; the `time.perf_counter()` measure should produce a non-zero positive float for any block).

  - [ ] 3.4 Add `test_test_event_exception_emits_errored_and_raises` (AC3):
    Block raises `ValueError("boom")` → 3 records (started + errored outcome + traceback ERROR) + the exception PROPAGATES out of the `with` block. Use `pytest.raises(ValueError)` to verify the re-raise.

    Verify the traceback record's `context.exc.type == "ValueError"` and `context.exc.msg == "boom"`.

  - [ ] 3.5 Add `test_test_event_explicit_outcome_short_circuits_auto_emit` (AC4):
    User calls `ev.outcome("failed", duration_s=0.1)` then exits cleanly (no exception). Verify EXACTLY ONE outcome record (the explicit `failed`) — the auto-emit path doesn't fire.

  - [ ] 3.6 Add `test_test_event_supports_all_four_outcome_strings` (AC5):
    Run 4 separate `with test_event(...)` blocks, each calling `ev.outcome("passed" | "failed" | "skipped" | "errored", duration_s=0.1)`. Read all records, assert each outcome record has the exact string passed in (no normalization).

  - [ ] 3.7 Add `test_test_event_propagates_test_id_to_app_records` (AC6):
    During the context, emit `logging.getLogger("myapp").info("inside")`. After context exit, emit `logging.getLogger("myapp").info("outside")`. Verify the inside record has `context.test_id="X"` and the outside record does NOT.

  - [ ] 3.8 Add `test_test_event_outcome_record_level_matches_outcome` (AC5 corollary):
    Verify `ev.outcome("failed", ...)` produces a record at `level='ERROR'`; `ev.outcome("passed", ...)` at `level='INFO'`. Same level mapping as Story 1.2.

- [ ] **Task 4** — Tests for stable-signature stubs (AC7, AC8)
  - [ ] 4.1 Add `test_replay_records_importable` (AC7):
    `from ulog.testing import replay_records` succeeds. `replay_records` is callable. Calling it with any args raises `NotImplementedError` matching the message `"replay_records is implemented in v0.5"`.

  - [ ] 4.2 Add `test_test_session_importable` (AC7):
    `from ulog.testing import TestSession` succeeds. `TestSession` is a class. `TestSession(name="x")` constructs an instance with `name == "x"` and `records == []`.

  - [ ] 4.3 Add `test_testing_module_all_lists_three_exports` (AC8):
    `import ulog.testing as t; assert sorted(t.__all__) == ["TestSession", "replay_records", "test_event"]`.

- [ ] **Task 5** — Verify and ship
  - [ ] 5.1 Run `python3 -m pytest tests/ -v`. Full suite stays green. `tests/test_test_event.py` is **NEW** with 11 tests (8 from Tasks 3.2-3.8 + 3 from 4.1-4.3). Full project suite: 152 + 11 = **163 tests**.
  - [ ] 5.2 `mypy ulog/testing/ --follow-imports=silent` — clean. New helpers fully typed; no `# type: ignore` needed.
  - [ ] 5.3 `grep '^dependencies' pyproject.toml | grep -q '\[\]'` exits 0.
  - [ ] 5.4 `git diff --stat HEAD --` reports ONLY `ulog/testing/__init__.py`, `ulog/testing/test_event.py` (NEW), and `tests/test_test_event.py` (NEW).
  - [ ] 5.5 Verify `from ulog.testing import test_event, replay_records, TestSession` succeeds in a Python REPL with `[testing]` extra installed.

---

## Dev Notes

### Why `test_event` is a `@contextmanager` decorator + handle class hybrid

A pure `@contextmanager` generator function can't expose a method like `ev.outcome(...)` without yielding a separate object. The pattern:

```python
@contextmanager
def test_event(name):
    ev = _TestEventHandle(name)
    # setup ...
    try:
        yield ev  # user gets `ev` to call `ev.outcome(...)`
    finally:
        # teardown ...
```

is the standard Python idiom for "context manager that exposes a state object". `_TestEventHandle` is a private class (underscore prefix); the public surface is just `test_event` (the function).

### Bind/unbind ordering — why it matches Story 1.2 exactly

Story 1.2's pytest hookwrapper:
1. `ulog.bind(test_id=item.nodeid)` BEFORE `log.info("test started")`
2. yield (test runs; app records inherit test_id)
3. `_emit_outcome_records(item, log)` (outcome + traceback)
4. `ulog.unbind("test_id")` LAST

Story 1.9's `test_event` mirrors this exactly via the `try / except / else / finally` shape. The `finally` runs `ulog.unbind` AFTER all outcome emits (whether from the `except` branch or the `else` branch), so outcome records still carry `test_id` (matches Story 1.2's AC6).

### Traceback formatting — why `traceback.format_exception` and not pytest's `report.longrepr`

Story 1.2 uses `report.longrepr` (a pytest-specific object). Story 1.9 has no pytest dependency — it must use the stdlib. `traceback.format_exception(type, value, tb)` returns a list of strings ending in `\n`; we strip the trailing `\n` to match the JSON shape Story 1.2 establishes (list of bare strings).

### Why the stubs raise NotImplementedError, not just exist as `None`

`from ulog.testing import replay_records` followed by `if replay_records is None:` — would be a footgun. The Pythonic contract is "if the name resolves, the callable exists; if you call it and the operation isn't implemented, you get NotImplementedError". This is the same pattern stdlib uses (e.g. `numbers.Real.__truediv__` is abstract; calling it raises).

### Why `TestSession` is a dataclass with placeholder fields

Architecture.md (step-06) specifies `TestSession` as a "dataclass exported from `ulog.testing`". v0.3 publishes the import surface so v0.5 can extend without breaking client code. The placeholder fields (`name`, `records`) are provisional; v0.5 may add `start_ts`, `end_ts`, etc. The shape is fluid pre-1.0 release.

### `ulog/testing/__init__.py` import — why direct, not lazy

`from .test_event import test_event` at module top-level is fine because:
- `ulog.testing` is only imported when the `[testing]` extra is installed (the sub-package's `__init__.py` is the entry point).
- `test_event.py` itself uses lazy `import ulog` inside the context manager body to avoid circular-import issues at module-load time.

### Architecture references

| Topic | Read |
|---|---|
| PRD §5.2 programmatic API | `docs/prds/PRD-v0.3-test-integration.md` §5.2 |
| Test event schema | `docs/prds/PRD-v0.3-test-integration.md` §2.1.2 |
| Decision C2 — sub-package | `_bmad-output/planning-artifacts/architecture.md` § "Decision C2" |
| step-06 sub-package layout | `_bmad-output/planning-artifacts/architecture.md` line 937 |
| Gap G5 stable signature anchor | `_bmad-output/planning-artifacts/architecture.md` § "G5" |
| Story 1.2 record shape (mirror this) | `ulog/testing/pytest_plugin.py:226-280` (`_emit_outcome_records`) |
| Story 1.4 propagation site | `ulog/testing/pytest_plugin.py:106-130` (bind/unbind ordering) |
| `ulog.bind/unbind` primitives | `ulog/context.py:42-67` |
| Existing test fixture pattern | `tests/test_pytest_plugin.py:124-168` (record-readback via sqlite3) |

### Files being modified

#### `ulog/testing/__init__.py` (UPDATE)

Currently 14 lines (placeholder docstring + empty `__all__`). After Story 1.9: ~50 lines including the `replay_records` stub + `TestSession` dataclass + `from .test_event import test_event` + `__all__` = `["test_event", "replay_records", "TestSession"]`.

#### `ulog/testing/test_event.py` (NEW)

~140 lines including docstring, `_TestEventHandle` class, `test_event` context manager.

#### `tests/test_test_event.py` (NEW)

~250 lines including 11 tests + autouse `_isolate` fixture + `_read_records` helper.

#### Other files (DO NOT MODIFY)

`pyproject.toml`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/`, `ulog/testing/pytest_plugin.py`, `tests/test_pytest_plugin.py`, `tests/test_web.py`, all other tests.

### Story 1.8 lessons applied (carry-forward)

- **Read-only paths use `engine.connect()` not `engine.begin()`** — N/A here (no SQL access in `test_event`; it just emits log records via stdlib).
- **Set comparisons for order-independent assertions** — applies if any test compares unordered collections (none in this story; record ORDER matters per AC1).
- **Defensive `getattr` patterns** — apply in `_TestEventHandle` if needed (it's not, since the class is closed-shape).
- **`mypy` baseline** — Story 1.9 adds new files; no pre-existing baseline to compare. New code MUST be fully typed (no `# type: ignore`).

### LLM-Dev anti-patterns to avoid

| Anti-pattern | Why avoid | Correct approach |
|---|---|---|
| Implementing `test_event` as a class with `__enter__`/`__exit__` instead of `@contextmanager` | Verbose and error-prone for the bind/unbind+emit lifecycle | Use the `@contextmanager` decorator; let Python handle the protocol |
| Lazy-import `ulog` at the test_event module top | The package itself is `ulog.testing` so the parent `ulog` is already imported by the time this module loads | Direct import is fine; lazy is only needed inside the context manager body to avoid a circular-import edge |
| Naming the handle class `TestEvent` (no underscore) | Public name implies user can instantiate directly; the only sanctioned API is `with test_event(...) as ev` | `_TestEventHandle` (underscore-prefixed) signals "internal" |
| Letting `ev.outcome(...)` AND auto-emit both fire | Double outcome record breaks Story 1.2's "exactly one outcome per test" contract | Track `_outcome_emitted` flag on the handle; auto-emit checks it |
| Catching the exception in `__exit__` and not re-raising | The user's test framework relies on exception propagation to mark the test as failed | Re-raise via bare `raise` |
| Using `time.time()` instead of `time.perf_counter()` | `time.time()` can go backwards under NTP correction → negative duration | `perf_counter` is monotonic |
| Letting `replay_records` be a no-op (silently succeeds) | Hides the "v0.5 only" status; users could ship code that "works" but emits nothing | `raise NotImplementedError` with a message pointing at v0.5 / Story 4.9 |
| Making `TestSession.__post_init__` raise unconditionally | Some users may construct empty TestSession instances for type-checking or testing the import | `__post_init__` is `pass` — construction allowed, full behavior NotImplementedError-deferred to v0.5 |
| Adding `test_event` to `ulog.__all__` (top-level package) | Subpackage exports stay in the subpackage namespace; `ulog.test_event` would imply a top-level name | Stay in `ulog.testing` namespace — `from ulog.testing import test_event` |
| Adding `pytest` to `test_event`'s imports | This module must be usable by NON-pytest runners | Pure stdlib + `ulog` only |
| Forgetting to handle `BaseException` instead of `Exception` | KeyboardInterrupt / SystemExit are BaseExceptions; the user wants those to be marked `errored` too (the test was interrupted) | Catch `BaseException`, not just `Exception` |
| Computing duration AFTER `traceback.format_exception` | The traceback formatting can take milliseconds on deep stacks; biases the measured duration | Compute `duration_s` FIRST, then format the traceback |

### References

- [Source: `docs/prds/PRD-v0.3-test-integration.md`#5.2] programmatic API spec
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#2.1.2] record shape
- [Source: `_bmad-output/planning-artifacts/epics.md`#Story 1.9] AC framing
- [Source: `_bmad-output/planning-artifacts/architecture.md`#Decision C2] sub-package layout
- [Source: `_bmad-output/planning-artifacts/architecture.md`#G5] stable signature anchor
- [Source: `_bmad-output/implementation-artifacts/1-2-test-event-recording-start-outcome-finish.md`] record shape mirrored here
- [Source: `_bmad-output/implementation-artifacts/1-3-test-id-stability-for-parametrized-tests.md`] `_make_test_id` contract (test_event uses caller-supplied name, not nodeid — but the same `test_id` field name applies)
- [Source: `_bmad-output/implementation-artifacts/1-4-bound-context-propagation-of-test-id.md`] propagation contract this story ALSO satisfies
- [Source: `ulog/context.py`:42-67] bind/unbind primitives
- [Source: `ulog/testing/pytest_plugin.py`:106-280] reference implementation (mirror its emit shape exactly)

### Library / framework versions

- **Python `>=3.10`**. `@contextmanager`, `time.perf_counter()`, `traceback.format_exception()` all stdlib stable.
- **No new dependencies.** `dependencies = []` regression gate stays green.

### Definition of Done — Story 1.9

- [ ] `ulog/testing/test_event.py` exists with `_TestEventHandle` class + `test_event` `@contextmanager`.
- [ ] `ulog/testing/__init__.py` exports `test_event`, `replay_records` (stub), `TestSession` (stub) via `__all__`.
- [ ] `replay_records()` raises `NotImplementedError` with a v0.5 / Story 4.9 reference.
- [ ] `TestSession` is a `@dataclass` with placeholder fields.
- [ ] `tests/test_test_event.py` has 11 new tests covering AC1-AC8.
- [ ] Test module count: **NEW** `test_test_event.py` with 11 tests. Full suite: 152 + 11 = **163 tests**.
- [ ] `mypy ulog/testing/ --follow-imports=silent` clean — new files fully typed.
- [ ] `grep '^dependencies' pyproject.toml | grep -q '\[\]'` → exit 0.
- [ ] `git diff --stat HEAD --` reports ONLY `ulog/testing/__init__.py`, `ulog/testing/test_event.py` (new), `tests/test_test_event.py` (new).
- [ ] AC1-AC9 each verifiable.
- [ ] Story 1.10 (xdist edge cases) and 1.11 (docs) build on `test_event` API in the doc page only.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
