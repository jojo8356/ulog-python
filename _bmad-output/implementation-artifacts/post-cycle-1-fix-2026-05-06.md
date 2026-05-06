# Post-cycle-1 fix — Test isolation under `--ulog-db`

**Date:** 2026-05-06
**Trigger:** Browser-QA preparation step of the Epic 1 retrospective
**Outcome:** 13 → 0 failures. Suite green under both pytest invocations. Story `1-12` filed and closed same day.
**Production code touched:** None.

---

## 1. How the regression was found (5 min)

After Epic 1 closed (11 stories shipped, retrospective done), the QA checklist for browser verification said:

```bash
# Step 0.A — generate a fixture DB to populate the viewer for QA
python3 -m pytest tests/ --ulog-db /tmp/ulog-tests.sqlite -v
```

The user ran it. The summary line at the bottom (FR69, Story 1.5) reported:

```
ulog: 180 tests, 167 passed, 13 failed, 0 skipped → ulog-web /tmp/ulog-tests.sqlite to triage
```

13 failures spread across 4 files: `test_context.py` (9), `test_handlers.py` (1), `test_test_event.py` (2), `test_web.py` (1). All assert on the **shape of `ulog.get_bound()`** or on **records WITHOUT `test_id`**.

## 2. Diagnosis (10 min)

Read one failure end-to-end:

```python
def test_bind_then_clear():
    ulog.bind(a=1, b=2)
    assert ulog.get_bound() == {"a": 1, "b": 2}   # FAIL: actually {"a":1,"b":2,"test_id":"tests/test_context.py::test_bind_then_clear"}
```

The extra key `test_id` was a nodeid string. That's exactly what Story 1.4's `pytest_runtest_protocol` wraps every test with:

```python
ulog.bind(test_id=_make_test_id(item))
try:
    yield
finally:
    ulog.unbind("test_id")
```

The plugin gate normally stays OFF (Story 1.5 only auto-configures when `--ulog-db` is set OR when a host `pytest_configure` calls `ulog.setup`). With `--ulog-db` on the command line, the gate flipped ON, so EVERY test in the suite ran inside a `bind(test_id=...)` window — including tests that probe `ulog.bind` semantics directly. Those tests assumed a clean ContextVar at the start; they got the plugin's bind instead.

**Root-cause confirmed in 3 reads:**
1. `ulog/testing/pytest_plugin.py::pytest_runtest_protocol` — bind/unbind window covers the whole test.
2. `ulog/testing/pytest_plugin.py::pytest_configure` — auto-setup branch fires under `--ulog-db`.
3. `tests/test_context.py::_isolate` — `ulog.clear()` runs at TEARDOWN only, never at SETUP. So the plugin's bind from `pytest_runtest_protocol` is in effect for the entire test body.

This was missed during Epic 1 because:
- CI runs `pytest tests/` without `--ulog-db` → plugin self-disables → no bind → tests pass.
- The plugin's own propagation tests use `pytester` (Story 1.4) — pytester's in-process pytest run has isolated ContextVar state, so the OUTER plugin's bind doesn't leak into the INNER pytester run. Those tests passed.

## 3. Fix design — three options weighed

| Option | What | Cost | Risk | Decision |
|---|---|---|---|---|
| **A** Document, don't fix | Add a "known limitation" note in `docs/test-integration.md` Troubleshooting | 5 min | Leaves real interaction unfixed; future epics' QA prep will hit the same issue | **rejected** |
| **B** Fix in test files | Add `ulog.clear()` at SETUP of each affected `_isolate` fixture | 30 min | Idempotent, no-op when plugin off, zero production touch | **chosen** |
| **C** Fix in plugin | Detect "tests that touch `ulog.bind` itself" and skip the plugin's bind | not feasible without explicit tagging | Intrusive; cannot detect cleanly | **rejected** |

Option B is the right scope because the bug is in the **test fixtures' isolation contract**, not in the plugin or the bind primitive. Production behavior is correct under both invocations.

## 4. Patch — uniform pattern across 4 files

Same diff applied to `_isolate` in `test_context.py`, `test_handlers.py`, `test_test_event.py`, `test_web.py`:

```diff
 @pytest.fixture(autouse=True)
 def _isolate():
+    """Clear bound state at SETUP and teardown.
+
+    Setup-side clear is required so an OUTER pytest run with `--ulog-db`
+    (which binds test_id=<nodeid> for each test via pytest_runtest_protocol)
+    does not leak its bind into assertions on get_bound() shape or records
+    WITHOUT test_id.
+    """
+    ulog.clear()
     yield
     # ... existing teardown logic + ulog.clear() ...
```

Plus a one-line edit in `test_web.py::sqlite_fixture` to declare an explicit dependency on `_isolate` (guarantees setup-time ordering across pytest releases):

```diff
-def sqlite_fixture(tmp_path) -> Path:
+def sqlite_fixture(_isolate, tmp_path) -> Path:
```

**Why the docstring matters more than the line of code**: the retrospective's "lessons learned" already flagged "test fixtures with cross-story reuse benefit from locked docstrings explaining WHY each isolation step exists". A future maintainer doing dead-code cleanup might delete the setup-side `ulog.clear()` as redundant ("we already clear at teardown"). The docstring is the lock that prevents that.

## 5. Verification — both invocations green

```bash
$ python3 -m pytest tests/
============================= 180 passed in 4.75s ==============================

$ python3 -m pytest tests/ --ulog-db /tmp/ulog-tests-fix.sqlite
============================= 180 passed in 4.46s ==============================
ulog: 180 tests, 180 passed, 0 failed, 0 skipped → ulog-web /tmp/ulog-tests-fix.sqlite to triage
```

Same count, same outcomes, no flakes. The summary line itself (FR69) is the regression sentinel for this fix — if anyone re-introduces a leak, the summary's failed count will spike under `--ulog-db`.

## 6. Story trail

Filed as **Story 1.12 — `1-12-test-isolation-when-plugin-active.md`** in `_bmad-output/implementation-artifacts/`. Marked `done` immediately because:

- Test-only patch (no production touch).
- Deterministic 1-line fix replicated across 4 files.
- Trivial regression coverage (the suite itself, run under both invocations).
- No CR cycle: zero ambiguity, zero production surface.

`sprint-status.yaml` updated. Epic 1 still marked `done` (the patch is documented as a post-retro addendum, not a re-opening).

## 7. Lessons captured for Epic 2+

1. **Run pytest WITH `--ulog-db` as part of every epic's CI matrix.** This regression would have been caught by Story 1.5's own auto-setup if the project dogfooded its own plugin during CI. Action: add a CI step in Epic 7 (consolidation/release) that runs `pytest tests/ --ulog-db /tmp/ci-fixture.sqlite` and asserts a non-empty fixture DB + 0 failures. Cost: 1 CI line.
2. **Setup-side state hygiene is part of the autouse-fixture contract**, not a "nice to have". Future epics that introduce ContextVars or process-global state should extend `_isolate` to clear them at setup AND teardown by default.
3. **Locked docstrings on isolation fixtures**: any line in a test fixture that exists "because of an interaction" should have a 1-line WHY comment so it survives refactor passes.
4. **Browser-QA preparation is a real verification step** — the user found this bug because the QA checklist asked them to run the suite WITH the plugin active. Future epics' QA checklists should keep this pattern.

These are appended to the Epic 1 retrospective lessons; no separate retro doc needed.
