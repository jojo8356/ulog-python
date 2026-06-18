# Epic 9: BMAD catch-up ledger — v0.7 to v0.9 shipped PRDs

Status: done

**Project:** ulog-python
**Purpose:** Regularize BMAD tracking for PRDs that shipped after Epic 8 without per-story BMAD artifacts.

## Context

BMAD implementation tracking currently stops at Epic 8, while the codebase and PRD index show later shipped work:

- v0.7.0 — Test execution stack (`ulog.span`, span panel, `ulog explain`)
- v0.8.0 — Modern frontend stack (Tailwind CLI, Alpine.js, HTMX surfaces)
- v0.8.1 — Docs syntax highlighting (Prism.js)
- v0.9.0 — Resource validity (`ulog validate-resources`, Resources sidebar)

Epic 9 is therefore a **catch-up ledger**, not a forward implementation epic. Its stories record the shipped surfaces, test anchors, and commits so future BMAD work does not lose traceability.

## Stories

| Story | Scope | Status |
|---|---|---|
| 9-1 | v0.7 span core API and SQL record shape | done |
| 9-2 | v0.7 span UI panel and `ulog explain` CLI | done |
| 9-3 | v0.8 Tailwind/Alpine/HTMX frontend stack | done |
| 9-4 | v0.8.1 Prism docs syntax highlighting | done |
| 9-5 | v0.9 resource validation CLI | done |
| 9-6 | v0.9 Resources sidebar panel | done |
| 9-7 | PRD/changelog/BMAD alignment record | done |

## Acceptance Criteria

1. Every shipped PRD from v0.7 through v0.9 has at least one BMAD artifact.
2. Each artifact lists the concrete implementation commit(s) and regression tests.
3. `sprint-status.yaml` includes Epic 9 and marks all catch-up stories done.
4. The catch-up explicitly avoids changing shipped production behavior.

## Verification Anchors

- `CHANGELOG.md` entries for v0.7.0, v0.8.0, v0.8.1, v0.9.0.
- `docs/prds/index.md` shipped statuses for v0.7.0 through v0.9.0.
- Regression tests:
  - `tests/test_spans.py`
  - `tests/test_span_panel.py`
  - `tests/test_explain.py`
  - `tests/test_v08_frontend.py`
  - `tests/test_filter_form_htmx.py`
  - `tests/test_pagination_htmx.py`
  - `tests/test_cheatsheet_search.py`
  - `tests/test_docs_syntax_highlight.py`
  - `tests/test_validate_resources.py`
  - `tests/test_resources_sidebar.py`
