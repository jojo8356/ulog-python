# Story 6.5: Multi-track Django view + template + vanilla JS

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-5-multi-track-django-view-template-vanilla-js`
**Implements:** FR112, NFR-PERF-55 / SC7, NFR-DEP-50.
**Built on:** Story 6.4 (multi_track adapter method).

## Story

As a viewer user,
I want a `/multi-track` page rendering 4 horizontal SVG strips
(level/service/author/file) over the shared time axis with mute
toggles,
so that I can see traffic patterns across multiple dimensions at a
glance.

## Acceptance Criteria

1. Route `/multi-track?from=...&to=...` rendered by `multi_track_view`.
2. Defaults: `from = now-1h`, `to = now` when params omitted.
3. Page shows 4 horizontal SVG strips, one per track
   (level/service/author/file), with one tick per `(bucket, value)`
   colored per value.
4. Each strip has a mute toggle checkbox; muted tracks are visually
   dimmed.
5. Adapter call uses `Story 6.4`'s `multi_track(...)`; `author` track
   plumbed via blame index in the view.
6. JS < 50 LOC vanilla (no d3/plotly/chart.js — NFR-DEP-50).
7. Nav link "Multi-track" in `base.html`.
8. Tests:
   - View renders 200 with 4 strips.
   - Default window when no `from`/`to`.
   - Author track populated when blame index is configured.
   - Empty window → `(no data)` placeholder for that track.

## Dev Agent Record

### Completion Notes List

- New `iter_records_in_window(start, end)` on `Adapter` (SQLite SQL
  scan; JSONL/CSV in-memory filter).
- New view `multi_track_view`; URL wired in `urls.py`.
- New template `multi_track.html` (4 SVG strips + mute toggles).
- Nav link added to `base.html`.
- 7 / 7 tests green.

### File List

- `ulog/web/viewer/adapters.py` — `iter_records_in_window` on each adapter
- `ulog/web/viewer/views.py` — `multi_track_view`
- `ulog/web/urls.py` — new route
- `ulog/web/templates/ulog/multi_track.html` (NEW)
- `ulog/web/templates/ulog/base.html` — nav link
- `tests/test_multi_track_view.py` (NEW)
