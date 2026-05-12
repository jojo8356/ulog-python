# Story 6.8: Sidebar "Incidents" section quick filters

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-8-sidebar-incidents-section-quick-filters`
**Implements:** FR115.
**Depends on:** Epic 5 (resolve / reopen / compute_states).

## Story

As a viewer user wanting to triage incidents,
I want a sidebar "Incidents" section with quick filters: Open /
Closed (last 7d) / Reopened,
so that I can focus on what needs attention.

## Acceptance Criteria

1. Sidebar shows "Incidents" section with 3 radio choices + "All".
2. Each choice shows a per-state count.
3. Selecting "Open" filters records to currently-open incidents.
4. Selecting "Reopened" filters to reopened incidents (excludes
   never-resolved).
5. Selecting "Closed (last 7d)" filters to incidents closed within
   the last week.
6. JSONL / CSV adapters (no chain) → section hidden.

## Dev Agent Record

### Completion Notes List

- `Filters.incident_state` field; parsed from `?incident_state=...`.
- View helper `_apply_incident_state_filter` walks states once,
  builds per-state counts, post-filters records.
- `list.html` Incidents block (radio choices + counts).
- 4 / 4 tests green; compute_states bugfix
  (order-agnostic — sort by chain_pos ASC) shipped here.

### File List

- `ulog/web/viewer/adapters.py` — Filters.incident_state
- `ulog/web/viewer/views.py` — `_apply_incident_state_filter`
- `ulog/web/templates/ulog/list.html` — Incidents sidebar block
- `ulog/_incidents.py` — `compute_states` sort fix
- `tests/test_incidents_sidebar.py` (NEW)
