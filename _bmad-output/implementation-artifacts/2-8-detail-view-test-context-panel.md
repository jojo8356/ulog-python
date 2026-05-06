# Story 2.8: Detail-view "Authored by" panel

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-8-detail-view-test-context-panel`
**Implements:** FR80 (detail-view sub-section: name + email + 7-char short-sha + relative date + 2 links)
**Source:** PRD-v0.4 §3.3 FR80; epics.md Story 2.8

## Story
As a viewer user investigating a record, I want a detail-view sub-section with the author's name, email, short-sha, relative date, and links to "all records from this author" + "view diff", so I can pivot from one record to context.

## Acceptance Criteria
- **AC1** — Panel rendered between "Test context" (Story 1.8) and "Exception" blocks when an author is resolved.
- **AC2** — Panel hidden when `author is None` (no idx, untracked file, or line OOR).
- **AC3** — Shows: name + email (truncated to 40 chars) + 7-char short-sha + relative date.
- **AC4** — Two links: "view all records from this author" → `/?author=<email>` and "view diff: <sha>" → `/diff/<full_sha>/`.
- **AC5** — `_relative_date(ts)` formats unix-ts as "X minutes/hours/days/months/years ago" using stdlib only.
- **AC6** — Tests cover render + hide cases + relative-date helper.

## Dev Agent Record
### File List
- `ulog/web/viewer/views.py` — author lookup + relative-date helper
- `ulog/web/templates/ulog/detail.html` — Authored by panel
- `tests/test_authors_detail_panel.py` — NEW

### Completion Notes
The /diff/<sha>/ route is Story 2.9. For now the link just navigates; Story 2.9 wires the actual handler.
