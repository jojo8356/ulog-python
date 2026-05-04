---
docType: prd
project_name: ulog-python
version: 0.3.0
date: 2026-05-04
author: jojo8356
status: draft v1
parent_prd: PRD-v0.2-storage-and-ui.md
---

# ULog v0.3 — Test integration

> Tests are the most important consumer of structured logs in any
> codebase. v0.3 adds a **pytest plugin** that emits structured
> "test session" events into ULog storage, plus a UI section that
> shows test pass/fail status alongside ordinary log records — so
> you can answer "what did this failing test log?" in two clicks
> instead of grepping CI output.

---

## 0. The 30-second pitch

When a CI pipeline fails, the standard workflow is:

1. Open the CI page.
2. Find the failing test.
3. Scroll up through 2000 lines of pytest noise looking for the
   relevant log lines.
4. Cross-reference the assertion error with what your code logged.

ULog v0.3 collapses that to:

1. `ulog-web ./logs.sqlite`.
2. Filter "Failed tests only".
3. Click the failing test → see ITS log records (records emitted
   between `pytest test_foo started` and `pytest test_foo failed`)
   PLUS the assertion error and traceback.

The trick: a `ulog.pytest_plugin` hooks pytest's `pytest_runtest_*`
lifecycle and emits structured records into ULog storage with a
`test_id` bound-context field. The UI groups records by `test_id`
and shows the pass/fail badge.

---

## 1. Vision

### 1.1 Why this exists

Modern test frameworks (pytest, unittest, Jest, …) all emit per-test
events to stdout, but they do it in their own ad-hoc format. Tools
like Allure, ReportPortal, and pytest-html try to bridge this — but
they all build a **separate** report format that doesn't speak the
same language as your application logs.

ULog is already the application's log store. v0.3 just teaches it
about test events: same DB, same query API, same UI. The first day
of using it: you stop tab-switching between your test report and your
log viewer.

### 1.2 What v0.3 isn't

- A test runner. We don't replace pytest/unittest. We listen.
- A test report aggregator. No history, no flake detection, no
  "compare to last run". Use Allure or pytest-watch for that.
- A test author tool. No fixtures, no parametrize helpers.
- An assertion library. We just record what pytest tells us.

### 1.3 Target user (carried + new)

- **Marco** (carried) — local dev. Runs `pytest` on his laptop;
  one test fails. Without v0.3 he hunts in scrollback. With v0.3 he
  opens `ulog-web ./logs.sqlite` and sees the test's records grouped
  in 2 clicks.
- **Lin** (carried) — pipeline integrator. CI uploads
  `logs.sqlite` as a build artefact. Triage-on-failure: open
  artefact in `ulog-web`, filter "Failed tests only".
- **Iza** (NEW) — test reviewer. Writes a fix, runs `pytest -k
  flaky_test --count=10` to nail down a flake. Without v0.3 she
  drowns in 10× the output. With v0.3 the UI groups the 10 runs
  side-by-side under the same `test_id` (with `iteration` field
  distinguishing them).

---

## 2. Scope (v0.3)

### 2.1 In scope

#### 2.1.1 pytest plugin

- A `ulog.pytest_plugin` module declared as a pytest entry-point.
  Auto-discovered by pytest without any config — installing
  `ulog[testing]` is enough.
- Hooks into:
  - `pytest_runtest_logstart(nodeid, location)` — emits a
    `test.started` INFO record with `test_id` bound-context.
  - `pytest_runtest_logfinish(nodeid, location)` — emits a
    `test.finished` record with the outcome and duration.
  - `pytest_runtest_makereport(item, call)` — captures
    pass/fail/skip/error verdict per phase (setup/call/teardown).
  - `pytest_collection_modifyitems` — tags each collected item with
    a stable `test_id` based on its nodeid + parametrize markers.
- Configurable via pytest CLI flags:
  - `--ulog-db PATH` — where to write (overrides whatever the
    application code's `setup()` chose).
  - `--ulog-disable` — opt out per run.

#### 2.1.2 Test event schema

Every test produces three records minimum (start, outcome, finish),
all with the same `test_id`:

```json
{"level":"INFO","msg":"test started","test_id":"tests/test_foo.py::test_bar","logger":"ulog.test"}
{"level":"INFO|ERROR","msg":"test passed|failed|skipped|errored","test_id":"...","outcome":"passed","duration_s":0.024,"logger":"ulog.test"}
{"level":"INFO","msg":"test finished","test_id":"..."}
```

On failure, an additional ERROR record:

```json
{"level":"ERROR","msg":"AssertionError: foo != bar","test_id":"...","exc":{"type":"AssertionError","msg":"...","tb":[...]}}
```

#### 2.1.3 Bound test_id propagation

When a test runs, the plugin pushes `test_id` onto the contextvars
stack via `ulog.bind(test_id=...)`. EVERY log record emitted DURING
that test (by application code, not just the plugin itself) inherits
the `test_id` field. So:

```python
def test_audio_render():
    log.info("rendering rom")  # → record has test_id="tests/test_audio.py::test_audio_render"
    assert renderer.render() == expected
```

The unbind happens in the `pytest_runtest_logfinish` hook, so
post-test code (other tests, fixtures' teardown) doesn't carry the
stale id.

#### 2.1.4 UI: Tests sidebar section

A new sidebar section above "Sectors" shows the test summary:

```
TESTS
☑ Show all          (412)
☐ Failed only       (3)
☐ Slowest top 10    (10)

▼ tests/test_foo.py
  ✓ test_bar              (1.2s)
  ✓ test_baz              (0.4s)
  ✗ test_quux             (0.8s) ← red badge
▼ tests/test_audio.py
  ✓ test_render           (12s)
```

Clicking a test name filters the record list to ONLY records with
that `test_id`. The badge color reflects the test's final outcome
(pass=green, fail=red, skip=yellow, error=red+icon).

#### 2.1.5 Detail-view "test context" panel

When viewing any record that has a `test_id` set, the detail panel
adds a "Test context" sub-section showing:

- Test name + file:line
- Outcome (pass/fail/skip/error) with badge
- Duration
- Setup/call/teardown phase (which phase failed, if any)
- Link "View all records for this test" (filters list)
- Link "View only ERROR/WARNING records for this test"

#### 2.1.6 `pytest --ulog-summary` post-run

After `pytest` finishes, an optional one-line summary printed to
stderr:

```
ulog: 412 tests, 409 passed, 3 failed, 0 skipped → ulog-web ./logs.sqlite to triage
```

Suppressed by `-q` / `--quiet`.

### 2.2 Explicit non-goals (deferred to v0.4+)

- **JUnit XML export**. Tests are stored in ULog format only;
  XML export for legacy CI tools is v0.4.
- **Flake detection**. No "ran 10 times, passed 7" stats. v0.5.
- **Test history across runs**. v0.3 ships single-run inspection.
  Historical merging is the v0.5 multi-file merge story.
- **unittest support**. v0.3 covers pytest only. unittest plugin in
  v0.4.
- **Coverage integration**. No "this line was hit by 3 tests"
  cross-reference. v0.5 vision.
- **Slow-test alerts**. Threshold-based notifications are out of
  scope.

---

## 3. Functional Requirements

### 3.1 Plugin auto-discovery

| FR | Description |
|---|---|
| FR51 | The plugin is registered via `[project.entry-points.pytest11]` in `pyproject.toml`, discoverable by pytest as soon as `pip install ulog[testing]` runs. |
| FR52 | The plugin is OFF by default unless either (a) `setup()` was called in the host's `conftest.py`, OR (b) `--ulog-db PATH` is passed on the pytest CLI. Otherwise pytest runs unaffected. |
| FR53 | `pytest --ulog-disable` short-circuits the plugin even when (a) or (b) hold — escape hatch for users who want the host setup but not test instrumentation. |

### 3.2 Test event recording

| FR | Description |
|---|---|
| FR54 | Each test emits at minimum 2 records: `test.started` (INFO) at logstart, `test.outcome` (INFO/ERROR depending on pass/fail) at logfinish. |
| FR55 | `test_id` is the pytest nodeid (`tests/test_foo.py::test_bar`) for non-parametrized tests, and `nodeid + parametrize_id` for parametrized (e.g. `test_foo[True-1]`). Stable across runs. |
| FR56 | Failures produce an ERROR record with full traceback (`exc.tb`). The traceback comes from `report.longrepr`. |
| FR57 | Test phases (setup/call/teardown) are recorded as `phase` field on the outcome record. A teardown failure emits a separate ERROR with `phase="teardown"`. |
| FR58 | Test duration (`duration_s`) is computed from `report.duration`. |

### 3.3 Bound-context propagation

| FR | Description |
|---|---|
| FR59 | Plugin pushes `test_id` via `ulog.bind(test_id=...)` at logstart, calls `ulog.unbind('test_id')` at logfinish. |
| FR60 | Records emitted by application code DURING the test inherit `test_id` automatically (no explicit propagation needed). |
| FR61 | Pytest fixtures' setup/teardown emit records with the fixture's owning test's `test_id` (the plugin scopes the bind to the entire `pytest_runtest_protocol` for that nodeid). |

### 3.4 UI rendering

| FR | Description |
|---|---|
| FR62 | New "Tests" sidebar section above "Sectors". Lists all collected tests grouped by file, with outcome badges. |
| FR63 | "Failed only" filter checkbox at the top of the section toggles `outcome IN ('failed', 'errored')`. |
| FR64 | "Slowest top 10" sorts by `duration_s DESC` limit 10 — useful for finding the latency tail. |
| FR65 | Click a test name filters records to that `test_id`. Persisted in URL query string. |
| FR66 | Detail view for a record with `test_id` shows a "Test context" panel with file:line, outcome, duration, phase. Two links: "all records for this test" + "errors+warnings for this test". |

### 3.5 CLI flags

| FR | Description |
|---|---|
| FR67 | `pytest --ulog-db PATH` overrides the destination DB; setup is auto-configured if no host setup exists. |
| FR68 | `pytest --ulog-disable` short-circuits the plugin entirely. |
| FR69 | `pytest --ulog-summary` prints the one-line stderr summary after the session (default ON; `-q` suppresses). |

---

## 4. Non-functional requirements

| NFR | Budget |
|---|---|
| NFR-PERF-20 | Plugin overhead < 5 ms per test (the bind + 2-3 record inserts on a batched SQL handler are cheap). |
| NFR-COMPAT-10 | Pytest 7.0+. xdist (parallel tests) supported via the SQL handler's batch queue. |
| NFR-DOC-10 | New `/docs/test-integration.md` page covering: plugin install, pytest CLI flags, schema, "find failed tests" worked example. |
| NFR-REL-10 | Plugin is opt-in by default — installing `ulog[testing]` MUST NOT change the behavior of `pytest` until the user passes a flag or configures setup. |
| NFR-PORT-10 | Linux + macOS + Windows. xdist on Windows is the trickiest case (file locking on SQLite); fall back to JSONL if xdist + sqlite combination is detected. |

---

## 5. API surface (sketch)

### 5.1 conftest.py recipe

```python
# Most users: just install + add a one-line setup in conftest
import ulog

def pytest_configure(config):
    ulog.setup(
        handlers=['sql'],
        sql_url='sqlite:///./tests-logs.sqlite',
    )
```

### 5.2 Programmatic test event API (advanced)

For users running tests outside pytest (custom runners, CI hooks), a
manual API:

```python
from ulog.testing import test_event

with test_event("custom_test_42") as ev:
    log.info("step 1")    # auto-bound test_id
    do_thing()
    ev.outcome("passed", duration_s=0.42)
```

### 5.3 CLI examples

```bash
# Most basic — full summary on stderr after the run
pytest

# Override DB location (host didn't call setup)
pytest --ulog-db ./mytests.sqlite

# Disable the plugin even when host setup exists
pytest --ulog-disable

# Open the UI on the captured logs
ulog-web ./tests-logs.sqlite
```

---

## 6. UI mockup (text)

```
TESTS                           [Show all] [Failed only ✗3] [Slowest 10]

▼ tests/test_audio.py (5)
  ✓ test_render_wav         12ms
  ✓ test_render_mp3         18ms
  ✗ test_render_alter_ego   850ms   ← click here
  ✓ test_loop_detection     34ms
  ⊘ test_legacy             skip

▼ tests/test_engine.py (8)
  ✓ test_detect_famitracker  4ms
  …

▶ tests/test_cli.py (12)
```

Detail view (record from a failing test):

```
ERROR  tests/test_audio.py::test_render_alter_ego
       AssertionError: PCM hash drift detected

       file: tests/test_audio.py:85
       phase: call
       duration: 850 ms
       test_id: tests/test_audio.py::test_render_alter_ego

       Test context ▼
         outcome: failed
         total records: 12
         [view all records for this test]
         [view errors+warnings only]

       Traceback:
         File "tests/test_audio.py", line 85, in test_render_alter_ego
           assert hash(pcm) == EXPECTED_HASH
       AssertionError
```

---

## 7. Roadmap continuation

- **v0.4** — unittest plugin + JUnit XML exporter.
- **v0.5** — multi-file merge (compare across runs/branches).
- **v0.6** — flake detection + history.
- **v1.0** — feature freeze + Stable classifier.

---

## 8. Open questions

1. **Capture stdout/stderr of tests?** pytest already captures via
   `capsys`. Should the plugin emit captured stdout as a `test.stdout`
   record? Lean: yes for v0.3, gated by `--ulog-capture-stdout` (off
   by default — can be VERY noisy).
2. **Treat test parameter IDs as a separate field?** Currently bundled
   into `test_id` (`test_foo[True-1]`). v0.4 may split into
   `test_id="...test_foo"` + `params={"flag":True,"n":1}` for
   filterable parameter values. v0.3 keeps the conservative
   nodeid-only form.
3. **xdist DB file locking**. SQLite WAL mode handles concurrent writes
   on the same file, but on NFS it's flaky. v0.3 prints a warning
   if xdist is detected + SQL handler points at NFS.
4. **CI-friendly timestamps**. Some CI capture systems strip
   ANSI/colour but want sub-second precision. JSON formatter already
   has it; ULog test plugin uses the JSON shape internally.

---

## 9. Definition of Done — v0.3

- [ ] `ulog/testing/__init__.py` + `ulog/testing/pytest_plugin.py`
       implementing all hooks above.
- [ ] Auto-discovered via `[project.entry-points.pytest11]`.
- [ ] `--ulog-db`, `--ulog-disable`, `--ulog-summary` flags.
- [ ] `test_event(...)` programmatic API for non-pytest runners.
- [ ] UI Tests sidebar section + detail-view test context panel.
- [ ] `/docs/test-integration.md` page.
- [ ] ≥ 25 new tests covering the plugin (use pytest's `pytester`
       fixture).
- [ ] xdist compatibility verified on Linux + macOS + Windows.
- [ ] Tag `v0.3.0` + push.
