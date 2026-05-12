# Story 5.3: Incident state walk (chain-derived latest-wins)

Status: done

**Epic:** 5 — v0.5 Incident lifecycle
**Story key:** `5-3-incident-state-walk-chain-derived-latest-wins`
**Implements:** FR106 (latest-wins).

## Story

As a UI or CLI consumer needing the open/closed state,
I want a pure function that walks the chain and returns the current
state of each incident,
so that the latest-wins semantics is implemented in one place.

## Acceptance Criteria

1. `ulog.compute_states(records)` returns
   `dict[incident_hash, IncidentState]`.
2. `IncidentState(incident_hash, state, last_action, opened_ts,
   last_action_ts)` is exported.
3. State values: `"open"` | `"closed"` | `"reopened"`.
4. Incident candidates: every record with `level in (ERROR, CRITICAL)`,
   plus any record explicitly referenced via `context.resolves`.
5. Latest action wins (last RESOLVED/REOPENED row by chain_pos).

## Dev Agent Record

### Completion Notes List

- Pure function `compute_states(records)` in `ulog/_incidents.py`.
- Tests cover open / closed / reopened / latest-wins paths.

### File List

- `ulog/_incidents.py`
- `ulog/__init__.py` — re-export
- `tests/test_incidents.py`
