# Story 1.6: Tests sidebar — list + Failed-only + Slowest-top-10

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**Epic:** 1 — v0.3 Test integration
**Story key:** `1-6-tests-sidebar-list-failed-only-slowest-top-10`
**Implements:** FR62, FR63, FR64 (PRD-v0.3 §3.4)
**Source:** `docs/prds/PRD-v0.3-test-integration.md` §3.4 + §2.1.4 (UI mockup §6), `_bmad-output/planning-artifacts/architecture.md`, `_bmad-output/planning-artifacts/epics.md` Story 1.6
**Built on:** Stories 1.1-1.5 (the plugin produces `logger='ulog.test'` records with `context.outcome` / `context.duration_s` / `context.test_id` / `context.phase` populated; Story 1.5 ensures records actually land in a DB via auto-setup or host setup), pre-v0.3 viewer (Django `list_view` + `list.html` already render Sectors/Files/Levels sidebar)
**Foundation for:** Story 1.7 (clicking a test name in this sidebar applies a `?test_id=...` URL filter), Story 1.8 (record detail's "Test context" panel reads the same per-test data this story aggregates)

---

## Story

As a **pytest viewer user**,
I want **a "TESTS" sidebar section above "Sectors" that lists collected tests grouped by file with outcome badges (✓/✗/⊘) and duration, plus quick-filter checkboxes for "Failed only" and "Slowest top 10"**,
so that **I can triage failures or latency outliers in two clicks instead of grepping through CI scrollback**.

## Acceptance Criteria

### AC1 — TESTS section renders above Sectors when test records exist (FR62)

**Given** the loaded log file contains at least one record with `logger='ulog.test'` AND `context.outcome` set
**When** the user opens `/`
**Then** the left sidebar contains a new section titled `TESTS` positioned ABOVE the existing `Sectors` section
**And** that section lists every distinct `test_id` found in the records, grouped by file (the prefix before `::` in the nodeid), one collapsible group per file
**And** each test row shows: the test name (the portion AFTER the last `::`), an outcome badge (✓ green for passed / ✗ red for failed / ⊘ amber for skipped / 🔥 red-with-icon for errored), and a duration in milliseconds (rounded to integer ms when ≥ 1ms, or `<1ms` otherwise).

### AC2 — TESTS section is HIDDEN when no test records exist

**Given** the loaded log file contains zero records with `logger='ulog.test'`
**When** the user opens `/`
**Then** the TESTS section is NOT rendered at all (no empty heading, no empty list).

This is the regression guard for non-test logs — pre-v0.3 users opening their app's `prod.sqlite` should see exactly the same UI as before (Sectors / Files / Levels / Bound, no extra empty section).

### AC3 — "Failed only" checkbox filters records list (FR63)

**Given** the TESTS section is visible (test records exist)
**When** the user ticks the "Failed only" checkbox at the top of the TESTS section and submits the filter form
**Then** the URL acquires the query parameter `failed_only=1`
**And** the records list is filtered to ONLY records whose `context.outcome` is in `{"failed", "errored"}` — both the plugin's outcome records (`logger='ulog.test'` with `context.outcome IN ('failed','errored')`) AND any application records bound to a test_id whose outcome is failed/errored.

For the v0.3 implementation simplicity, "Failed only" applies to plugin records only (those with `logger='ulog.test'`). The cross-cut "all records bound to a failed test_id" is a Story 1.7 enhancement; this story limits the filter to direct outcome-record matches.

### AC4 — "Slowest top 10" checkbox sorts and limits records (FR64)

**Given** the TESTS section is visible
**When** the user ticks the "Slowest top 10" checkbox and submits
**Then** the URL acquires `slowest_only=1`
**And** the records list shows the 10 plugin outcome records (`logger='ulog.test'` with `context.outcome` in passed/failed/errored — NOT skipped, since skipped tests have `duration_s=0` by pytest convention) sorted by `context.duration_s DESC` and limited to 10 rows.

If fewer than 10 such records exist, ALL of them appear, in slowest-first order.

### AC5 — "Failed only" and "Slowest top 10" can combine

**Given** both checkboxes are ticked simultaneously
**When** the user submits the form
**Then** the URL contains both `failed_only=1` AND `slowest_only=1`
**And** the records list shows the 10 SLOWEST FAILED tests (intersection: `outcome IN ('failed','errored')` AND ordered by `duration_s DESC LIMIT 10`).

### AC6 — Outcome badge mapping matches PRD §6 mockup

**Given** any test row in the TESTS sidebar
**When** rendered
**Then** the badge maps the `context.outcome` field of that test's outcome record to the visual symbol per the PRD §6 mockup:

| outcome | badge | color |
|---|---|---|
| `passed` | `✓` | green |
| `failed` | `✗` | red |
| `errored` | `🔥` (or `✗` with red flame styling — implementer's choice, document in code) | red |
| `skipped` | `⊘` | amber/yellow |

Badges use the existing Tailwind class palette already in `list.html` (e.g. `text-green-600`, `text-red-600`, `text-amber-500`); do NOT introduce custom CSS or inline styles. Lucide icons (already imported via `django-lucide`) MAY be used for the icons but plain UTF-8 glyphs are also acceptable.

### AC7 — Test rows are ordered by file path then test name within each file group

**Given** multiple tests exist in multiple files
**When** the TESTS section renders
**Then** files are sorted alphabetically by path, and tests within each file are sorted alphabetically by the post-`::` name (parametrized variants of the same test cluster together by virtue of the bracket suffix sort).

### AC8 — Duration display uses milliseconds, not seconds

**Given** a test with `context.duration_s = 0.024` (24 ms) on its outcome record
**When** the TESTS sidebar renders that row
**Then** the duration shows as `24ms` (NOT `0.024s`, NOT `0.024`, NOT `24.0ms`).

For very fast tests (`duration_s < 0.001`), display `<1ms`. For long tests (`duration_s >= 1.0`), display in seconds with one decimal (e.g. `12.0s` or `1.2s`) — the PRD §6 mockup uses `12s` form and the rendered form should match.

### AC9 — Existing filters compose with the new ones

**Given** any combination of pre-existing filters (level / logger / file / search / bound / time range)
**When** combined with `failed_only` and/or `slowest_only`
**Then** all filters apply jointly via AND (the new filters are additional `WHERE` clauses, not exclusive replacements).

### AC10 — Frozen-invariant + regression-gate compliance

**Given** Story 1.6's changes
**When** the standard regression checks run
**Then**:
  - `dependencies = []` in `pyproject.toml` is unchanged (NFR-DEP-50 / SC4).
  - `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/testing/` ALL UNCHANGED. Story 1.6 lives entirely in `ulog/web/` (specifically `viewer/adapters.py`, `viewer/views.py`, `templates/ulog/list.html`) and `tests/` (specifically `tests/test_web.py` — extending the existing test module, not creating a new one).
  - All 122 existing tests still pass (no regressions in plugin or web).

---

## Tasks / Subtasks

- [ ] **Task 1** — Extend `Filters` and `QueryResult` dataclasses (AC3, AC4, AC9)
  - [ ] 1.1 In `ulog/web/viewer/adapters.py`, add two new fields to `Filters` (around line 38):

    ```python
    failed_only: bool = False  # FR63 — Story 1.6
    slowest_only: bool = False  # FR64 — Story 1.6
    ```

    Update `is_empty()` to include them in the "all empty" check:

    ```python
    def is_empty(self) -> bool:
        return (
            not self.levels and not self.loggers and not self.files
            and not self.search and not self.bound
            and not self.ts_from and not self.ts_to
            and not self.failed_only and not self.slowest_only
        )
    ```

  - [ ] 1.2 Add a new field to `QueryResult` (around line 58) for the test summary:

    ```python
    test_summary: list["TestSummaryRow"] = field(default_factory=list)  # Story 1.6 — populated only when test records exist
    ```

    And introduce a small frozen dataclass right above `QueryResult`:

    ```python
    @dataclass(frozen=True)
    class TestSummaryRow:
        """One row in the TESTS sidebar (Story 1.6, FR62)."""
        test_id: str         # e.g. "tests/test_audio.py::test_render_alter_ego[44100]"
        file: str            # the part before `::` — e.g. "tests/test_audio.py"
        name: str            # the part after the last `::` — e.g. "test_render_alter_ego[44100]"
        outcome: str         # "passed" / "failed" / "skipped" / "errored"
        duration_s: float    # raw seconds; template formats to ms/s
    ```

- [ ] **Task 2** — Build the test summary in `SQLiteAdapter.query` (AC1, AC7)
  - [ ] 2.1 In `SQLiteAdapter.query` (around line 153), after computing `level_counts` (line 196), call a new helper `_build_test_summary(conn)` and assign it to the result:

    ```python
    test_summary = self._build_test_summary(conn)
    ```

    Return it in the `QueryResult(...)` constructor.

  - [ ] 2.2 Add `_build_test_summary(self, conn)` method on `SQLiteAdapter`:

    ```python
    def _build_test_summary(self, conn) -> list[TestSummaryRow]:
        """Aggregate one row per distinct test_id from the plugin's outcome records.

        We pick the OUTCOME record (the one whose msg starts with "test " and
        whose context.outcome is set) — NOT the "test started" record, which
        has no outcome/duration. We use SQLAlchemy's JSON path syntax for the
        SQLite dialect: `json_extract(context, '$.test_id')`.
        """
        from sqlalchemy import select, func, text

        t = self._table
        # Pull every plugin outcome record. We can't easily group by test_id
        # in pure SQL because we want the LATEST outcome per test_id (in
        # case a test ran multiple times under a rerun plugin). Sort by id
        # ASC and let Python pick the last seen — small table size makes
        # this cheap.
        sql = text(
            f"SELECT json_extract(context, '$.test_id') AS test_id, "
            f"       json_extract(context, '$.outcome') AS outcome, "
            f"       json_extract(context, '$.duration_s') AS duration_s "
            f"FROM {self._table_name} "
            f"WHERE logger = 'ulog.test' "
            f"  AND json_extract(context, '$.outcome') IS NOT NULL "
            f"ORDER BY id ASC"
        )
        latest_by_test_id: dict[str, tuple[str, float]] = {}
        for row in conn.execute(sql):
            tid = row.test_id
            outcome = row.outcome
            duration_s = float(row.duration_s) if row.duration_s is not None else 0.0
            if tid:
                latest_by_test_id[tid] = (outcome, duration_s)

        rows = []
        for tid, (outcome, duration_s) in latest_by_test_id.items():
            file, _, name = tid.partition("::")
            if not name:  # malformed nodeid — skip
                continue
            rows.append(TestSummaryRow(
                test_id=tid, file=file, name=name,
                outcome=outcome, duration_s=duration_s,
            ))
        # AC7: sort by file then by name (alphabetical within file)
        rows.sort(key=lambda r: (r.file, r.name))
        return rows
    ```

  - [ ] 2.3 The `JSONLAdapter` and `CSVAdapter` paths (lines 268-330) MUST also return `test_summary=[]` (empty) — they don't need full implementation in v0.3. Add a `test_summary=[]` to both `QueryResult(...)` calls in those adapters as a placeholder. Story 1.10 may extend; not this story's scope.

- [ ] **Task 3** — Apply `failed_only` and `slowest_only` filters in `SQLiteAdapter._base_filters` (AC3, AC4, AC5)
  - [ ] 3.1 Extend `_base_filters` (around line 124) to add WHERE clauses when the new fields are set:

    ```python
    if filters.failed_only:
        # FR63 — limit to plugin outcome records flagged failed/errored
        clauses.append(
            and_(
                t.c.logger == "ulog.test",
                func.json_extract(t.c.context, "$.outcome").in_(
                    ("failed", "errored")
                ),
            )
        )
    ```

    Note: `failed_only` is restrictive — it filters the records LIST (not just the test summary). It does NOT scope to "all records bound to a failed test_id" — that's Story 1.7 territory.

  - [ ] 3.2 For `slowest_only`, the filter's role is BOTH a WHERE clause AND an ORDER BY override. Add a parallel handling in `query()` (around line 153, before pagination):

    ```python
    if filters.slowest_only:
        # FR64 — restrict to plugin outcome records with a non-skipped outcome
        # AND change the ordering to duration_s DESC. The page_size is
        # treated as a CAP at 10 here.
        # Note: the WHERE clause is added in _base_filters via a parallel branch;
        # the ORDER BY override happens here.
        ...
    ```

    Implementation detail: a clean approach is to handle `slowest_only`'s WHERE (logger='ulog.test' AND duration_s IS NOT NULL AND outcome != 'skipped') in `_base_filters`, and the ORDER BY + LIMIT 10 directly in the `query()` method overriding the default `id DESC` ordering. Document this split in code comments so a future reader sees both halves.

  - [ ] 3.3 When both `failed_only` AND `slowest_only` are set (AC5), the filters AND together: WHERE clauses combine via the existing list-of-clauses pattern; the ORDER BY override applies only when `slowest_only` is set.

- [ ] **Task 4** — Wire query string parsing in `views.py` (AC3, AC4, AC5, AC9)
  - [ ] 4.1 In `_parse_filters` (around line 29 of `views.py`), add:

    ```python
    failed_only=qs.get("failed_only", "").strip() in ("1", "true", "on"),
    slowest_only=qs.get("slowest_only", "").strip() in ("1", "true", "on"),
    ```

    The "1/true/on" tuple matches HTML form-checkbox conventions (`<input type="checkbox" value="1">` submits `on` by default; explicit `value="1"` submits `1`).

  - [ ] 4.2 In `list_view` (around line 54), pass `test_summary` to the template:

    ```python
    "test_summary": result.test_summary,
    ```

    in the `ctx` dict.

  - [ ] 4.3 Also update `api_records` (around line 98) to expose `test_summary` in the JSON response — minor parallel for the JS-driven UI consumers (FR34); convert each `TestSummaryRow` to a dict.

- [ ] **Task 5** — Render the TESTS section in `list.html` (AC1, AC2, AC3, AC4, AC6, AC7, AC8)
  - [ ] 5.1 In `ulog/web/templates/ulog/list.html`, BEFORE the existing Sectors block (line 41 in the post-Story-1.5 file), add the TESTS section:

    ```django
    {# TESTS sidebar (Story 1.6 — FR62-64). Hidden when no test records exist. #}
    {% if test_summary %}
      <div>
        <h3 class="font-semibold mb-2 text-slate-700 dark:text-slate-300 flex items-center gap-1.5"
            title="Tests collected from `logger='ulog.test'` records. Click a test name (Story 1.7) or use the quick filters below.">
          {% lucide "flask-conical" size=14 %}
          <span>Tests</span>
        </h3>
        {# Quick filters — FR63 + FR64 #}
        <div class="space-y-1 mb-2">
          <label class="flex items-center gap-2 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 px-1 rounded">
            <input type="checkbox" name="failed_only" value="1"
                   {% if filters.failed_only %}checked{% endif %}
                   class="rounded text-red-600 focus:ring-red-500 flex-shrink-0">
            <span class="font-mono text-xs flex-1">Failed only</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 px-1 rounded">
            <input type="checkbox" name="slowest_only" value="1"
                   {% if filters.slowest_only %}checked{% endif %}
                   class="rounded text-amber-600 focus:ring-amber-500 flex-shrink-0">
            <span class="font-mono text-xs flex-1">Slowest top 10</span>
          </label>
        </div>
        {# Test list grouped by file. Tests are pre-sorted by adapter (AC7). #}
        <div class="space-y-1 max-h-60 overflow-y-auto">
          {% regroup test_summary by file as tests_by_file %}
          {% for file_group in tests_by_file %}
            <details open class="text-xs">
              <summary class="font-mono text-slate-600 dark:text-slate-400 cursor-pointer truncate"
                       title="{{ file_group.grouper }}">
                {{ file_group.grouper }}
              </summary>
              <ul class="ml-3 mt-1 space-y-0.5">
                {% for t in file_group.list %}
                  <li class="flex items-center gap-2 px-1">
                    {% if t.outcome == "passed" %}
                      <span class="text-green-600 dark:text-green-400" title="passed">✓</span>
                    {% elif t.outcome == "failed" %}
                      <span class="text-red-600 dark:text-red-400" title="failed">✗</span>
                    {% elif t.outcome == "errored" %}
                      <span class="text-red-600 dark:text-red-400" title="errored">🔥</span>
                    {% elif t.outcome == "skipped" %}
                      <span class="text-amber-500 dark:text-amber-400" title="skipped">⊘</span>
                    {% else %}
                      <span class="text-slate-400" title="{{ t.outcome }}">?</span>
                    {% endif %}
                    <span class="font-mono flex-1 min-w-0 truncate" title="{{ t.test_id }}">
                      {{ t.name }}
                    </span>
                    <span class="ml-2 text-slate-500 dark:text-slate-400 tabular-nums text-xs flex-shrink-0">
                      {% include "ulog/_test_duration.html" with seconds=t.duration_s %}
                    </span>
                  </li>
                {% endfor %}
              </ul>
            </details>
          {% endfor %}
        </div>
      </div>
    {% endif %}
    ```

  - [ ] 5.2 Create a tiny inclusion partial `templates/ulog/_test_duration.html` that formats the duration per AC8:

    ```django
    {% load ulog_filters %}{% comment %}
        Format `seconds` (float) per Story 1.6 AC8:
          - >= 1.0     → "{:.1f}s"  e.g. "12.0s"
          - >= 0.001   → "{:.0f}ms" e.g. "24ms"
          - else       → "<1ms"
    {% endcomment %}{{ seconds|test_duration_fmt }}
    ```

    And add a tiny `templatetags/ulog_filters.py` (if not already present) registering `test_duration_fmt`:

    ```python
    from django import template

    register = template.Library()


    @register.filter
    def test_duration_fmt(seconds):
        try:
            s = float(seconds)
        except (TypeError, ValueError):
            return ""
        if s >= 1.0:
            return f"{s:.1f}s"
        if s >= 0.001:
            return f"{s * 1000:.0f}ms"
        return "<1ms"
    ```

    Check whether `templatetags/` already exists. If yes, append the filter; if not, create the directory + `__init__.py` + the file. Adding a new templatetag MAY require a Django app reload in dev — document if so.

- [ ] **Task 6** — Tests for the adapter aggregation (AC1, AC2, AC6, AC7, AC8)
  - [ ] 6.1 In `tests/test_web.py`, add a new section under the existing tests:

    ```python
    # ============================================================================
    # Story 1.6 — Tests sidebar (FR62-64)
    # ============================================================================
    ```

  - [ ] 6.2 Add `test_test_summary_groups_by_file_and_sorts_alphabetically` (AC1, AC7):
    Build a SQLite log file with 4 plugin outcome records across 2 files, with names that would naturally sort the wrong way without explicit sort. Assert `test_summary` ordering matches AC7.

  - [ ] 6.3 Add `test_test_summary_empty_when_no_plugin_records` (AC2):
    Build a SQLite log file with only `logger='myapp'` records (no `ulog.test`). Assert `result.test_summary == []`.

  - [ ] 6.4 Add `test_test_summary_picks_outcome_record_not_started` (AC6):
    Build records: 1 "test started" (logger='ulog.test', no `outcome` in context) + 1 "test passed" (logger='ulog.test', outcome='passed', duration_s=0.024). Assert exactly 1 row in `test_summary`, with `outcome='passed'` and `duration_s=0.024` — proves the adapter filters out `test started` records.

  - [ ] 6.5 Add `test_test_summary_handles_all_four_outcomes`:
    Build records covering passed/failed/skipped/errored. Assert all four appear in `test_summary` with correct outcome strings.

- [ ] **Task 7** — Tests for the views / filter wiring (AC3, AC4, AC5, AC9)
  - [ ] 7.1 Add `test_failed_only_filter_via_query_param` (AC3) — Django test client `Client.get('/?failed_only=1')`, assert response 200 and that all returned records have `outcome IN ('failed', 'errored')`.

  - [ ] 7.2 Add `test_slowest_only_orders_by_duration_desc` (AC4) — query string `?slowest_only=1`, build a fixture DB with 12 plugin outcome records of varying durations, assert response shows exactly 10 records in DESC order.

  - [ ] 7.3 Add `test_failed_and_slowest_combine` (AC5) — both query params; build a fixture with 5 failed slow + 5 passed fast + 5 failed fast; assert top 10 of the 5 failed rows appear, sorted DESC.

  - [ ] 7.4 Add `test_existing_filters_compose_with_failed_only` (AC9) — combine `?failed_only=1&level=ERROR&logger=ulog.test`; assert intersection.

- [ ] **Task 8** — Template smoke tests (AC1, AC2, AC6, AC8)
  - [ ] 8.1 Add `test_tests_sidebar_renders_when_records_exist` (AC1) — Client.get('/'), assert response contains `<span>Tests</span>` (the section heading) and at least one outcome glyph (e.g. `✓`).

  - [ ] 8.2 Add `test_tests_sidebar_hidden_when_no_test_records` (AC2) — fixture DB with only `myapp` records, assert response does NOT contain `<span>Tests</span>` (uses `assertNotContains` from Django's `TestCase`).

  - [ ] 8.3 Add `test_duration_format_milliseconds_and_seconds` (AC8) — fixture DB with 3 tests at durations 0.0005, 0.024, 12.5 seconds. Assert the rendered HTML contains `<1ms`, `24ms`, and `12.5s` substrings respectively.

- [ ] **Task 9** — Verify and ship
  - [ ] 9.1 Run `python3 -m pytest tests/ -v`. Full suite stays green. **Test counts:** `tests/test_pytest_plugin.py` is **untouched** (40 tests, no regression). `tests/test_web.py` grows by **10 new tests** (Tasks 6.2-6.5 = 4 + 7.1-7.4 = 4 + 8.1-8.3 = 3 — actually that's 11; consolidate where overlap exists, target 10-11 net new). Verify the precise baseline of `tests/test_web.py` BEFORE starting Task 6 and report the delta in the dev agent record.
  - [ ] 9.2 Run `python3 -m mypy ulog/web/ --follow-imports=silent` — clean. The new `TestSummaryRow` dataclass and `_build_test_summary` method need accurate type hints (`list[TestSummaryRow]`). Pre-existing `ulog/web/viewer/views.py` mypy errors flagged in Story 1.1's debug log (12 of them) are NOT this story's concern — DO NOT attempt to fix them.
  - [ ] 9.3 `grep '^dependencies' pyproject.toml | grep -q '\[\]'` exits 0.
  - [ ] 9.4 `git diff --stat HEAD -- pyproject.toml ulog/__init__.py ulog/setup.py ulog/context.py ulog/formatters.py ulog/_color.py ulog/handlers/ ulog/testing/` returns empty (no production code touched outside `ulog/web/`).
  - [ ] 9.5 `git diff --stat HEAD -- tests/` reports only `tests/test_web.py` (no other test file touched — `tests/test_pytest_plugin.py` is NOT modified).
  - [ ] 9.6 Manually launch the dev server (`./run.sh dev` or equivalent) with a fixture log DB containing test records. Visually verify:
    - The TESTS sidebar appears above Sectors.
    - Outcome badges render in the correct colors.
    - Clicking "Failed only" filters the records list.
    - Clicking "Slowest top 10" reorders.
    - Both checked together combines correctly.
  - [ ] 9.7 Visually verify with a NON-test log (e.g., a `prod.sqlite` from a non-pytest application): the TESTS sidebar is ABSENT (AC2 regression check).

---

## Dev Notes

### Why this is the first significant UI story in Epic 1

Stories 1.1-1.5 were all backend (plugin internals + tests). Story 1.6 introduces the FIRST USER-FACING output: a sidebar block in the existing Django viewer template. Several discipline items shift:

1. **Template changes are visual** — automated tests can verify HTML structure (`assertContains`/`assertNotContains`), but they CANNOT verify color, spacing, or icon-rendering. Task 9.6/9.7 (manual browser check) is required, not optional.
2. **Tailwind classes** are the design system; do NOT introduce custom CSS. Reuse the patterns in the existing Sectors / Files / Levels blocks (lines 41-115 of `list.html`). The TESTS section's heading style, checkbox style, list item style — all should mirror the existing blocks visually.
3. **Frontend dependency: `django-lucide`** is already in the `[web]` extra (per `pyproject.toml`). Use `{% lucide "icon-name" size=14 %}` for icons, NOT inline SVG.
4. **The viewer's existing test-style** (in `tests/test_web.py`) uses Django's `Client` test client, NOT pytester. Don't import pytester for these tests.

### What the test data shape actually is in the DB

After Stories 1.2-1.5, a passing test produces 2 records in the SQLite `logs` table (per `_emit_outcome_records`):

| id | logger | level | msg | context (JSON) |
|----|--------|-------|-----|----------------|
| 1 | `ulog.test` | INFO | `test started` | `{"test_id": "tests/test_a.py::test_x"}` |
| 2 | `ulog.test` | INFO | `test passed` | `{"test_id": "...::test_x", "outcome": "passed", "duration_s": 0.024, "phase": "call"}` |

A failing test produces 3 records (started + outcome ERROR + traceback ERROR). A teardown failure adds a 4th record.

**The test summary is built ONLY from records where `context.outcome IS NOT NULL`** — that filters out `test started` AND traceback records, leaving exactly one row per test (the body verdict). The SQL filter `json_extract(context, '$.outcome') IS NOT NULL` matches this exactly.

### Why Story 1.7's `?test_id=` filter is OUT OF SCOPE here

Story 1.7's job is to make clicking a test name route to `/?test_id=...` AND apply that as a filter on the records list. Story 1.6 limits itself to:
- The TESTS section RENDERS test names (with the test_id value visible in `title="..."` for hover, but no click handler).
- The records list shows ALL records (subject to existing filters); it does NOT filter to a specific test_id.

If the spec is followed, Story 1.7 will simply add an `<a href="?test_id={{ t.test_id|urlencode }}">` wrapping the name, plus the `Filters.test_id: str` field and corresponding adapter clause. Story 1.6 leaves the markup in a state where Story 1.7's diff is small.

### `_build_test_summary` performance considerations (NFR-PERF)

For a typical test session of 100-500 tests, the subquery `SELECT json_extract(context, '$.test_id'), ... WHERE logger='ulog.test' AND json_extract(context, '$.outcome') IS NOT NULL` returns 100-500 rows. Even on an unindexed `logs` table, SQLite handles this in well under 50ms. No explicit index is needed for v0.3.

If a v1 user reports slow viewer loads on a 100k-test DB, Story 3.X (storage core) can add an index on `(logger, json_extract(context, '$.outcome'))`. Don't pre-emptively add it.

### Files being modified

#### `ulog/web/viewer/adapters.py` (UPDATE)

**Current state:** 420 lines. Has `Filters`, `QueryResult`, `Record` dataclasses; `SQLiteAdapter` (140 lines), `JSONLAdapter`, `CSVAdapter`.

**What this story adds:**
- New `TestSummaryRow` dataclass (~10 lines).
- Two new fields on `Filters` (`failed_only`, `slowest_only`).
- One new field on `QueryResult` (`test_summary`).
- Two `failed_only`/`slowest_only` clauses in `SQLiteAdapter._base_filters` (or split, see Task 3.2).
- New `SQLiteAdapter._build_test_summary` method (~30 lines).
- `test_summary=[]` placeholders in `JSONLAdapter.query` and `CSVAdapter.query` results.

**What this story preserves:**
- All existing dataclass fields and method signatures.
- The `_base_filters` / `_count_by` / `_distinct_bound_keys` private helpers — UNCHANGED except for the new clauses.
- The `_filter_and_paginate` Python-side filter for JSONL/CSV — UNCHANGED (those formats don't get test_summary in v0.3).

#### `ulog/web/viewer/views.py` (UPDATE)

**Current state:** 252 lines.

**What this story adds:**
- Two new keys in the dict returned by `_parse_filters` (`failed_only`, `slowest_only`).
- One new key in the `ctx` dict passed to the template (`test_summary`).
- One new key in the JSON response of `api_records` (parallel for the JS UI).

**What this story preserves:**
- `list_view` / `detail_view` / `api_records` / `docs_*` view signatures.

#### `ulog/web/templates/ulog/list.html` (UPDATE)

**Current state:** ~250 lines. Sidebar at lines 8-115; main records list below.

**What this story adds:**
- A new `<div>` block with the TESTS section, inserted BEFORE the Sectors block (line 41).
- ~50 lines of Django template + Tailwind classes.

**What this story preserves:**
- All existing sidebar blocks (Sectors, Files, Levels, Bound) — UNCHANGED.
- The records list table below — UNCHANGED (filters apply but rendering stays the same).
- The empty-state message at line 235 — UNCHANGED.

#### `ulog/web/templates/ulog/_test_duration.html` (NEW — small inclusion partial)

3-line partial that calls the `test_duration_fmt` filter. Keeps the duration logic out of the main template's inline conditionals.

#### `ulog/web/viewer/templatetags/__init__.py` + `ulog/web/viewer/templatetags/ulog_filters.py` (NEW or UPDATE)

If `templatetags/` doesn't already exist in the viewer app, create it. Add `test_duration_fmt` filter per AC8.

#### `tests/test_web.py` (UPDATE — additive)

**Current state:** existing web tests using Django test Client. Verify by reading the file's first ~30 lines and noting how Client is set up + how a fixture DB is created.

**What this story adds:**
- A new section header.
- 10-11 new test functions (Tasks 6.2-6.5 + 7.1-7.4 + 8.1-8.3).

#### Other files (DO NOT MODIFY)

`pyproject.toml`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/testing/`, `tests/test_pytest_plugin.py`. **Verify with `git diff --stat HEAD --` after the change** — the only files reported should be those listed above.

### Story 1.5 lessons applied (carry-forward)

- **Reorder mutation BEFORE risky calls** (Story 1.5 review patch P1 — `pytest_configure` set `_ulog_enabled` before `ulog.setup` to handle setup-raise gracefully). Equivalent here: in the adapter's `query` method, build `test_summary` AFTER the records query but inside the same connection's `try` block — if the JSON extract fails for any row, the empty test_summary should not break the records list.
- **Anchor record/string assertions** (Stories 1.3-1.5 carry-forward). Tests that assert on rendered HTML should use `assertContains(response, "ulog: 1 tests, 1 passed")`-style literal match where possible; substring fragility (e.g. `"passed" in html`) is too easy to false-positive.
- **Defensive guards in helpers** (Story 1.5's `_bump_session_stats` `getattr(..., None)` pattern). Apply to `test_duration_fmt`: handle non-numeric input gracefully (return empty string) so a malformed `duration_s` doesn't break the template render.
- **Initialize state only when needed** (Story 1.5 patch P5). The `test_summary` field on `QueryResult` defaults to `[]` — no extra initialization needed in disabled / non-test-data paths.
- **Hookimpl ordering** (Story 1.5 patch P6) — no analogue here (no plugin hooks in this story).

### Architecture references

| Topic | Read |
|---|---|
| FR62-64 spec | `docs/prds/PRD-v0.3-test-integration.md` §3.4 + UI mockup §6 |
| Test event schema | `docs/prds/PRD-v0.3-test-integration.md` §2.1.2 — `outcome`, `duration_s`, `test_id`, `phase` field locations |
| Sectors block reference (visual template) | `ulog/web/templates/ulog/list.html:41-61` |
| `Filters` / `QueryResult` dataclasses | `ulog/web/viewer/adapters.py:38-69` |
| `SQLiteAdapter.query` flow | `ulog/web/viewer/adapters.py:153-211` |
| `list_view` context dict | `ulog/web/viewer/views.py:54-82` |
| `_parse_filters` query-string decoding | `ulog/web/viewer/views.py:29-51` |
| Lucide icon usage in templates | search `list.html` for `{% lucide` — already used for `git-branch`, `file-text`, etc. |

### LLM-Dev anti-patterns to avoid

| Anti-pattern | Why avoid | Correct approach |
|---|---|---|
| Adding `failed_only` / `slowest_only` as full enum/state-machine | Two booleans suffice — keep it simple | `bool` fields on `Filters`, default False |
| Building `test_summary` via Python-side iteration of all `result.records` | Wasteful (records is page-limited; we want SUMMARY across the whole DB) AND mixes concerns | Use the dedicated SQL `_build_test_summary` query |
| Computing the test summary inside the template via `{% with %}` and Python-side aggregation | Templates aren't the place for SQL or aggregation logic | Pre-aggregate in the adapter, pass a flat list to the template |
| Naming the new template variable `tests` (collision with pytest's "tests" concept) | Confusing | Use `test_summary` consistently — adapter, view, template |
| Hardcoding the 10 in "Slowest top 10" as a magic number scattered across files | Maintenance hazard | Define `SLOWEST_TOP_N = 10` as a module-level constant in `adapters.py`; reference everywhere |
| Adding a custom CSS file for the test badges | The design system is Tailwind | Use existing classes (`text-green-600`, `text-red-600`, `text-amber-500`); reuse the Sectors block's patterns |
| Adding new dependencies (e.g. `pytest-django`, `humanize`) | Breaks NFR-DEP-50 | Stdlib + Django + already-installed `django-lucide` only |
| Touching `ulog/testing/pytest_plugin.py` "for consistency" | Story 1.6 is web-only; that file is plugin code, locked | Add `# DO NOT MODIFY` mental check — verify diff scope post-implementation |
| `assertContains(response, "Tests")` (substring-match for the section heading) | Both `Tests sidebar` and `Test failed` and `Tests/test_a.py` would match | Use `assertContains(response, "<span>Tests</span>")` with the exact tag wrapper |
| Using `request.GET["failed_only"]` (raises KeyError on absent) | Filter parsing must never raise on missing query params | `qs.get("failed_only", "")` with `.strip()` and the truthy-tuple check |
| Sorting `test_summary` in the template via `|dictsort` | Sort happens in the adapter (AC7); template is for rendering only | Pre-sort in `_build_test_summary` |
| Filtering `slowest_only` to exactly 10 in the template | Magic number duplication; impossible to test the limit | Apply the LIMIT in the adapter's query |
| Using `?failed=1` instead of `?failed_only=1` | Spec says `failed_only` (per AC3); URL stability matters for Story 1.7 share-able URLs | Match the spec's exact param names |
| Forgetting to update `JSONLAdapter` and `CSVAdapter` `query` to return `test_summary=[]` | The shared `QueryResult` dataclass adds the field; missing default would break those adapters | Pass `test_summary=[]` explicitly in both fallback adapter paths |
| Building a separate Django app for the test-summary feature | Over-engineering — the existing `viewer` app is the right place | Add to `viewer/`; reuse its app config |

### References

- [Source: `docs/prds/PRD-v0.3-test-integration.md`#3.4] FR62-64 — Tests sidebar rendering and quick filters
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#2.1.4] UI sketch with badges and counts
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#6] Detail-view text mockup with badge mapping
- [Source: `_bmad-output/planning-artifacts/epics.md`#Story 1.6] AC framing
- [Source: `ulog/web/templates/ulog/list.html`:41-61] Sectors block — visual template to mirror
- [Source: `ulog/web/viewer/adapters.py`:38-69] `Filters` + `QueryResult` extension points
- [Source: `ulog/web/viewer/adapters.py`:120-211] `SQLiteAdapter._base_filters` + `query` — extension sites
- [Source: `ulog/web/viewer/views.py`:29-82] `_parse_filters` + `list_view` extension sites
- [Source: `_bmad-output/implementation-artifacts/1-2-test-event-recording-start-outcome-finish.md`] Record shape that Story 1.6 reads (`logger='ulog.test'` + `context.outcome`/`duration_s`/`test_id`)
- [Source: `_bmad-output/implementation-artifacts/1-3-test-id-stability-for-parametrized-tests.md`] `test_id` format (file::name[bracket]) — partition on `::` to derive file
- [Source: `_bmad-output/implementation-artifacts/1-4-bound-context-propagation-of-test-id.md`] App records carry `test_id` (relevant for Story 1.7 cross-record filtering, NOT this story)
- [Source: `_bmad-output/implementation-artifacts/1-5-pytest-cli-flags.md`] Story 1.5 lessons — review patches P1/P3/P4 inform the AC anchoring discipline

### Library / framework versions

- **Python `>=3.10`**, Django `>=5.0` (in `[web]` extra). Template features used (`{% regroup %}`, `<details>` / `<summary>` HTML5 elements, `{% include with %}`) all stable since Django 4.x and HTML5.
- **`django-lucide >= 1.3`** (already in `[web]` extra) — used for the `flask-conical` icon. If a future Lucide release renames the icon, swap to a near-equivalent (`beaker`, `microscope`); keep the section's visual identity.
- **SQLAlchemy `>= 2.0`** (already in `[storage]` extra) — `func.json_extract(...)` is the SQLite dialect form for reading JSON columns. Stable since SQLAlchemy 1.4+.
- **No new dependencies.** `dependencies = []` regression gate stays green.

### Definition of Done — Story 1.6

- [ ] `Filters` has `failed_only: bool` and `slowest_only: bool` fields, both default False; `is_empty()` accounts for them.
- [ ] `QueryResult` has `test_summary: list[TestSummaryRow]` field.
- [ ] `TestSummaryRow` dataclass exists with the documented fields.
- [ ] `SQLiteAdapter._build_test_summary` aggregates one row per distinct `test_id` from `logger='ulog.test'` records with non-null `context.outcome`, sorted by file then by name.
- [ ] `_base_filters` applies the `failed_only` and `slowest_only` WHERE clauses; `query()` applies `slowest_only`'s ORDER BY + LIMIT 10.
- [ ] `JSONLAdapter` and `CSVAdapter` return `test_summary=[]` (placeholder for v0.3).
- [ ] `_parse_filters` decodes `?failed_only=1` and `?slowest_only=1` from the query string.
- [ ] `list_view` and `api_records` pass `test_summary` to their respective consumers.
- [ ] `list.html` renders the TESTS section above Sectors when `test_summary` is non-empty; hides it otherwise.
- [ ] Outcome badges visually distinguish passed/failed/skipped/errored per AC6.
- [ ] Duration formatting follows AC8 (ms / s / `<1ms`).
- [ ] Quick-filter checkboxes exist and are wired to `failed_only` / `slowest_only`.
- [ ] `tests/test_web.py` has 10-11 new tests covering the adapter, view, and template layers.
- [ ] `tests/test_pytest_plugin.py` is **untouched** (40 tests, no regression).
- [ ] Full suite (122 baseline + 10-11 new = 132-133 tests) green.
- [ ] `mypy ulog/web/ --follow-imports=silent` clean (no NEW errors; pre-existing 12 errors in `views.py` are deferred).
- [ ] `grep '^dependencies' pyproject.toml | grep -q '\[\]'` → exit 0.
- [ ] `git diff --stat HEAD --` reports ONLY `ulog/web/*` and `tests/test_web.py`.
- [ ] Manual browser check (Task 9.6/9.7) confirms visual correctness on test-DB and absence on non-test DB.
- [ ] AC1-AC10 each verifiable.
- [ ] Story 1.7 will be a small extension: just an `<a href>` wrapping the test name + a single-clause filter — Story 1.6 leaves the structure in that shape.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
