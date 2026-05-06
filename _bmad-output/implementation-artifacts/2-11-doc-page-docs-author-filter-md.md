# Story 2.11: Doc page `/docs/author-filter`

Status: done

**Epic:** 2 — v0.4 Author attribution (FINAL story; closes the epic)
**Story key:** `2-11-doc-page-docs-author-filter-md`
**Implements:** NFR-DOC-30 (PRD-v0.4 §4)
**Source:** PRD-v0.4 §4 NFR-DOC-30; epics.md Story 2.11

## Story
As a new author-filter user, I want a doc page covering how it works, what `<unknown>` means, the "code author vs commit author" distinction, and a worked example, so I understand the feature without reading the PRD.

## Acceptance Criteria
- **AC1** — Page renders at `/docs/author-filter/` with HTTP 200.
- **AC2** — Page covers: how the indexer works, CLI flags, `<unknown>` semantics, code-vs-commit-author distinction, "find errors in code Lin wrote this week" worked example, performance budgets, security, no-dep guarantee, troubleshooting.
- **AC3** — Page registered in the docs index `/docs/`.
- **AC4** — Page renders without markdown syntax leaking into the HTML output.
- **AC5** — Tests cover the page render path and presence in the index.

## Dev Agent Record
### File List
- `ulog/web/docs/author-filter.md` — NEW
- `ulog/web/viewer/views.py` — `_DOC_PAGES` extended with `"author-filter": "Author filter"`
- `tests/test_authors_doc_page.py` — NEW

### Completion Notes
Suite at 262 + 4 = 266/266. Epic 2 v0.4 — done.
