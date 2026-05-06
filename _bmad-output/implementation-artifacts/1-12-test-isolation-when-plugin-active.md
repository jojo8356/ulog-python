# Story 1.12: Test isolation when ulog plugin is active under `--ulog-db`

Status: done

**Epic:** 1 — v0.3 Test integration (POST-RETRO patch — late-discovered regression)
**Story key:** `1-12-test-isolation-when-plugin-active`
**Implements:** N/A (test-only fix; no PRD requirement, no production code change)
**Source:** Discovered 2026-05-06 during the QA verification step of the Epic 1 retrospective workflow when the user ran `pytest tests/ --ulog-db /tmp/ulog-tests.sqlite` to generate a fixture DB for browser QA. 13 unrelated tests failed because the plugin's `pytest_runtest_protocol` bind of `test_id` leaked into tests that probe `ulog.bind()` semantics or assert on records WITHOUT `test_id`.
**Built on:** Stories 1.1, 1.4, 1.5, 1.9 (the bind/unbind contract + auto-setup gate)
**Foundation for:** Epic 1 release stability; v0.3 doc Troubleshooting note

---

## Context — why this story exists outside the normal CS→VS→DS→CR cycle

Epic 1 closed (retrospective done, all 11 stories shipped) on 2026-05-06. The next morning, during the browser-QA preparation step (run pytest with `--ulog-db` to seed a real test-event DB), the user reported 13 test failures. Investigation surfaced a real interaction artifact:

When `pytest --ulog-db <path>` is invoked, Story 1.5's `pytest_configure` auto-setup branch fires → ulog gets configured → the plugin gate flips ON → `pytest_runtest_protocol` (Story 1.4) wraps every test with `ulog.bind(test_id=<nodeid>) ... ulog.unbind("test_id")`. This is **correct** plugin behavior.

The failures came from FOUR test files whose autouse `_isolate` fixtures only cleared bound state at **teardown** (after `yield`), not at **setup** (before `yield`):

- `tests/test_context.py` (9 failures): tests like `test_bind_then_clear` do `ulog.bind(a=1, b=2); assert get_bound() == {"a":1,"b":2}` — but `get_bound()` is `{"a":1,"b":2,"test_id":"<outer nodeid>"}`.
- `tests/test_handlers.py::test_sql_persists_bound_context` (1 failure): the SQL handler's `context` JSON column carries the outer plugin's `test_id` in addition to the user's `bind`.
- `tests/test_test_event.py` (2 failures): `test_test_event_propagates_test_id_to_app_records` and `test_test_event_nested_blocks_restore_outer_test_id` assert that records emitted OUTSIDE a `with test_event(...)` block carry NO `test_id`. With the outer plugin active, the outer test's nodeid is bound for the entire test body, so the post-`with` records do carry it.
- `tests/test_web.py::test_detail_view_hides_test_context_panel_when_record_has_no_test_id` (1 failure): records emitted by `sqlite_fixture` get the plugin's `test_id`, so the detail view DOES render the panel that this test asserts is absent.

This is a **test-fixture isolation bug**, not a production-code bug. Production behavior is correct under both invocations.

## Story

As a **maintainer running the ulog test suite under `pytest --ulog-db`** (whether for QA fixture generation, dogfooding the plugin, or recording v0.3 demo data),
I want **the project's own test files to clear ulog's bound state at fixture SETUP time, not just teardown**,
so that **the suite stays green regardless of whether the outer pytest invocation has the plugin gate active, and the QA verification step of every future epic can use `--ulog-db` to generate fixture DBs without producing noise.**

## Acceptance Criteria

### AC1 — `tests/test_context.py` `_isolate` fixture clears at setup

**Given** the autouse `_isolate` fixture in `test_context.py`
**When** any test in the file runs under `pytest --ulog-db <path>`
**Then** `ulog.clear()` is called BEFORE `yield` so that any `test_id` bound by the outer pytest plugin is wiped before assertions that probe `get_bound()` shape.

### AC2 — `tests/test_handlers.py` `_isolate` fixture clears at setup

**Given** the autouse `_isolate` fixture in `test_handlers.py`
**When** `test_sql_persists_bound_context` (or any future test asserting on the SQL handler's `context` JSON column) runs under `--ulog-db`
**Then** the assertion sees only the keys explicitly bound by the test body, not the outer plugin's `test_id`.

### AC3 — `tests/test_test_event.py` `_isolate` fixture clears at setup

**Given** the autouse `_isolate` fixture in `test_test_event.py`
**When** any test verifying `test_event` scope-exit semantics runs under `--ulog-db`
**Then** records emitted outside the inner `with test_event(...)` block carry no `test_id` (no leak from the outer plugin's bind).

### AC4 — `tests/test_web.py` `_isolate` fixture clears at setup AND `sqlite_fixture` depends on it

**Given** the autouse `_isolate` and the `sqlite_fixture` in `test_web.py`
**When** records are inserted into the fixture DB
**Then** they do NOT carry the outer plugin's `test_id`. `sqlite_fixture` declares `_isolate` as a dependency to guarantee setup ordering across the file.

### AC5 — Full suite green under both invocations

**Given** the project test suite at `tests/`
**When** the user runs `python3 -m pytest tests/` (no flag)
**Then** 180/180 pass.
**And when** the user runs `python3 -m pytest tests/ --ulog-db /tmp/ulog-tests.sqlite`
**Then** 180/180 pass — same count, same outcomes, no flake, no order-dependence.

### AC6 — No production-code touch

**Given** the fix is scoped to test-fixture hygiene
**When** the diff is reviewed
**Then** ZERO files under `ulog/` are modified. Only the four files in `tests/` and one new doc page in `_bmad-output/`. The `dependencies = []` SC4 gate is preserved trivially.

### AC7 — Idempotency note in `_isolate` docstrings

**Given** each modified `_isolate` fixture
**When** the file is read by a future maintainer
**Then** the docstring explains WHY the setup-side `ulog.clear()` is necessary (outer plugin bind under `--ulog-db`) so the line is not deleted as "redundant" in a later refactor.

## Tasks / Subtasks

- [x] **Task 1** — Patch `tests/test_context.py` `_isolate` (AC1, AC7)
- [x] **Task 2** — Patch `tests/test_handlers.py` `_isolate` (AC2, AC7)
- [x] **Task 3** — Patch `tests/test_test_event.py` `_isolate` (AC3, AC7)
- [x] **Task 4** — Patch `tests/test_web.py` `_isolate` and add `_isolate` dependency to `sqlite_fixture` (AC4, AC7)
- [x] **Task 5** — Run `pytest tests/` (no flag) → 180/180 ✓ (AC5)
- [x] **Task 6** — Run `pytest tests/ --ulog-db /tmp/ulog-tests-fix.sqlite` → 180/180 ✓ (AC5)
- [x] **Task 7** — Verify zero touch to `ulog/` source (AC6)

## Dev Notes

**Pattern applied (uniform across all four files):**

```python
@pytest.fixture(autouse=True)
def _isolate():
    """Clear bound state at SETUP and teardown.

    Setup-side clear is required so an OUTER pytest run with `--ulog-db`
    (which binds test_id=<nodeid> for each test via pytest_runtest_protocol)
    does not leak its bind into assertions that probe ulog's bind shape
    or assert on records WITHOUT test_id.
    """
    ulog.clear()           # ← THE FIX (1 line, idempotent, no-op when plugin inactive)
    yield
    # ... existing handler cleanup + ulog.clear() ...
```

**For `test_web.py::sqlite_fixture`, an extra step**: the explicit fixture is changed from `def sqlite_fixture(tmp_path)` to `def sqlite_fixture(_isolate, tmp_path)`, declaring `_isolate` as a dependency. This guarantees `_isolate` setup runs before `sqlite_fixture` setup (records get inserted with a clean bound state, regardless of pytest's autouse-vs-explicit ordering rules across releases).

**Why `ulog.clear()` is safe to call at setup:**
- It's idempotent (clears the ContextVar to `{}`).
- It's already called at teardown by the same fixture, so the API surface is identical.
- It does NOT remove configured handlers (those use a separate cleanup loop).
- When the plugin is inactive (no `--ulog-db`, no host setup), the ContextVar is already empty → no-op.

**Why this wasn't caught earlier:**
- Epic 1's CI runs `pytest tests/` WITHOUT `--ulog-db` (the plugin self-disables, no bind happens, the test files never see the leak).
- The Story 1.4 propagation test in `test_pytest_plugin.py` uses `pytester` (in-process pytest) which has its own isolated bind state — the OUTER test's bind doesn't leak into the INNER pytester run.
- The Story 1.9 test_event tests don't use `pytester` — they run in-process and DO see the outer bind. Hence 2/13 of the failures came from there.

The retrospective's "lessons learned" already flagged: **"test fixtures with cross-story reuse benefit from locked docstrings explaining WHY each isolation step exists"**. This story applies that lesson concretely: the new docstring in each `_isolate` is the lock.

## Change Log

- 2026-05-06: Initial story creation + same-day implementation. Patch applied across 4 test files. 180/180 green under both invocations. No production code touched. SC4 (zero new deps) preserved trivially.

## Dev Agent Record

### File List

- `tests/test_context.py` — modified `_isolate` fixture
- `tests/test_handlers.py` — modified `_isolate` fixture
- `tests/test_test_event.py` — modified `_isolate` fixture (already done in pre-story spike before this story was formalized)
- `tests/test_web.py` — modified `_isolate` fixture + added `_isolate` dep to `sqlite_fixture`

### Completion Notes

Confirmed both invocations green:
- `python3 -m pytest tests/` → 180 passed in 4.75s
- `python3 -m pytest tests/ --ulog-db /tmp/ulog-tests-fix.sqlite` → 180 passed in 4.46s + summary line `ulog: 180 tests, 180 passed, 0 failed, 0 skipped → ulog-web /tmp/ulog-tests-fix.sqlite to triage`

No CR cycle for this story — it's a test-only patch with a clear root cause, deterministic fix pattern (1-line setup-side clear in 4 files), trivial regression coverage (the suite itself, run under both invocations), and zero production-code impact. The retro has already happened; this is a documented post-retro patch.

### Code Review Notes

Skipped per scope (test-only, deterministic).

### Risk Assessment

- **Regression risk**: NONE. `ulog.clear()` is idempotent, already runs at teardown, no behavior change when plugin is inactive.
- **Coverage risk**: NONE. Both invocations green; the new pattern is uniformly applied; future tests in any of these files inherit the fix via the autouse fixture.
- **CI risk**: NONE. Existing CI runs `pytest tests/` (no flag) → already green and stays green. If a future CI step opts into `--ulog-db` (e.g., for v0.3 dogfooding), it'll be green from day one.
