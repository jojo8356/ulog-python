# Story 2.7: Multi-select OR + URL query string + "Show unknown"

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-7-multi-select-or-url-query-string-show-unknown`
**Implements:** FR77 (multi-select OR + URL persistence), FR78 (Show unknown checkbox, default ON)
**Source:** PRD-v0.4 §3.2 FR77+FR78; epics.md Story 2.7
**Built on:** Story 2.6 (sidebar render + filters parsing)

## Story
As a viewer user combining author filters, I want multi-select with OR semantics persisted in the URL, so I can share the URL of a specific author combination.

## Acceptance Criteria
- **AC1** — `?author=foo@x&author=bar@y` filters records to authors with those emails (OR).
- **AC2** — Reload preserves the selection (URL is canonical).
- **AC3** — `<unknown>` value (URL-encoded) in `?author=` filters to records with no resolved author.
- **AC4** — `?show_unknown=0` hides unknown records when no specific author filter is active.
- **AC5** — Pagination is correct after filtering (total count reflects filtered set).
- **AC6** — Tests cover single-author, multi-author OR, unknown sentinel, show_unknown toggle.

## Implementation
The view post-filters records returned by the adapter. For Epic 2 we accept the in-memory cost (NFR-PERF-31 budget is ≤500ms; v0.5 may push the JOIN down to SQL).

## Dev Agent Record
### File List
- `ulog/web/viewer/views.py` — post-filter + manual pagination when author filter active
- `tests/test_authors_filter.py` — NEW

### Completion Notes
Suite at 233 + 7 = 240/240.
