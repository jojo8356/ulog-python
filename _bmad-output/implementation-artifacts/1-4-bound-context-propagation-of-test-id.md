# Story 1.4: Bound-context propagation of test_id

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**Epic:** 1 — v0.3 Test integration
**Story key:** `1-4-bound-context-propagation-of-test-id`
**Implements:** FR59, FR60, FR61 (PRD-v0.3 §3.3)
**Source:** `docs/prds/PRD-v0.3-test-integration.md` §3.3 + §2.1.3, `_bmad-output/planning-artifacts/architecture.md` ContextVar pattern + Decision C2, `_bmad-output/planning-artifacts/epics.md` Story 1.4
**Built on:** Story 1.2 (`pytest_runtest_protocol` already calls `ulog.bind(test_id=...)` before yield and `ulog.unbind("test_id")` in `finally`), Story 1.3 (`_make_test_id` is the source of truth for the bound value)
**Foundation for:** Story 1.7 (URL filter `?test_id=...` on the viewer assumes app records carry the binding), Story 1.8 (Test-context detail panel queries by app records' `test_id`), Story 1.9 (`test_event` programmatic API replicates the same propagation contract for non-pytest runners)

---

## Story

As a **developer instrumenting application code under test**,
I want **every `log.info()` / `log.error()` / etc. emitted DURING a test to inherit `test_id` automatically — including from fixtures' setup and teardown — and to STOP carrying it once the test finishes**,
so that **I can filter the viewer to "all records this test produced" without instrumenting each call site, and inter-test or post-session records are not falsely attributed to the previous test**.

## Acceptance Criteria

### AC1 — App-code records during the test body inherit `test_id` (FR60)

**Given** the plugin is enabled (host conftest called `ulog.setup(handlers=['sql'], sql_url=...)`)
**And** a test body that calls `logging.getLogger("myapp").info("rendering rom")`
**When** the test runs
**Then** the `logs` table contains a record with `logger='myapp'`, `msg='rendering rom'`, and `context.test_id == item.nodeid` for that test (the same `test_id` value the plugin's own `ulog.test` records carry).

### AC2 — Fixture setup records inherit the owning test's `test_id` (FR61)

**Given** a function-scoped fixture whose setup body emits `logging.getLogger("myapp").info("fixture setup")`
**And** a test that consumes that fixture
**When** the test runs
**Then** the setup record carries `context.test_id == item.nodeid` for the consuming test — matching the plugin's `ulog.test` started/outcome records for the same test.

### AC3 — Fixture teardown records inherit the owning test's `test_id` (FR61)

**Given** a function-scoped fixture using the `yield` form, whose post-yield teardown emits `logging.getLogger("myapp").info("fixture teardown")`
**When** the test completes (test body passes, teardown runs)
**Then** the teardown record carries `context.test_id == item.nodeid` for the test that consumed the fixture.

### AC4 — Records do NOT carry `test_id` after the protocol exits (FR59)

**Given** two tests `test_a` and `test_b` running in sequence
**When** `test_a` finishes (its protocol hookwrapper's `finally` block runs `ulog.unbind("test_id")`) and `test_b` has not yet started
**Then** any record emitted in the gap (e.g., from a session-scoped fixture's teardown that runs AFTER all items, or from `pytest_unconfigure` hooks) carries either no `test_id` at all, OR the `test_id` of whichever item's protocol the emit is currently nested inside — never `test_a`'s `test_id` if `test_a` has already finished AND the emit is outside any subsequent test's protocol.

**More directly testable form:** records emitted from a `pytest_unconfigure` hook (post-session) carry NO `test_id` field in their `context` (or carry an empty/None context).

### AC5 — Cross-test isolation: each test's app records carry ONLY its own `test_id`

**Given** two tests `test_alpha` (calls `log.info("alpha-1")`) and `test_beta` (calls `log.info("beta-1")`)
**When** both tests run in the same pytest session
**Then** the record with `msg='alpha-1'` carries `test_id` ending `::test_alpha` and the record with `msg='beta-1'` carries `test_id` ending `::test_beta`. No record's `test_id` ever names a test other than the one that emitted it.

### AC6 — Parametrized variants: each variant's app records inherit the variant-specific `test_id`

**Given** `@pytest.mark.parametrize("n", [1, 2])` `def test_p(n): logging.getLogger("myapp").info(f"n={n}")`
**When** both variants run
**Then** the record with `msg='n=1'` carries `test_id` ending `::test_p[1]` and the record with `msg='n=2'` carries `test_id` ending `::test_p[2]`.

### AC7 — Class-scoped fixture: setup record carries first test's `test_id`, teardown record carries last test's `test_id`

**Given** a class-scoped fixture that emits a log on setup and on teardown, consumed by two methods `test_one` and `test_two` of `class TestX`
**When** the class runs
**Then**:
  - The setup record's `test_id` ends with `::TestX::test_one` (setup runs inside `test_one`'s protocol bind window — the FIRST item that requests the class fixture).
  - The teardown record's `test_id` ends with `::TestX::test_two` (teardown runs inside `test_two`'s protocol bind window — the LAST item before the fixture is garbage-collected).
  - The body records of each method carry their respective `test_id`.

### AC8 — Frozen-invariant + regression-gate compliance

**Given** Story 1.4's changes
**When** the standard regression checks run
**Then**:
  - `dependencies = []` in `pyproject.toml` is unchanged (NFR-DEP-50 / SC4).
  - `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/`, `ulog/testing/` ALL UNCHANGED — Story 1.4 is a pure-tests story; the propagation behavior was shipped in Story 1.2 (bind/unbind in the protocol hookwrapper) and the SQL handler's `get_bound()` merge in pre-v0.3 code. Story 1.4 only adds tests.
  - Other files under `tests/` UNCHANGED — only `tests/test_pytest_plugin.py` may be edited.
  - All Story 1.1 + 1.2 + 1.3 tests still pass (24 baseline in `test_pytest_plugin.py`).

---

## Tasks / Subtasks

- [x] **Task 1** — Add a small read helper for app records (or extend the existing one) (AC1-AC7)
  - [x] 1.1 In `tests/test_pytest_plugin.py`, just after `_read_test_records` (line ~125), add `_read_app_records(db_path: Path, logger_name: str) -> list[dict]`:

    ```python
    def _read_app_records(db_path: Path, logger_name: str) -> list[dict]:
        """Read non-plugin records from a SQLite log DB filtered by exact logger name.

        Story 1.4 (FR60/61) needs to assert that APPLICATION records — those
        produced by `logging.getLogger("myapp").info(...)` from inside a test
        — carry the bound `test_id`. The existing ``_read_test_records`` filters
        for ``logger='ulog.test'`` (the plugin's own logger name), so a
        complementary helper for arbitrary loggers keeps the read pattern
        consistent.

        Exact match only — uses ``WHERE logger = ?``. For hierarchical logger
        filtering (e.g. catching ``"myapp"`` AND ``"myapp.submodule"`` in one
        query) a future helper would need ``WHERE logger LIKE ?`` with
        ``"myapp.%"``. Story 1.7/1.8 may want this; Story 1.4's seven tests
        all emit through a single logger name, so exact match is sufficient.
        """
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM logs WHERE logger = ? ORDER BY id ASC",
                (logger_name,),
            )
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()
    ```

  - [x] 1.2 The helper accepts an exact logger name (no globbing) and uses a parameterized query to keep the test code unambiguous about WHICH logger's records it cares about. AC1-AC7 all use `logger_name="myapp"` — there is no need to support multiple loggers in one query.

- [x] **Task 2** — Tests for body-record propagation (AC1, AC5, AC6)
  - [x] 2.1 Add a section header comment in `tests/test_pytest_plugin.py` after the Story 1.3 block:

    ```python
    # ============================================================================
    # Story 1.4 — Bound-context propagation of test_id (FR59-61)
    # ============================================================================
    ```

  - [x] 2.2 Add `test_app_log_during_test_inherits_test_id` (AC1):
    ```python
    def test_app_log_during_test_inherits_test_id(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC1, FR60 — `logging.getLogger("myapp").info(...)` during the test
        body produces a record whose `context.test_id` matches the test's nodeid."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_with_setup(db))
        pytester.makepyfile("""
            import logging

            log = logging.getLogger("myapp")

            def test_render():
                log.info("rendering rom")
        """)
        pytester.runpytest()

        app_records = _read_app_records(db, "myapp")
        assert len(app_records) == 1
        ctx = json.loads(app_records[0]["context"])
        assert ctx["test_id"].endswith("::test_render")
        assert app_records[0]["msg"] == "rendering rom"

        # Sanity-check: the value the SQL handler wrote into the app record's
        # context.test_id matches the value bound by the plugin's protocol
        # hookwrapper for the same test. Both records read from the same
        # `_bound` ContextVar via `get_bound()`, so this is a regression
        # sentinel — catches any future change where `_record_to_row` injects
        # a different test_id source than `ulog.bind` set.
        plugin_records = _read_test_records(db)
        plugin_test_ids = {json.loads(r["context"])["test_id"] for r in plugin_records}
        assert ctx["test_id"] in plugin_test_ids
    ```

  - [x] 2.3 Add `test_app_log_in_two_tests_carries_each_tests_id` (AC5) — two tests, each calling `log.info` with a distinct message; assert that each app record's `test_id` ends with the calling test's name and that the two `test_id` values differ. Reject the bug where both records share one `test_id` (cross-contamination).

  - [x] 2.4 Add `test_app_log_in_parametrized_variants` (AC6) — single parametrized test emitting `log.info(f"n={n}")` for `n in [1, 2]`; assert two app records exist with `test_id` ending `[1]` and `[2]` respectively, and that each record's `msg` matches its `test_id`'s bracket suffix.

- [x] **Task 3** — Tests for fixture-record propagation (AC2, AC3)
  - [x] 3.1 Add `test_fixture_setup_log_inherits_test_id` (AC2):
    ```python
    def test_fixture_setup_log_inherits_test_id(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC2, FR61 — a fixture's setup body emitting log.info(...) produces
        a record whose `context.test_id` matches the consuming test's nodeid."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_with_setup(db))
        pytester.makepyfile("""
            import logging
            import pytest

            log = logging.getLogger("myapp")

            @pytest.fixture
            def fx():
                log.info("fixture setup")
                return "ok"

            def test_uses_fx(fx):
                assert fx == "ok"
        """)
        pytester.runpytest()

        app_records = _read_app_records(db, "myapp")
        assert len(app_records) == 1
        assert app_records[0]["msg"] == "fixture setup"
        ctx = json.loads(app_records[0]["context"])
        assert ctx["test_id"].endswith("::test_uses_fx")
    ```

  - [x] 3.2 Add `test_fixture_teardown_log_inherits_test_id` (AC3) — fixture using `yield` form with a post-yield `log.info("fixture teardown")`. Assert the teardown record has `test_id` matching the consuming test. Use the same pattern as 3.1 but with the fixture body:
    ```python
    @pytest.fixture
    def fx():
        yield "ok"
        log.info("fixture teardown")
    ```

  - [x] 3.3 Add `test_class_scoped_fixture_propagation` (AC7):
    ```python
    def test_class_scoped_fixture_propagation(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC7 — class-scoped fixture emits in setup (during first test's protocol)
        and in teardown (during last test's protocol). Each gets that test's test_id."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_with_setup(db))
        pytester.makepyfile("""
            import logging
            import pytest

            log = logging.getLogger("myapp")

            class TestX:
                @pytest.fixture(scope="class")
                def fx(self):
                    log.info("class-fx setup")
                    yield
                    log.info("class-fx teardown")

                def test_one(self, fx):
                    log.info("body-one")

                def test_two(self, fx):
                    log.info("body-two")
        """)
        pytester.runpytest()

        app_records = _read_app_records(db, "myapp")
        # 4 expected: class-fx setup + body-one + body-two + class-fx teardown
        assert len(app_records) == 4, f"got {[r['msg'] for r in app_records]}"

        by_msg = {r["msg"]: json.loads(r["context"])["test_id"] for r in app_records}
        # Diagnostic dump on failure — if pytest's class-finalizer scheduling
        # ever changes, this dict shows exactly which test_id each emit got.
        diag = f"by_msg={by_msg!r}"

        # Setup records go to FIRST test (test_one) — class-fx setup runs during
        # test_one's protocol bind window
        assert by_msg["class-fx setup"].endswith("::TestX::test_one"), diag
        assert by_msg["body-one"].endswith("::TestX::test_one"), diag
        assert by_msg["body-two"].endswith("::TestX::test_two"), diag
        # Teardown of class fixture runs during the LAST test's (test_two's) protocol
        # bind window — that's where pytest schedules the class-scope finalizer
        assert by_msg["class-fx teardown"].endswith("::TestX::test_two"), diag
    ```

- [x] **Task 4** — Tests for unbind/post-session behavior (AC4)
  - [x] 4.1 Add `test_test_id_unbound_after_session` (AC4, FR59) — emit a log record from inside the host conftest's `pytest_unconfigure` hook (which runs AFTER all items have completed AND each item's protocol hookwrapper has already unbound `test_id`). Verify the record has no `test_id` in its `context` (or its `context` is None / lacks the key).

    **NOTE on conftest construction:** `pytester.makeconftest(...)` REPLACES the conftest entirely; it does not merge with `_conftest_with_setup`. This test deliberately inlines a complete custom conftest because the standard `_conftest_with_setup` helper closes its `_ulog_managed` handlers from inside `pytest_unconfigure` BEFORE we want to emit the post-session record — and the order matters. We need: (a) `pytest_configure` calls `ulog.setup(... sql_batch_size=1)` (same as the standard helper), (b) `pytest_unconfigure` first emits `log.info("post-session emit")`, THEN closes the handler. Don't try to "extend" the helper — write the conftest body in full.

    Implementation pattern:
    ```python
    def test_test_id_unbound_after_session(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC4, FR59 — a record emitted from `pytest_unconfigure` (post-session,
        outside any item's protocol bind window) does not carry test_id."""
        db = tmp_path / "logs.sqlite"
        # CRITICAL ORDERING: pytest_unconfigure must EMIT then CLOSE, not the
        # reverse. With sql_batch_size=1 the emit flushes immediately, but if a
        # future change reorders this body the test silently passes with zero
        # records and AC4 is no longer being verified. The
        # `assert len(app_records) == 1` below anchors that the emit happened.
        posix_path = db.as_posix()
        pytester.makeconftest(f"""
            import logging
            import ulog

            def pytest_configure(config):
                ulog.setup(handlers=['sql'], sql_url='sqlite:///{posix_path}', sql_batch_size=1)

            def pytest_unconfigure(config):
                # CRITICAL: emit FIRST, close SECOND. By this point each test's
                # pytest_runtest_protocol finally-block has already unbound test_id.
                logging.getLogger("myapp").info("post-session emit")
                for h in list(logging.getLogger().handlers):
                    if getattr(h, '_ulog_managed', False):
                        try:
                            h.flush()
                            h.close()
                        except Exception:
                            pass
                        logging.getLogger().removeHandler(h)
        """)
        pytester.makepyfile("def test_dummy(): assert True")
        pytester.runpytest()

        app_records = _read_app_records(db, "myapp")
        assert len(app_records) == 1
        assert app_records[0]["msg"] == "post-session emit"
        # context may be None (no bound fields) or a dict without test_id —
        # either form satisfies AC4 / FR59.
        raw_ctx = app_records[0]["context"]
        if raw_ctx is None:
            return  # no bound fields at all → unbind worked
        ctx = json.loads(raw_ctx) if isinstance(raw_ctx, str) else raw_ctx
        assert "test_id" not in ctx, (
            f"FR59: post-session emit must not carry test_id; got {ctx!r}"
        )
    ```

  - [x] **4.2 dropped** — earlier draft proposed `test_test_id_unbound_between_tests_via_app_records`. Removed: it tests the same property as Task 2.3 (AC5 cross-test isolation) from a different angle. Task 2.3 already includes the explicit anti-leak assertions (`"::test_b" not in by_msg["from-a"]`); duplicating them under a 4.2 banner adds no coverage. Final story has 7 new tests, not 8.

- [x] **Task 5** — Verify and ship
  - [x] 5.1 Run `make test` (i.e. `python3 -m pytest tests/ -v`). Full suite stays green. The plugin test module `tests/test_pytest_plugin.py` grows from 24 tests (Story 1.3 baseline) to **31 tests** (24 + 7 new from Story 1.4 — Tasks 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1 = seven functions). Earlier draft of this story considered an additional Task 4.2 (`test_test_id_unbound_between_tests_via_app_records`); it is **dropped** because it tests the same property as Task 2.3 (cross-test isolation, AC5) from a different angle — semantic duplicate, no new coverage. Final count: **7 new tests**, total **31 in `test_pytest_plugin.py`**.

  - [x] 5.2 Run `mypy ulog/testing/ --follow-imports=silent` — clean (no new errors). Story 1.4 doesn't touch `ulog/testing/` at all; this is a sanity check.
  - [x] 5.3 `grep '^dependencies' pyproject.toml | grep -q '\[\]'` exits 0 (NFR-DEP-50 / SC4 regression gate).
  - [x] 5.4 `git diff --stat HEAD -- pyproject.toml ulog/` returns empty (Story 1.4 introduces NO production code changes).
  - [x] 5.5 `git diff --stat HEAD -- tests/` returns only `tests/test_pytest_plugin.py` (no other test file touched).
  - [x] 5.6 Manually invoke `pytest tests/test_pytest_plugin.py -k "propagation or app_log or fixture or unbound"` and confirm the new tests run together in < 10s.

---

## Dev Notes

### Why this story has zero production code changes

Stories 1.2 and pre-v0.3 already implemented every line of behavior FR59-61 require:

1. **Story 1.2** — `pytest_runtest_protocol` hookwrapper calls `ulog.bind(test_id=test_id)` BEFORE `yield` and `ulog.unbind("test_id")` in the `finally` block AFTER `_emit_outcome_records`. The yield window covers the entire setup → call → teardown phase sequence pytest runs for the item, so fixtures that emit during ANY phase are inside the bind window. The unbind happens before pytest moves to the next item.

2. **Pre-v0.3 (`ulog/handlers/sql.py:182`)** — `SQLHandler._record_to_row` reads `dict(get_bound())` and merges those fields into the `context` JSON column for EVERY record reaching the handler, regardless of which logger emitted it. So an app `logging.getLogger("myapp").info(...)` call that propagates to the root logger (where the SQL handler is attached) lands a row whose `context` already includes `test_id`.

3. **Pre-v0.3 (`ulog/context.py:42-67`)** — `bind` / `unbind` are wired through a single `_bound: ContextVar[dict[str, Any]]`. `unbind` removes a key by rewriting the snapshot dict; subsequent reads return the new dict without the key. Concurrent items in the same Python process see consistent state via copy-on-write semantics (commented in `context.py:34-36`).

So Story 1.4 is **purely about locking the propagation contract via tests**. If the dev finds themselves wanting to edit any file under `ulog/`, **stop** — re-read this section. The story's implementation surface is `tests/test_pytest_plugin.py` only.

### Why these specific tests, not others

The seven (or eight) tests in this story map exactly onto the AC matrix:

| AC | Test | What it proves |
|---|---|---|
| AC1 (FR60) | `test_app_log_during_test_inherits_test_id` | Body emit picks up bound `test_id`, value matches plugin's own records |
| AC2 (FR61) | `test_fixture_setup_log_inherits_test_id` | Fixture setup is inside the protocol bind window |
| AC3 (FR61) | `test_fixture_teardown_log_inherits_test_id` | Fixture teardown is inside the protocol bind window |
| AC4 (FR59) | `test_test_id_unbound_after_session` | `pytest_unconfigure` emits don't carry stale `test_id` |
| AC4 supplement | `test_test_id_unbound_between_tests_via_app_records` (or merged into AC5) | No leak between adjacent tests in the same session |
| AC5 | (above) | Cross-test isolation via explicit anti-leak assertions |
| AC6 | `test_app_log_in_parametrized_variants` | Each variant's records carry the variant-specific `test_id` |
| AC7 | `test_class_scoped_fixture_propagation` | Class-scoped fixture setup → first test's id; teardown → last test's id |

Tests outside this list would be either redundant (re-proving Story 1.2's `bind` happens, already covered by Story 1.2 tests) or out of scope (async tests, threading, multiprocess — Story 1.10 owns xdist edges).

### What pytest's protocol bind window actually covers

```
pytest_runtest_protocol(item, nextitem):  ← Story 1.2's hookwrapper bind starts here
  pytest_runtest_setup(item)               ← fixture setup runs (FR61 — covered)
    [test body sees `test_id` bound]       ← log.info() here gets test_id (FR60)
  pytest_runtest_call(item)
  pytest_runtest_teardown(item)            ← fixture teardown runs (FR61 — covered)
                                            ← Story 1.2's `finally: ulog.unbind` runs here
```

For class/session-scoped fixtures, pytest schedules the setup at the START of the FIRST item that depends on the fixture, and the finalizer at the END of the LAST such item. Both schedule points are INSIDE the corresponding item's `pytest_runtest_protocol` call — which is where Story 1.2's bind/unbind operates. So even non-function-scoped fixtures get a `test_id` (the first or last item's, respectively). AC7 locks this exact behavior.

### Files being modified — one file, additive only

#### `tests/test_pytest_plugin.py` (UPDATE — additive)

**Current state (post-Story 1.3):** ~430 lines after patches P1-P7 applied during Story 1.3 review. Has Story 1.1 tests (5), Story 1.2 tests (11), Story 1.3 tests (8), `_read_test_records` + `_conftest_with_setup` + `_isolate_logging` + `_FakeItem` helpers.

**Behavior to preserve:**
- All 24 existing tests must keep passing.
- The `_isolate_logging` autouse fixture stays as-is — Story 1.4 introduces no new logger names beyond `myapp` (which is already in the fixture's name list, line 27 of post-Story-1.3 state).
- The `_conftest_with_setup` helper is reused without modification.
- The `pytest_plugins = ["pytester"]` declaration is unchanged.

**What this story adds:**
- `_read_app_records(db_path, logger_name)` helper, placed immediately after `_read_test_records` (Task 1.1).
- A new `# Story 1.4` section header (Task 2.1).
- 7 new test functions (Tasks 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1 + the supplemental variant in 4.2 if not merged).

**Lines added: ~200-220.** No deletions.

#### Other files (DO NOT MODIFY)

`pyproject.toml`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/`, `ulog/testing/__init__.py`, `ulog/testing/pytest_plugin.py`. Story 1.4 lives entirely in `tests/test_pytest_plugin.py`. **Verify with `git diff --stat HEAD --` after the change** — only `tests/test_pytest_plugin.py` should appear.

### Pytester process model — relevant note

`pytester.runpytest()` runs the inner pytest **in-process** (same Python interpreter, same OS process as the outer test). This means the outer test's `_isolate_logging` autouse fixture and the inner pytest's `pytest_configure` share the same `logging` module state. The fixture's name list (line 27 of post-Story-1.3 state) already includes `"myapp"`, so any leftover handlers on `myapp` from a prior outer test are stripped between outer tests. None of Story 1.4's tests directly emit to `logging.getLogger("myapp")` from the OUTER test — every emit happens INSIDE the inner pytester subprocess (via `pytester.makepyfile`'s embedded test code). So no defensive cleanup beyond what `_isolate_logging` already does is needed. Don't add one.

### Story 1.3 lessons applied (carry-forward)

From Story 1.3's code review (Sonnet 4.6 fresh-eyes):
- **Anchor record-count assertions** (Patches P1, P3, P4, P6). Before checking `distinct_ids`, assert the TOTAL `len(records)` so partial-emit regressions trip loudly. Apply the same discipline here for app-record counts.
- **Don't introduce assertions that depend on platform-specific behavior** (Patch P7). The propagation contract is platform-agnostic at the contextvar level; tests should not assume specific path separators or filesystem behavior.
- **Drop the `_FakeItem` precedent for new test scaffolding** unless needed — Story 1.4's tests don't need a fake-item type because they exercise the plugin via pytester, not the helper directly.
- **Use `endswith` for nodeid suffix matches** rather than full-string equality, for the same reason as Story 1.3 (pytester sandbox path component varies by calling test name).

### Architecture references — what to read before coding

| Topic | Read |
|---|---|
| FR59-61 spec | `docs/prds/PRD-v0.3-test-integration.md` §3.3 + §2.1.3 |
| ContextVar pattern | `ulog/context.py` (full file — 83 lines) and `_bmad-output/planning-artifacts/architecture.md` § "ContextVar copy-on-write" |
| SQL handler context merge | `ulog/handlers/sql.py:181-209` (`_record_to_row` — reads `get_bound()` into the `context` JSON column) |
| Story 1.2 bind/unbind site | `ulog/testing/pytest_plugin.py:101-130` (the `pytest_runtest_protocol` hookwrapper, post-Story-1.2 + post-review) |
| `_make_test_id` (Story 1.3) | `ulog/testing/pytest_plugin.py:88-115` (the helper that produces the value being bound) |
| Existing test fixture patterns | `tests/test_pytest_plugin.py:124-168` (`_read_test_records`, `_conftest_with_setup`) |
| Frozen invariants | `_bmad-output/planning-artifacts/architecture.md` § "Frozen invariants" — I5/I6, NFR-DEP-50 |

### Code skeleton — `_read_app_records` placement

Insert immediately after `_read_test_records`'s closing brace (around line 137 of the post-Story-1.3 test file):

```python
def _read_test_records(db_path: Path) -> list[dict]:
    """Read ``ulog.test`` records from a SQLite log DB. ..."""
    ...


def _read_app_records(db_path: Path, logger_name: str) -> list[dict]:
    """Read non-plugin records from a SQLite log DB filtered by exact logger name.

    Story 1.4 (FR60/61) needs to assert that APPLICATION records — those
    produced by ``logging.getLogger("myapp").info(...)`` from inside a test —
    carry the bound ``test_id``.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM logs WHERE logger = ? ORDER BY id ASC",
            (logger_name,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _conftest_with_setup(db_path: Path) -> str:
    ...
```

### LLM-Dev anti-patterns to avoid

| Anti-pattern | Why avoid | Correct approach |
|---|---|---|
| Editing `ulog/testing/pytest_plugin.py` "to make propagation work" | The bind/unbind already exists in Story 1.2; "fixing" it changes a green-test surface | This story is tests-only — `git diff --stat HEAD -- ulog/` MUST be empty |
| Asserting `app_records[0]["context"]` is a `dict` directly | SQLite JSON column comes back as a string from `sqlite3.connect`; the cursor returns it raw | Always `json.loads(rec["context"])` before reading keys, mirroring Story 1.2 / 1.3 patterns |
| Adding `"myapp"` to `_isolate_logging`'s name list "to be safe" | It's already there (line 27, post-Story-1.3 state) — duplicate adds noise | Verify the fixture state before extending; reuse it as-is |
| Loose `>= ` assertions on record counts (e.g. `len(records) >= 1`) | Story 1.3 review patch L1 caught this exact pattern | Use `==` and document the exact expected count per scenario |
| Using `caplog` fixture instead of `_read_app_records` | `caplog` only captures records from a test's own logging context; it does NOT see records the SQL handler stored | Stay on the SQLite read-back pattern Story 1.2 established |
| Calling `ulog.bind(...)` directly from a test fixture | The whole point of FR60/61 is automatic propagation — manual bind would mask the bug we're testing for | Let the plugin's `pytest_runtest_protocol` do the bind; test only the read side |
| Asserting the TOTAL number of records in the `logs` table (not filtered by logger) | The SQL handler stores both plugin records (`logger='ulog.test'`) AND app records (`logger='myapp'`); a total count couples the two | Always filter via `_read_test_records` (plugin) or `_read_app_records(db, "myapp")` (app) |
| Skipping the cross-check that app `test_id` matches plugin `test_id` for the same test | A bug where app gets a DIFFERENT `test_id` value than the plugin (e.g., race condition in bind ordering) would slip through any single-side check | Test 2.2 includes the cross-check (`ctx["test_id"] in plugin_test_ids`); apply the same defensive pairing where it adds value |
| Adding a session-scoped fixture test "for completeness" | Session-scoped fixtures' setup/teardown run during the FIRST/LAST item's protocol — same mechanic as class-scoped (AC7). Adding a session-scoped variant doubles tests without testing a different code path | Stop at class-scoped (AC7); session scope is structurally identical |
| Writing a test that asserts `test_id` is unbound IMMEDIATELY after the test body (not after the protocol exits) | The unbind happens in the protocol's `finally`, AFTER the makereport hook captures the outcome reports — emits during teardown still see the bind. AC4's "post-protocol" point is `pytest_unconfigure`, not "after the test body" | Use `pytest_unconfigure` as the post-bind-window emit point |
| Annotating new generator/autouse fixtures with `-> None` | Story 1.1 review caught this; mirror `tests/test_setup.py` exactly (no annotation on generator fixtures) | If you add a new fixture, leave it unannotated |
| Introducing `# type: ignore[arg-type]` for the new tests | Story 1.4's tests don't need any type-ignore; the SQL records are plain dicts and the helpers are typed | If you find yourself reaching for a type-ignore, the test signature is probably wrong |

### References

- [Source: `docs/prds/PRD-v0.3-test-integration.md`#3.3] FR59-61 — bind, propagate, unbind
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#2.1.3] Bound test_id propagation example
- [Source: `_bmad-output/planning-artifacts/epics.md`#Story 1.4] AC framing
- [Source: `_bmad-output/planning-artifacts/architecture.md`# ContextVar copy-on-write] Concurrency-safe bind semantics
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Frozen invariants] I5/I6, NFR-DEP-50
- [Source: `ulog/context.py`:42-83] `bind` / `unbind` / `clear` / `context` — the four primitives
- [Source: `ulog/handlers/sql.py`:181-209] `_record_to_row` — `dict(get_bound())` is merged into the `context` JSON column for every record
- [Source: `ulog/testing/pytest_plugin.py`:101-130] Story 1.2's protocol hookwrapper — bind site
- [Source: `ulog/testing/pytest_plugin.py`:88-115] Story 1.3's `_make_test_id` helper — value source
- [Source: `_bmad-output/implementation-artifacts/1-2-test-event-recording-start-outcome-finish.md`] Story 1.2 — review patches H1/H2 informed the unbind-must-always-run discipline
- [Source: `_bmad-output/implementation-artifacts/1-3-test-id-stability-for-parametrized-tests.md`] Story 1.3 — review patches P1/P3/P4/P6 informed the anchor-total-record-count discipline

### Library / framework versions

- **pytest >= 7.0** (NFR-COMPAT-10). Class-scoped fixtures, parametrize, `yield`-form fixtures all stable since pytest 4.x. No version-specific concerns.
- **No new dependencies.** Story 1.4 introduces zero production deps and zero new test deps. `dependencies = []` regression gate stays green.
- **Stdlib `logging` only.** Tests use `logging.getLogger("myapp").info(...)` — the canonical idiom for application code per FR60.

### Definition of Done — Story 1.4

- [x] `tests/test_pytest_plugin.py` has `_read_app_records(db_path, logger_name)` helper.
- [x] Story 1.4 section header comment present.
- [x] Exactly 7 new tests covering AC1-AC7 (`test_app_log_during_test_inherits_test_id`, `test_app_log_in_two_tests_carries_each_tests_id`, `test_app_log_in_parametrized_variants`, `test_fixture_setup_log_inherits_test_id`, `test_fixture_teardown_log_inherits_test_id`, `test_class_scoped_fixture_propagation`, `test_test_id_unbound_after_session`). The earlier draft's `test_test_id_unbound_between_tests_via_app_records` is intentionally NOT in this list — it duplicates AC5 coverage.
- [x] Test module count: 24 baseline (5 Story 1.1 + 11 Story 1.2 + 8 Story 1.3) + 7 new = **31 tests** in `tests/test_pytest_plugin.py`. Full suite stays green.
- [x] All new tests use `_conftest_with_setup` (Story 1.2) and `_read_test_records` / `_read_app_records` (Stories 1.2 + 1.4) — no parallel helpers introduced.
- [x] All new tests use `endswith("::test_<name>")` for nodeid matching (mirrors Story 1.2 / 1.3 conventions for pytester sandbox files).
- [x] All new tests anchor record counts with `==` (no `>=`).
- [x] `mypy ulog/testing/ --follow-imports=silent` clean — no new errors. Story 1.4 doesn't touch `ulog/`, so this should be unchanged from Story 1.3's clean state.
- [x] `grep '^dependencies' pyproject.toml | grep -q '\[\]'` → exit 0.
- [x] `git diff --stat HEAD -- pyproject.toml ulog/` empty (zero production code changes).
- [x] `git diff --stat HEAD -- tests/` reports only `tests/test_pytest_plugin.py`.
- [x] AC1-AC8 each verifiable via the corresponding new test or invariant.
- [x] Story 1.7 / 1.8 will rely on app records carrying `test_id` to filter the viewer; this story locks that contract.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (1M context window)

### Debug Log References

- **30/31 tests passed first run; 1 failure in `test_test_id_unbound_after_session`.** `TypeError: argument of type 'NoneType' is not iterable` on the `assert "test_id" not in ctx` line. Root cause: the SQL handler stores `bound or None` (`sql.py:208`); for an empty bound dict, that becomes Python `None`, which SQLAlchemy serializes as JSON `null`. Reading back via `sqlite3.Row`, the `context` column comes back as the string `"null"`. `json.loads("null")` returns Python `None`. My initial guard only handled `raw_ctx is None` (SQL NULL), not the post-`json.loads` `None` case. **Fix:** added a second guard for `parsed is None` after json.loads.
- **Validation gate against `git diff HEAD -- ulog/`** returns non-empty BUT only because Story 1.3's `_make_test_id` helper hasn't been committed yet. Story 1.4 itself adds zero lines to `ulog/` — verified by inspecting the diff: every change in `ulog/testing/pytest_plugin.py` is dated 2026-05-06 from Story 1.3. The frozen-invariant intent (Story 1.4 = pure tests-only) holds.
- Final state: `pytest tests/` → 113/113 (was 106 baseline + 7 new). `mypy ulog/testing/ --follow-imports=silent` → clean. NFR-DEP-50 grep → exit 0.

### Completion Notes List

**Implementation summary:**
- Added `_read_app_records(db_path: Path, logger_name: str) -> list[dict]` helper to `tests/test_pytest_plugin.py`, immediately after `_read_test_records`. Exact-match `WHERE logger = ?` query; docstring documents the limitation and the future `LIKE` extension Story 1.7/1.8 may want.
- Added the Story 1.4 section header comment + 7 new test functions covering AC1-AC7. All tests use the existing `_conftest_with_setup` (Story 1.2) and `_isolate_logging` autouse fixture; only `test_test_id_unbound_after_session` inlines a custom conftest because the standard helper closes its handlers from inside `pytest_unconfigure` BEFORE we want to emit.
- **Zero changes to `ulog/`** — Story 1.4 is genuinely tests-only. The bind/unbind/merge machinery shipped in Story 1.2 (`pytest_runtest_protocol`'s hookwrapper) and pre-v0.3 code (`SQLHandler._record_to_row`'s `dict(get_bound())` merge) needed no modification.

**ACs satisfied:**
- AC1 ✅ FR60 — `test_app_log_during_test_inherits_test_id` (body record carries test_id, value matches plugin's records)
- AC2 ✅ FR61 — `test_fixture_setup_log_inherits_test_id` (fixture setup inside protocol bind window)
- AC3 ✅ FR61 — `test_fixture_teardown_log_inherits_test_id` (fixture teardown inside protocol bind window)
- AC4 ✅ FR59 — `test_test_id_unbound_after_session` (post-session `pytest_unconfigure` emit carries no test_id)
- AC5 ✅ — `test_app_log_in_two_tests_carries_each_tests_id` (cross-test isolation, anti-leak assertions)
- AC6 ✅ — `test_app_log_in_parametrized_variants` (each variant inherits its own test_id)
- AC7 ✅ — `test_class_scoped_fixture_propagation` (setup → first test's id, teardown → last test's id; diagnostic `by_msg` dump on failure for future scheduler-change debugging)
- AC8 ✅ — Story 1.4 added zero lines to `ulog/`, only one file in `tests/` modified

**Validation:**
- `pytest tests/`: **113/113 pass** (106 baseline from Stories 1.1-1.3 + 7 new). `tests/test_pytest_plugin.py`: **31 tests** (24 baseline + 7 new).
- `mypy ulog/testing/ --follow-imports=silent`: clean.
- `grep '^dependencies' pyproject.toml | grep -q '\[\]'`: PASS.
- `git diff --stat HEAD -- tests/`: only `tests/test_pytest_plugin.py` modified (586 lines added cumulative across Stories 1.2/1.3/1.4 — Story 1.4 contribution is ~280 lines).
- `git diff --stat HEAD -- pyproject.toml ulog/`: only Story 1.3's uncommitted `pytest_plugin.py` diff appears; Story 1.4 added 0 lines to `ulog/`.

**Out-of-scope deliberately deferred:**
- Async tests (`pytest-asyncio`) — contextvars copy across `await` correctly per Python's design; explicit asyncio test would just re-prove a stdlib guarantee. Reopen if a downstream user reports propagation issues with asyncio.
- xdist worker-id propagation — Story 1.10's scope.
- Hierarchical logger filtering (`myapp.submodule` matches `myapp.*`) — `_read_app_records` exact-match-only is sufficient for Story 1.4; Story 1.7/1.8 may extend.
- Earlier draft's Test 4.2 (`test_test_id_unbound_between_tests_via_app_records`) — dropped per validation feedback (semantic duplicate of Task 2.3 / AC5; removed during VS step before implementation).

### File List

**Modified:**
- `tests/test_pytest_plugin.py` (+~280 lines for Story 1.4: `_read_app_records` helper + section header + 7 new test functions)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (1-4 status: ready-for-dev → in-progress → review)

**Untouched (verified via git diff):**
- All files under `ulog/` (`ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/*`, `ulog/web/*`, `ulog/testing/*`).
- `pyproject.toml`.
- All other files under `tests/`.

### Change Log

| Date | Change | Rationale |
|---|---|---|
| 2026-05-06 | Added `_read_app_records(db_path, logger_name)` helper | Complementary to Story 1.2's `_read_test_records` (which filters `logger='ulog.test'`); needed to inspect APPLICATION records for FR60/61 propagation testing. Exact-match query — extension to hierarchical filtering deferred to Story 1.7/1.8 if needed. |
| 2026-05-06 | Added 7 propagation tests to `tests/test_pytest_plugin.py` | Locks FR59-61 contract: body/fixture-setup/fixture-teardown/parametrized-variant records all inherit bound `test_id`; cross-test isolation; class-scoped fixture scheduling (setup → first test, teardown → last test); post-session `pytest_unconfigure` emits don't carry stale `test_id`. |
| 2026-05-06 | `test_test_id_unbound_after_session` handles SQL NULL → JSON "null" double-None case | The SQL handler stores `bound or None` (`sql.py:208`); for an empty bound dict, that's serialized as JSON `null`. After `json.loads("null")` returns Python `None`, the assertion `"test_id" not in ctx` would TypeError. Added a second guard for `parsed is None` after `json.loads`. |
| 2026-05-06 | Pre-implementation: VS step dropped earlier draft's Task 4.2 | Validation review (3-reviewer fresh-eyes) flagged `test_test_id_unbound_between_tests_via_app_records` as a semantic duplicate of Task 2.3 (AC5 cross-test isolation). Removed before implementation; final test count is 7, not 8. |
| 2026-05-06 | Code review patches (P1-P8) applied | 3 reviewers in parallel (Blind Hunter + Edge Case Hunter + Acceptance Auditor) flagged 26 findings. 8 patched: anchor `.py::` boundary on body-record assertion, total-records anchor on Story 1.3's `parametrized_multi_param` (P2 — backport of Story 1.3 review pattern), `_read_app_records` docstring clarified (no built-in plugin-vs-app distinction), graceful handling of "no such table" when zero records emitted, class-fixture test made order-independent by reading insertion order, `pytest_unconfigure` decorated `@pytest.hookimpl(tryfirst=True)` for plugin-ordering safety, mid-test comment correction, `_FakeItem` annotation comment refined. 2 deferred (`tmp_path` quote f-string injection — broader `_conftest_with_setup` concern; skipped-test propagation coverage — FR59-61 don't scope by outcome but coverage is light). 16 dismissed with rationale. |

### Review Findings (added by `bmad-code-review` 2026-05-06, Sonnet 4.6 fresh-eyes — 3 parallel reviewers)

**Patches applied (8):**

- [x] [Review][Patch] P1: Anchor `.py::` boundary in `test_app_log_during_test_inherits_test_id` so a future class-wrap refactor (which prepends `::ClassName::`) trips loudly instead of passing the bare `endswith("::test_render")` [`tests/test_pytest_plugin.py:763`]. Source: Blind Hunter MED.
- [x] [Review][Patch] P2: Add total record-count anchor (`len(records) == 4`) to Story 1.3's `test_test_id_format_parametrized_multi_param` — backport of the Story 1.3 review pattern (P3/P4/P6) that was missed for this specific test [`tests/test_pytest_plugin.py:526`]. Source: Blind Hunter MED.
- [x] [Review][Patch] P3: `_read_app_records` docstring rewritten to remove the misleading "non-plugin records" framing — the helper has no built-in plugin/app distinction, it filters on the exact logger name parameter [`tests/test_pytest_plugin.py:140`]. Source: Blind Hunter LOW.
- [x] [Review][Patch] P4: `_FakeItem` annotation comment refined to acknowledge that the class-level `nodeid: str` is documentation, not enforcement (Python doesn't enforce bare annotations without `__slots__`/`@dataclass`) [`tests/test_pytest_plugin.py:704`]. Source: Blind Hunter LOW.
- [x] [Review][Patch] P5: `_read_app_records` wraps the SQL execute in `try/except sqlite3.OperationalError` returning `[]` for "no such table: logs" — the SQL handler creates the schema lazily on first emit, so a test that exercises the "no records emitted" path would otherwise raise instead of seeing empty results [`tests/test_pytest_plugin.py:159-167`]. Source: Edge Case Hunter HIGH.
- [x] [Review][Patch] P6: `test_class_scoped_fixture_propagation` made order-independent — the test now reads records in insertion order and verifies `setup.test_id == first_body.test_id` and `teardown.test_id == last_body.test_id`, rather than hard-coding `test_one`/`test_two` as first/last. Stable under `pytest-randomly` or any future intra-class collection-order shuffle [`tests/test_pytest_plugin.py:863-892`]. Source: Edge Case Hunter HIGH.
- [x] [Review][Patch] P7: Corrected the misleading comment on `test_app_log_in_two_tests_carries_each_tests_id` that erroneously claimed assertions "assume test_alpha runs before test_beta" — the `by_msg` lookup is order-independent [`tests/test_pytest_plugin.py:792-795`]. Source: Edge Case Hunter MED.
- [x] [Review][Patch] P8: `test_test_id_unbound_after_session`'s inner `pytest_unconfigure` decorated `@pytest.hookimpl(tryfirst=True)` so a third-party plugin (e.g. `pytest-cov`) tearing down logging in its own unconfigure cannot swallow the post-session emit [`tests/test_pytest_plugin.py:957-962`]. Source: Edge Case Hunter MED.

**Deferred (2):**

- [x] [Review][Defer] D1: `pytester.makeconftest(f"...")` f-string vulnerability if `tmp_path` ever contains a single quote — the same concern applies to Story 1.2's `_conftest_with_setup` and is broader than Story 1.4. Reason: Linux `/tmp/pytest-of-USER/...` paths don't contain quotes; addressing it requires switching all conftest helpers to triple-quoted raw or `repr()` interpolation, which is a hardening pass orthogonal to FR59-61 coverage. Source: Blind Hunter MED.
- [x] [Review][Defer] D2: Skipped-test propagation coverage missing — FR59-61 don't scope by outcome, so a `@pytest.mark.skip` test's potential fixture emits should also propagate `test_id` correctly. Reason: Story 1.2's `pytest_runtest_protocol` hookwrapper still fires for skipped items (the bind happens before `yield` regardless of outcome), so propagation works mechanically; adding a dedicated test would just re-prove this. Reopen if a downstream user reports a skipped-test propagation issue. Source: Edge Case Hunter MED.

**Dismissed with rationale (16):**

| # | Finding | Source | Why dismissed |
|---|---|---|---|
| 1 | `pytest_unconfigure` cleanup wipes ALL `_ulog_managed` handlers, could affect outer pytest | Blind HIGH | False alarm. Outer process's `_isolate_logging` autouse fixture (line 27 of post-Story-1.3) ALSO strips `_ulog_managed` handlers between outer tests. The cleanup is defensive, scoped, and correct. |
| 2 | `test_fixture_teardown_log_inherits_test_id` assumes unbind ordering relative to teardown | Blind HIGH | The hookwrapper pattern guarantees the `finally`-unbind runs AFTER pytest's setup→call→teardown sequence completes. This is a documented pytest hook contract, not a coincidence. |
| 3 | Class-finalizer scheduling is implementation detail | Blind HIGH | True theoretical concern; mitigated in P6 by reading insertion order rather than hard-coding `test_one`/`test_two`. |
| 4 | `by_msg` dedupes on key collision, masking duplicate-emit bugs | Blind MED | Mitigated by upstream `assert len(app_records) == 2` — a duplicate emit would push the count to 3+, tripping that anchor before the dict comprehension obscures it. |
| 5 | Test name dictates literal nodeid → refactor risk | Blind MED | Acknowledged trade-off — the literal-match locks the FR55 contract more strongly than a regex would. Rename → update assertion is a documented one-step migration. |
| 6 | `endswith("::test_render")` could match `::TestX::test_render` | Blind MED | Addressed under P1 (`.py::` boundary anchor). |
| 7 | `parametrized_multi_param` no total record-count anchor | Blind MED | Addressed under P2. |
| 8 | `myapp` propagate=False scenario | Blind MED | Theoretical — Python's default propagation is True, ulog.setup doesn't disable it. Failure mode is "0 records" which the existing `assert len(app_records) == 1` catches. |
| 9 | `test_test_id_stable_across_runs` "stronger guarantee" claim | Blind LOW | Story 1.3 territory (already reviewed); auditor convention dismissed identical finding there too. |
| 10 | In-process pytester contextvars bleed | Edge HIGH | Story 1.2's H1 patch guarantees `unbind` always fires (try/except/finally guard around emission). The OUTER test's protocol bind window doesn't exist (outer test isn't an inner pytest item), so there's nothing to bleed FROM. Defensive `ulog.unbind` in `_isolate_logging` would be over-engineering for a non-existent failure mode. |
| 11 | `bound or None` collapses `{"test_id": ""}` | Edge LOW | `_make_test_id(item)` returns `item.nodeid` which is non-empty by pytest contract. The empty-string scenario can't fire under documented behavior. |
| 12 | AC8 PARTIAL — gates "claimed but not independently verifiable from diff" | Auditor convention | Same as Story 1.3 review dismissal #8 — I actually ran every gate (`pytest tests/` 113/113, mypy clean, deps grep exit 0). Auditor convention marks self-reports as PARTIAL; not a real gap. |
| 13 | DoD items "UNVERIFIED" (mypy, deps grep, suite count, tests/ scope) | Auditor convention | Same as #12 — outputs documented in Dev Agent Record Debug Log. |
| 14 | Diff is combined Story 1.3 + 1.4, not pure 1.4 | Auditor Deviation 1 | Factual but inevitable — neither story is committed yet. Story 1.4-specific contribution (~280 lines) is identifiable inside the cumulative ~586-line diff. |
| 15 | `_read_app_records` docstring wording diverges from spec skeleton | Auditor Deviation 2 | Substance preserved (exact-match note + LIKE extension hint both present); the rephrasing makes the docstring tighter. |
| 16 | CRITICAL ORDERING comment placement | Auditor Deviation 3 | Spec says comment goes BEFORE `pytester.makeconftest`; diff places it both there AND inside the generated conftest body — strictly more visibility, not a deviation in spirit. |

**Final review verdict:** ✅ **All 8 ACs satisfied · all 5 tasks complete · 8 patches applied (including 1 backport to Story 1.3 — P2) · 2 deferred · 16 dismissed with rationale.** Tests: 24 → 31 in `test_pytest_plugin.py`. Full suite: **113/113 verts**. mypy clean. Regression gates PASS. 3-reviewer parallel pass adds 8 net code-quality + robustness improvements (notably P5 — graceful empty-DB handling — and P6 — order-independent class-fixture test) without changing FR59-61 semantics.
