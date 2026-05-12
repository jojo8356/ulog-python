---
docType: epic
epic_num: 1
title: v0.3 — Test integration
project_name: ulog-python
source: extracted from _bmad-output/planning-artifacts/epics.md (lines 543-779)
status: done
shipped: v0.3
stories_canonical: 11
stories_added_via_correct_course: 2
retrospective: _bmad-output/implementation-artifacts/epic-1-retro-2026-05-06.md
---

# Epic 1: v0.3 — Test integration

A pytest user installs `ulog[testing]` and immediately gets every test's lifecycle recorded as structured ulog records, with `test_id` propagated to every application log emitted during the test. The viewer adds a "Tests" sidebar with quick filters and a detail-view "Test context" panel.

### Story 1.1: Pytest plugin entry-point registration

As a pytest user,
I want `ulog[testing]` to register the pytest plugin via the standard pytest11 entry-point,
So that `pip install ulog[testing]` followed by `pytest` auto-discovers the plugin without manual config.

**Acceptance Criteria:**

**Given** a fresh project with `pip install ulog[testing]`
**When** pytest is invoked
**Then** the plugin module `ulog.testing.pytest_plugin` is loaded automatically
**And** `pytest --trace-config` lists `ulog` in the registered plugins.

**Given** the plugin is loaded but no host `setup()` was called and no `--ulog-db` was passed
**When** pytest runs the test suite
**Then** the plugin is OFF — no `test.started` records are emitted (FR52).

**Given** the plugin is enabled (host `setup()` or `--ulog-db`)
**When** the user passes `--ulog-disable`
**Then** the plugin short-circuits — no `test.started` records emitted (FR53).

---

### Story 1.2: Test event recording (start, outcome, finish)

As a pytest user,
I want every test to emit at least 2 structured records (`test.started`, `test.outcome`) plus an ERROR record on failure with full traceback,
So that I can reconstruct what happened during any test run from the log archive alone.

**Acceptance Criteria:**

**Given** a test that passes
**When** the test runs
**Then** an INFO record `msg="test started"` is emitted at logstart with `test_id` bound
**And** an INFO record `msg="test passed"` with `outcome="passed"`, `duration_s=<float>`, `phase="call"` is emitted at logfinish (FR54, FR58).

**Given** a test that fails on assertion
**When** the test runs
**Then** an ERROR record is emitted with `exc.type`, `exc.msg`, `exc.tb` populated from `report.longrepr` (FR56).

**Given** a teardown failure
**When** pytest finalizes the test
**Then** a separate ERROR record with `phase="teardown"` is emitted (FR57).

---

### Story 1.3: Test ID stability for parametrized tests

As a pytest user,
I want `test_id` to be stable across runs and uniquely identify parametrized variants,
So that filtering by `test_id` returns the same set of records on every run of the same test.

**Acceptance Criteria:**

**Given** a non-parametrized test `tests/test_foo.py::test_bar`
**When** the plugin records its lifecycle
**Then** `test_id == "tests/test_foo.py::test_bar"` (FR55).

**Given** a parametrized test `test_foo[True-1]`
**When** the plugin records its lifecycle
**Then** `test_id == "tests/test_foo.py::test_foo[True-1]"` (FR55).

**Given** the same test run twice
**When** records from both runs are inspected
**Then** the `test_id` values are identical.

---

### Story 1.4: Bound-context propagation of test_id

As a developer instrumenting application code,
I want every `log.info()` / `log.error()` emitted DURING a test to inherit `test_id` automatically,
So that I can filter the viewer to "all records this test produced" without instrumenting each log call.

**Acceptance Criteria:**

**Given** a test `test_audio_render` that calls `log.info("rendering rom")`
**When** the test runs with the plugin enabled
**Then** the application's INFO record carries `test_id="tests/test_audio.py::test_audio_render"` (FR60).

**Given** a fixture's setup or teardown emits a record
**When** the fixture is scoped to a specific test
**Then** the record carries that test's `test_id` (FR61).

**Given** the test has finished
**When** post-test code (other tests' fixtures) emits records
**Then** records do NOT carry the previous `test_id` (unbind happens at logfinish — FR59).

---

### Story 1.5: Pytest CLI flags

As a pytest user,
I want `--ulog-db PATH`, `--ulog-disable`, and `--ulog-summary` flags exposed via pytest's standard option machinery,
So that I can override DB destination, opt out, or get a summary line without modifying conftest.

**Acceptance Criteria:**

**Given** no `setup()` was called by the host
**When** `pytest --ulog-db ./mytests.sqlite` is invoked
**Then** the plugin auto-configures `ulog.setup(handlers=['sql'], sql_url=...)` to that path (FR67).

**Given** the plugin is enabled
**When** `pytest --ulog-disable` is invoked
**Then** no records are emitted by the plugin (FR68).

**Given** `pytest --ulog-summary` (default ON)
**When** the session ends
**Then** a one-line summary appears on stderr: `ulog: N tests, X passed, Y failed, Z skipped → ulog-web ./logs.sqlite to triage` (FR69).

**Given** `pytest -q` is used
**When** the session ends
**Then** the summary line is suppressed (FR69).

---

### Story 1.6: Tests sidebar — list + Failed-only + Slowest-top-10

As a pytest viewer user,
I want a "Tests" sidebar section above "Sectors" listing collected tests grouped by file, with quick filters for "Failed only" and "Slowest top 10",
So that I can triage failures or latency outliers in two clicks.

**Acceptance Criteria:**

**Given** the loaded log file contains test records
**When** the viewer renders `/`
**Then** a "TESTS" sidebar section appears above "Sectors" listing tests grouped by file with outcome badge (✓/✗/⊘) and duration (FR62).

**Given** "Failed only" is ticked
**When** the page reloads
**Then** the records list filters to `outcome IN ('failed', 'errored')` (FR63).

**Given** "Slowest top 10" is ticked
**When** the page reloads
**Then** the records list shows tests sorted by `duration_s DESC LIMIT 10` (FR64).

---

### Story 1.7: Click test name to filter records by test_id

As a pytest viewer user,
I want clicking a test name in the sidebar to filter the record list to that `test_id`, with the filter persisted in the URL,
So that I can share the URL of a specific failing test's records with a colleague.

**Acceptance Criteria:**

**Given** the Tests sidebar is rendered
**When** the user clicks `test_render_alter_ego`
**Then** the record list filters to `test_id="tests/test_audio.py::test_render_alter_ego"`
**And** the URL contains `?test_id=tests%2Ftest_audio.py%3A%3Atest_render_alter_ego` (FR65).

**Given** the URL is opened in a fresh tab
**When** the page renders
**Then** the same filter is applied (URL is the source of truth).

---

### Story 1.8: Detail-view "Test context" panel

As a pytest viewer user inspecting a single record,
I want the detail page to show a "Test context" sub-section for any record that has `test_id`,
So that I can jump from one record to all records for that test or to errors+warnings only.

**Acceptance Criteria:**

**Given** a record's detail view (`/r/<id>/`) where `test_id` is set
**When** the page renders
**Then** a "Test context" panel shows: file:line, outcome badge, duration, phase, total records count, "view all records for this test" link, "view errors+warnings only" link (FR66).

**Given** a record with no `test_id`
**When** the detail view renders
**Then** the "Test context" panel is absent.

---

### Story 1.9: Programmatic `test_event()` API for non-pytest runners

As a developer running tests via a custom runner (not pytest),
I want a programmatic `test_event(name)` context manager exported from `ulog.testing`,
So that I can record test lifecycle events from any test framework without relying on pytest hooks.

**Acceptance Criteria:**

**Given** `from ulog.testing import test_event`
**When** the user wraps test code: `with test_event("custom_test_42") as ev: ... ev.outcome("passed", duration_s=0.42)`
**Then** the same 2-3 records are emitted as for a pytest test (FR54-58).

**Given** the user does not call `ev.outcome(...)` before exiting the context
**When** the context exits
**Then** an `outcome="errored"` record is auto-emitted with the exception info if the block raised, or `outcome="passed"` if no exception.

**Given** the `ulog.testing` sub-package is installed
**When** `from ulog.testing import test_event, replay_records, TestSession` is invoked
**Then** all three names resolve (Gap G5 stable signature anchor).

---

### Story 1.10: xdist + Windows + NFS edge cases

As a CI integrator running tests with `pytest-xdist` on Windows / NFS,
I want the plugin to detect xdist + SQLite + NFS combinations and fall back to JSONL,
So that I don't hit SQLite locking issues silently corrupting the test log.

**Acceptance Criteria:**

**Given** xdist is detected (worker env vars present) AND the SQL handler points at a path on NFS
**When** the plugin initializes
**Then** the SQL handler is silently swapped for JSONL on the same path stem
**And** a warning is printed to stderr (NFR-PORT-10).

**Given** xdist is detected on a local filesystem
**When** the plugin initializes
**Then** SQLite WAL mode is enabled and writes proceed normally.

---

### Story 1.11: Doc page `/docs/test-integration.md`

As a new pytest+ulog user,
I want a doc page covering plugin install, CLI flags, schema, and a "find failed tests" worked example,
So that I can adopt the plugin without reading the PRD.

**Acceptance Criteria:**

**Given** the viewer is running
**When** the user navigates to `/docs/test-integration/`
**Then** the page renders covering: install (`pip install ulog[testing]`), CLI flags (`--ulog-db`, `--ulog-disable`, `--ulog-summary`), test event schema, "find failed tests" worked example (NFR-DOC-10).

**Given** the page is markdown source
**When** the in-house renderer processes it
**Then** it renders without syntax errors (no markdown-it-py dependency).

---

## Annex — Stories added via correct-course (post-retrospective patches)

Two regressions were surfaced during the retrospective QA pass (2026-05-06) and patched in-cycle. They are not part of the canonical 1.1–1.11 PRD scope; full specs live in their own implementation artifacts.

### Story 1.12: Test isolation when plugin is active

Discovered when running `pytest tests/ --ulog-db /tmp/ulog-tests.sqlite` to generate a fixture DB — 13 unrelated tests failed because the plugin's `pytest_runtest_protocol` bind of `test_id` leaked into tests that probe `ulog.bind()` semantics or assert on records WITHOUT `test_id`. Plugin scope (FR59 unbind contract) tightened so the bind/unbind cycle no longer pollutes tests that introspect the bound context.

→ Spec: https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/implementation-artifacts/1-12-test-isolation-when-plugin-active.md

### Story 1.13: SQL handler — guard against CREATE TABLE race under concurrent bootstrap

Surfaced when running the suite under `pytest -n auto --ulog-db /tmp/foo.sqlite` (real `pytest-xdist`, post-1.12 verification). 4 worker processes bootstrap their own `SQLHandler` against the same shared DB → TOCTOU race between `inspect.get_table_names()` and `metadata.create_all()` → `OperationalError("table 'logs' already exists")` for the losers. Story 1.10 had only mocked the xdist paths; this story protects against concurrent **schema bootstrap** (Story 1.10 protected only concurrent writes via WAL).

→ Spec: https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/implementation-artifacts/1-13-sql-handler-create-table-race.md

---

## References

- **Retrospective:** https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/implementation-artifacts/epic-1-retro-2026-05-06.md
- **Source PRD:** https://github.com/jojo8356/ulog-python/blob/main/docs/prds/PRD-v0.3-test-integration.md
- **Architecture:** https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/planning-artifacts/architecture.md
- **Monolithic epics file:** https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/planning-artifacts/epics.md — Epic 1 lives at lines 543–779
