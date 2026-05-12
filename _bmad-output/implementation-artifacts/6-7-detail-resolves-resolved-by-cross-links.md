# Story 6.7: Detail Resolves / Resolved-by cross-links

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-7-detail-resolves-resolved-by-cross-links`
**Implements:** FR114.
**Depends on:** Epic 5 (resolve / reopen).

## Story

As a viewer user inspecting an incident-bearing record,
I want the detail panel to show "Resolves: #N" / "Resolved by: #M"
cross-links with the resolution note inline,
so that I navigate the incident lifecycle without writing SQL.

## Acceptance Criteria

1. Detail page of an incident record shows "Resolved by: #M
   (<by>, <ts>, "<note>")" linking to record M.
2. Detail page of a RESOLVED record shows "Resolves: #N" linking
   to the original incident.
3. Records that are neither incidents nor resolutions show no
   Incident panel.

## Dev Agent Record

### Completion Notes List

- `SQLiteAdapter.find_by_record_hash(hex)` + `resolution_records_for(hex)`.
- Detail view passes `resolves_target` + `resolved_by` to template.
- `detail.html` "Incident" panel renders both cross-link types.
- 3 / 3 tests green.

### File List

- `ulog/web/viewer/adapters.py` — 2 new helpers
- `ulog/web/viewer/views.py` — context
- `ulog/web/templates/ulog/detail.html` — Incident panel
- `tests/test_incidents_detail_links.py` (NEW)
