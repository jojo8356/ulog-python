# Story 2.6: Authors sidebar section with ghost counts

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-6-authors-sidebar-section-with-ghost-counts`
**Implements:** FR76 (sidebar section between Files and Time range), FR79 (ghost counts ignore the author axis itself per v0.2.1)
**Source:** PRD-v0.4 §2.1.2, §3.2 FR76+FR79; epics.md Story 2.6
**Built on:** Stories 2.1, 2.3, 2.5 (`compute_authors_summary` is the count source)

## Story
As a viewer user filtering by author, I want a multi-select Authors sidebar section that honors the v0.2.1 ghost-count contract, so ticking authors doesn't zero out other authors' counts.

## Acceptance Criteria
- **AC1** — Sidebar block "AUTHORS" rendered between "Files" and "Time range".
- **AC2** — Each row shows: name + truncated email (≤20 chars) + ghost-count.
- **AC3** — `<unknown>` row appears last with the unknown count, IF unknown_count > 0.
- **AC4** — Counts are computed via `compute_authors_summary(adapter, idx)` with `filters._replace(authors=[])` (per v0.2.1 ghost-count rule).
- **AC5** — When `idx is None` (e.g. `--no-author-index` or no .git/), the entire Authors block is hidden.
- **AC6** — Tests cover the data path; template render is verified by Django test client.

## Implementation
- `Filters` gets `authors: list[str]` + `show_unknown: bool` (default True per FR78).
- View computes `authors_summary` via `compute_authors_summary(adapter, idx)`. Idx comes from `get_global_index()`.
- Template renders the new block + checkboxes (form submission preserves filters).

## Dev Agent Record
### File List
- `ulog/web/viewer/adapters.py` — `Filters` extended with `authors`, `show_unknown`
- `ulog/web/viewer/views.py` — `_parse_filters` reads `?author=...` getlist; computes summary
- `ulog/web/templates/ulog/list.html` — Authors block between Files and Time range
- `tests/test_authors_sidebar.py` — NEW

### Completion Notes
Suite at 226 + 5 = 231/231. Story 2.7 wires actual filter behavior; this story renders the panel + computes ghost counts.
