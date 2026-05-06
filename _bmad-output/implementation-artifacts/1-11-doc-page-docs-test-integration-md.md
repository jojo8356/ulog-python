# Story 1.11: Doc page `/docs/test-integration.md`

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**Epic:** 1 — v0.3 Test integration (FINAL story; closes the epic)
**Story key:** `1-11-doc-page-docs-test-integration-md`
**Implements:** NFR-DOC-10 (PRD-v0.3 §4)
**Source:** `docs/prds/PRD-v0.3-test-integration.md` §4 (NFR-DOC-10), `_bmad-output/planning-artifacts/epics.md` Story 1.11
**Built on:** Stories 1.1-1.10 (everything in v0.3 — the doc page is the user-facing index of all the features)
**Foundation for:** Epic 1 retrospective; v0.3 release notes

---

## Story

As a **new pytest+ulog user**,
I want **a doc page at `/docs/test-integration/` covering plugin install, CLI flags, schema, and a "find failed tests" worked example**,
so that **I can adopt the plugin without reading the PRD or the architecture document**.

## Acceptance Criteria

### AC1 — Doc page exists at `/docs/test-integration/` (NFR-DOC-10)

**Given** the viewer is running
**When** the user navigates to `/docs/test-integration/`
**Then** the page renders with HTTP 200 and the markdown content covers:
  - **Install** section: `pip install ulog[testing]` + a one-line note about pytest auto-discovery (no `conftest.py` config required for FR51)
  - **CLI flags** section: each of `--ulog-db PATH`, `--ulog-disable`, `--ulog-summary` with one-line description of behavior (Stories 1.1 + 1.5)
  - **Test event schema** section: the 3-record shape (started + outcome + optional traceback ERROR) with example JSON for each
  - **"Find failed tests" worked example** section: end-to-end recipe — `pytest --ulog-db ./logs.sqlite` → `ulog-web ./logs.sqlite` → click "Failed only" → click a test name → read records
  - **Troubleshooting** section: brief mention of xdist+NFS fallback (Story 1.10) and the JSONL warning text users may see

### AC2 — Page registered in the docs index (`/docs/`)

**Given** the user opens `/docs/`
**When** the index page renders
**Then** "Test integration" appears in the page list with a link to `/docs/test-integration/`. The `_DOC_PAGES` dict in `views.py` is extended with the new entry.

### AC3 — Markdown renders without syntax errors via the in-house renderer (no markdown-it-py dep)

**Given** the page is markdown source at `ulog/web/docs/test-integration.md`
**When** the in-house renderer (`_markdown_to_html` in `views.py`) processes it
**Then** the rendered HTML contains:
  - At least one `<h1>` (page title)
  - Multiple `<h2>` (section headings)
  - Multiple `<pre><code>` blocks (the install command, CLI examples, JSON schema)
  - At least one `<a href>` link (to the related `/docs/storage/` page or external pytest docs)
  No raw markdown syntax (`#`, `\`\`\``, `**`) leaks into the rendered output. NO `ImportError` for markdown-it-py.

### AC4 — Page contains a copy-pasteable conftest example (PRD §5.1)

**Given** the markdown source includes a Python code block with a conftest.py recipe
**When** the page renders
**Then** the code block is wrapped in `<pre><code class="language-python">...` and contains EXACTLY:

```python
# conftest.py
import ulog

def pytest_configure(config):
    ulog.setup(
        handlers=['sql'],
        sql_url='sqlite:///./tests-logs.sqlite',
    )
```

This is the canonical "host setup" recipe per PRD-v0.3 §5.1. Users copy-paste verbatim.

### AC5 — Page contains the FR69 summary line example

**Given** the section "CLI flags" mentions `--ulog-summary`
**When** the page renders
**Then** an exact-format example of the rendered summary line appears: `ulog: 412 tests, 409 passed, 3 failed, 0 skipped → ulog-web ./logs.sqlite to triage` (matching PRD-v0.3 §2.1.6 + Story 1.5's actual output format).

### AC6 — Page mentions the `test_event` programmatic API (Story 1.9 / PRD §5.2)

**Given** the section "Programmatic API" exists
**When** rendered
**Then** a code block shows the Story 1.9 idiom:

```python
from ulog.testing import test_event

with test_event("custom_test_42") as ev:
    log.info("step 1")
    ev.outcome("passed", duration_s=0.42)
```

### AC7 — Frozen-invariant + regression-gate compliance

**Given** Story 1.11's changes
**When** the standard regression checks run
**Then**:
  - `dependencies = []` in `pyproject.toml` is unchanged.
  - `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/testing/` ALL UNCHANGED. Story 1.11 lives in `ulog/web/docs/test-integration.md` (NEW file), `ulog/web/viewer/views.py` (extends `_DOC_PAGES`), and `tests/test_web.py` (new tests).
  - All 174 existing tests still pass.

---

## Tasks / Subtasks

- [ ] **Task 1** — Create `ulog/web/docs/test-integration.md` (AC1, AC4, AC5, AC6)
  - [ ] 1.1 The file structure (markdown headings):

    ```markdown
    # Test integration

    ULog v0.3 ships a pytest plugin that records every test's lifecycle
    as structured log records — so you can answer "what did this failing
    test log?" in two clicks instead of grepping CI output.

    ## 1. Install

    ```bash
    pip install ulog[testing]
    ```

    Pytest auto-discovers the plugin via the `pytest11` entry-point —
    no `conftest.py` configuration required (FR51).

    ## 2. Run your tests

    ### Option A — bare CLI flag

    ```bash
    pytest --ulog-db ./tests-logs.sqlite
    ```

    The plugin auto-configures `ulog.setup(handlers=['sql'], sql_url=...)`
    pointing at your chosen path (FR67).

    ### Option B — `conftest.py` setup

    ```python
    # conftest.py
    import ulog

    def pytest_configure(config):
        ulog.setup(
            handlers=['sql'],
            sql_url='sqlite:///./tests-logs.sqlite',
        )
    ```

    Use this when your project already has a `conftest.py` and you want
    test logs to live alongside other ulog setup (e.g. shared with
    application logs in dev).

    ## 3. CLI flags

    | Flag | Behavior |
    |---|---|
    | `--ulog-db PATH` | Override the destination DB. Auto-configures `setup()` if no host conftest did. |
    | `--ulog-disable` | Short-circuit the plugin (no records emitted). Escape hatch. |
    | `--ulog-summary` | Default ON. Prints a one-line stderr summary at session end. `pytest -q` suppresses. |

    Example summary line (FR69):

    ```
    ulog: 412 tests, 409 passed, 3 failed, 0 skipped → ulog-web ./logs.sqlite to triage
    ```

    ## 4. Test event schema

    Each test produces 2-3 records, all with the same `test_id` (the
    pytest nodeid):

    ```json
    {"level": "INFO", "msg": "test started", "logger": "ulog.test",
     "context": {"test_id": "tests/test_foo.py::test_bar"}}
    ```

    ```json
    {"level": "INFO", "msg": "test passed", "logger": "ulog.test",
     "context": {"test_id": "...", "outcome": "passed",
                 "duration_s": 0.024, "phase": "call"}}
    ```

    On failure, an additional ERROR record carries the traceback:

    ```json
    {"level": "ERROR", "msg": "AssertionError: foo != bar", "logger": "ulog.test",
     "context": {"exc": {"type": "AssertionError", "msg": "...", "tb": [...]}}}
    ```

    Application records emitted DURING a test inherit `test_id`
    automatically via `ulog.bind` (Story 1.4 propagation):

    ```python
    log = ulog.get_logger("myapp")

    def test_render():
        log.info("rendering rom")  # → record carries test_id="...::test_render"
    ```

    ## 5. Find failed tests — worked example

    Say a CI run flagged 3 failing tests out of 412 and you have the
    SQLite log artefact. Open the viewer:

    ```bash
    ulog-web ./logs.sqlite
    ```

    1. The TESTS sidebar lists every test grouped by file with outcome
       badges (✓ green / ✗ red / 🔥 errored / ⊘ skipped).
    2. Tick "Failed only" — the records list narrows to the 3 failing
       tests' outcome records.
    3. Click a test name in the sidebar — the records list filters to
       ALL records bound to that test (plugin records + application
       records inherited via `bind`).
    4. Click any record in the list to see its full detail. The "Test
       context" panel offers two more drill-downs: "view all records
       for this test" and "errors+warnings only".

    Total: 3 clicks from CI artefact to root cause.

    ## 6. Programmatic API (non-pytest runners)

    For custom test runners (asyncio drivers, benchmark harnesses, hand-
    rolled test loops), use the `test_event` context manager:

    ```python
    from ulog.testing import test_event

    with test_event("custom_test_42") as ev:
        log.info("step 1")  # propagates test_id via bind
        do_thing()
        ev.outcome("passed", duration_s=0.42)
    ```

    Same record shape as pytest tests. If the block raises without an
    explicit `ev.outcome(...)` call, the wrapper auto-emits
    `outcome="errored"` plus the traceback.

    ## 7. Troubleshooting

    ### "I see a `ulog: xdist+NFS detected` warning"

    The plugin detected `pytest-xdist` running with the SQLite path on
    a network filesystem (NFS / CIFS / SMB). SQLite locking is unreliable
    over NFS, so the plugin transparently swapped to JSONL output at the
    same path stem. Records still land — just in `<path>.jsonl` instead
    of `<path>.sqlite`. The viewer reads JSONL natively.

    ### "I see a `ulog: xdist+Windows detected` warning"

    Same fallback, triggered for any xdist run on Windows. Windows
    file-locking semantics on SQLite under multi-process are unreliable;
    JSONL is the safe path.

    ### "I see a `ulog: WAL mode unavailable` warning"

    The plugin tried to enable SQLite's WAL journal mode for concurrent
    xdist writers and the underlying filesystem rejected it. Falls back
    to JSONL — same as the NFS / Windows cases.

    ## See also

    - [Storage handlers](/docs/storage/) — how the SQL handler stores records
    - [Quickstart](/docs/quickstart/) — non-pytest setup
    - [pytest documentation](https://docs.pytest.org/) — pytest itself
    ```

  - [ ] 1.2 The triple-backtick-fenced bash/python/json blocks must NOT use the `language-bash` syntax that markdown-it-py supports — the in-house `_markdown_to_html` (in `views.py`) recognizes the simpler ``` ` ``` form. Verify by reading the renderer (line ~163-235 of `views.py`) before authoring.

- [ ] **Task 2** — Register the page in `_DOC_PAGES` (AC2)
  - [ ] 2.1 In `ulog/web/viewer/views.py`, extend `_DOC_PAGES` (line 175):

    ```python
    _DOC_PAGES: dict[str, str] = {
        "quickstart": "Quickstart",
        "storage": "Storage handlers (SQL / JSON / CSV)",
        "api": "Python API reference",
        "troubleshooting": "Troubleshooting",
        "sectors-and-files": "Sectors and files explained",
        "test-integration": "Test integration",  # Story 1.11 — v0.3
    }
    ```

  - [ ] 2.2 The order matters for the docs-index template — newest entries can go at the end. The page slug `"test-integration"` must match the markdown filename stem.

- [ ] **Task 3** — Tests for the new doc page (AC1, AC2, AC3, AC4, AC5, AC6)
  - [ ] 3.1 Add a section header in `tests/test_web.py`:

    ```python
    # ============================================================================
    # Story 1.11 — Doc page /docs/test-integration/ (NFR-DOC-10)
    # ============================================================================
    ```

  - [ ] 3.2 Add `test_test_integration_doc_page_renders` (AC1, AC3):

    ```python
    def test_test_integration_doc_page_renders(sqlite_fixture):
        client = _make_django_client(sqlite_fixture)
        resp = client.get("/docs/test-integration/")
        assert resp.status_code == 200
        body = resp.content.decode()
        # AC3: structural elements
        assert "<h1" in body  # page title
        assert "<h2" in body  # section headings
        assert "<pre" in body and "<code" in body  # code blocks
        # AC1: required sections
        assert "Install" in body
        assert "CLI flags" in body
        assert "Test event schema" in body
        assert "worked example" in body or "Find failed tests" in body
    ```

  - [ ] 3.3 Add `test_test_integration_doc_page_listed_in_index` (AC2):

    ```python
    def test_test_integration_doc_page_listed_in_index(sqlite_fixture):
        client = _make_django_client(sqlite_fixture)
        resp = client.get("/docs/")
        assert resp.status_code == 200
        body = resp.content.decode()
        # AC2: index lists the new page
        assert "Test integration" in body
        # And it's a clickable link to the new URL
        assert "/docs/test-integration/" in body
    ```

  - [ ] 3.4 Add `test_test_integration_doc_page_includes_conftest_example` (AC4):

    ```python
    def test_test_integration_doc_page_includes_conftest_example(sqlite_fixture):
        client = _make_django_client(sqlite_fixture)
        resp = client.get("/docs/test-integration/")
        body = resp.content.decode()
        # AC4: canonical conftest recipe (verbatim per PRD-v0.3 §5.1)
        assert "ulog.setup(" in body
        assert "handlers=['sql']" in body
        assert "sql_url=" in body
    ```

  - [ ] 3.5 Add `test_test_integration_doc_page_includes_summary_line_example` (AC5):

    ```python
    def test_test_integration_doc_page_includes_summary_line_example(sqlite_fixture):
        client = _make_django_client(sqlite_fixture)
        resp = client.get("/docs/test-integration/")
        body = resp.content.decode()
        # AC5: exact format of the rendered summary line
        assert "ulog: 412 tests, 409 passed, 3 failed, 0 skipped" in body
        assert "ulog-web" in body
    ```

  - [ ] 3.6 Add `test_test_integration_doc_page_includes_test_event_example` (AC6):

    ```python
    def test_test_integration_doc_page_includes_test_event_example(sqlite_fixture):
        client = _make_django_client(sqlite_fixture)
        resp = client.get("/docs/test-integration/")
        body = resp.content.decode()
        # AC6: programmatic API example
        assert "from ulog.testing import test_event" in body
        assert "with test_event(" in body
        assert "ev.outcome(" in body
    ```

  - [ ] 3.7 Add `test_test_integration_unknown_subpage_404`:

    ```python
    def test_test_integration_unknown_subpage_404(sqlite_fixture):
        client = _make_django_client(sqlite_fixture)
        # The page slug is "test-integration"; anything else 404s
        resp = client.get("/docs/test-integration-WRONG/")
        assert resp.status_code == 404
    ```

- [ ] **Task 4** — Verify and ship
  - [ ] 4.1 Run `python3 -m pytest tests/ -v`. Full suite stays green. `tests/test_web.py` baseline is **50 tests** (post-Story 1.8). This story grows it to **56 tests** (6 new from Tasks 3.2-3.7). Full project suite: 174 + 6 = **180 tests**.
  - [ ] 4.2 `mypy ulog/web/ --follow-imports=silent` — zero new errors. Story 1.11 only adds a markdown file + 1 dict entry — no new code paths.
  - [ ] 4.3 `grep '^dependencies' pyproject.toml | grep -q '\[\]'` exits 0.
  - [ ] 4.4 `git diff --stat HEAD --` reports ONLY:
    - `ulog/web/docs/test-integration.md` (NEW)
    - `ulog/web/viewer/views.py` (1-line `_DOC_PAGES` extension)
    - `tests/test_web.py` (6 new tests)
  - [ ] 4.5 Manual browser check: navigate to `http://localhost:<port>/docs/test-integration/` with the dev server running; verify the page renders without raw markdown syntax, links work, code blocks display correctly.

---

## Dev Notes

### Why this is the smallest story in the epic

Stories 1.1-1.10 implemented the entire v0.3 feature surface (plugin, propagation, viewer, programmatic API, xdist edges). Story 1.11 is the user-facing index — a single markdown file + a 1-line registration. The volume is in the markdown content, NOT in the code.

### `_markdown_to_html` constraints (read before authoring)

The in-house renderer at `ulog/web/viewer/views.py:163-235` supports a SUBSET of CommonMark:
- Headings via `# / ## / ###`
- Code blocks via fenced ` ``` ` (with optional language hint, e.g. ` ```python `)
- Inline code via single backticks
- Bold via `**text**`
- Links via `[text](url)`
- Lists via `-` or `*`
- Tables via pipe syntax (renderer-specific; verify by reading `_markdown_to_html`)

What it does NOT support:
- Footnotes (markdown-it-py extension)
- Task lists (`- [ ]`)
- Definition lists
- HTML embedded directly (renderer escapes raw `<`)

The doc page MUST stay within this subset. Story 1.11's markdown source uses ONLY headings + fenced code + simple lists + tables.

### Why the conftest example is verbatim from the PRD

PRD-v0.3 §5.1 documents the exact recipe a user is expected to copy-paste. Diverging risks the docs and PRD drifting. AC4's exact-string assertion locks the recipe; if a future PRD revision changes it, the test trips and the docs author updates both files together.

### Why the troubleshooting section mentions xdist warnings explicitly

A user hitting the warning text in stderr will Google the exact message. Including the literal `ulog: xdist+NFS detected` and `ulog: xdist+Windows detected` strings in the docs page makes the doc the canonical match for those searches.

### Files being modified

#### `ulog/web/docs/test-integration.md` (NEW)

~120-150 lines of markdown across 7 sections.

#### `ulog/web/viewer/views.py` (UPDATE — minimal)

1 new line in `_DOC_PAGES` dict. ~1-line change.

#### `tests/test_web.py` (UPDATE — additive)

Section header + 6 new tests. ~80 lines added.

#### Other files (DO NOT MODIFY)

`pyproject.toml`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/testing/`, `ulog/web/templates/`, `ulog/web/viewer/adapters.py`, `tests/test_pytest_plugin.py`, `tests/test_test_event.py`, all other tests.

### Story 1.10 lessons applied

- **mypy clean** (Story 1.10 final mypy fix). Story 1.11 has no new typed code; just dict literal + markdown.
- **`_make_django_client` settings cache** (Story 1.6 fix). The doc-page tests reuse `sqlite_fixture` — the same path every time — so no settings-cache concern.
- **Defensive guard against vacuous tests** (Story 1.6 P4). Each test has a UNIQUE substring matched against the rendered body to avoid false positives.

### Architecture references

| Topic | Read |
|---|---|
| NFR-DOC-10 spec | `docs/prds/PRD-v0.3-test-integration.md` §4 |
| Conftest recipe (verbatim) | `docs/prds/PRD-v0.3-test-integration.md` §5.1 |
| Programmatic API recipe | `docs/prds/PRD-v0.3-test-integration.md` §5.2 |
| Summary line format | `docs/prds/PRD-v0.3-test-integration.md` §2.1.6 |
| Test event schema | `docs/prds/PRD-v0.3-test-integration.md` §2.1.2 |
| Existing docs page format | `ulog/web/docs/quickstart.md` (mirror this style) |
| In-house markdown renderer | `ulog/web/viewer/views.py:163-235` (`_markdown_to_html`) |
| Docs registration | `ulog/web/viewer/views.py:175-181` (`_DOC_PAGES` dict) |

### LLM-Dev anti-patterns to avoid

| Anti-pattern | Why avoid | Correct approach |
|---|---|---|
| Using markdown features not supported by `_markdown_to_html` | Page renders broken (raw markdown syntax visible) | Stay within heading / fenced-code / list / table / link / inline-code / bold subset |
| Adding `# type: ignore` to the `_DOC_PAGES` extension | The dict literal is fully-typed already (`dict[str, str]`); no ignore needed | Just add the entry |
| Using `assert "Test integration" in body` ONLY (no link check) | Substring match passes if the heading appears anywhere; doesn't verify the link | Also assert `/docs/test-integration/` URL is in the rendered HTML |
| Embedding HTML directly in the markdown | Renderer escapes `<` to `&lt;` | Use markdown syntax only |
| Hardcoding "412 tests, 409 passed" as a fictional example | Could mislead users about realistic scale | The number is intentionally large (matches PRD example) — it's an example, not a claim about a specific run |
| Putting the troubleshooting section BEFORE the worked example | UX: users want recipes first, troubleshooting last | Recipes early, troubleshooting last |
| Using the language hint ``` ```python ``` if the renderer doesn't support it | Verify by reading the renderer; some recognize it as a class hint, some treat as part of the code block | Test rendering before committing |
| Linking to internal pages with absolute URLs | Path resolution depends on the request's host header | Use relative URLs `/docs/storage/` |
| Forgetting to add the entry to `_DOC_PAGES` | Page exists at `/docs/test-integration/` but doesn't appear in `/docs/` index | Both Task 1 (markdown) AND Task 2 (registration) are required |
| Adding a "TOC" section that duplicates the headings | Maintenance burden; markdown renderers often auto-generate | Skip explicit TOC; rely on heading anchors |

### References

- [Source: `docs/prds/PRD-v0.3-test-integration.md`#4] NFR-DOC-10
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#5.1] conftest recipe
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#5.2] programmatic API
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#2.1.6] summary line format
- [Source: `_bmad-output/planning-artifacts/epics.md`#Story 1.11] AC framing
- [Source: `ulog/web/docs/quickstart.md`] doc page style precedent
- [Source: `ulog/web/viewer/views.py`:175] _DOC_PAGES extension site

### Library / framework versions

- **No new dependencies.** Pure markdown + 1 dict entry.

### Definition of Done — Story 1.11

- [ ] `ulog/web/docs/test-integration.md` exists with all 7 sections (Install / Run / CLI flags / Schema / Worked example / Programmatic API / Troubleshooting).
- [ ] Conftest recipe (Task 1.1 §2 Option B) is present verbatim.
- [ ] Summary line example matches PRD §2.1.6 / Story 1.5 format.
- [ ] `test_event` programmatic example present.
- [ ] xdist+NFS / xdist+Windows / WAL warnings documented in troubleshooting.
- [ ] `_DOC_PAGES` extended with `"test-integration": "Test integration"`.
- [ ] 6 new tests in `tests/test_web.py` covering AC1-AC6 + 404 path.
- [ ] Test module count: 50 baseline + 6 new = **56 tests** in `tests/test_web.py`. Full suite: 174 + 6 = **180 tests**.
- [ ] `mypy ulog/web/ --follow-imports=silent` clean.
- [ ] `grep '^dependencies' pyproject.toml | grep -q '\[\]'` → exit 0.
- [ ] `git diff --stat HEAD --` reports only `ulog/web/docs/test-integration.md` (NEW) + `ulog/web/viewer/views.py` + `tests/test_web.py`.
- [ ] AC1-AC7 each verifiable.
- [ ] Epic 1 (v0.3) is COMPLETE — retrospective is the only remaining step.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
