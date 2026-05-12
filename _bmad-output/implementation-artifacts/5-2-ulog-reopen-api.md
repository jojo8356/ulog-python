# Story 5.2: `ulog.reopen()` API

Status: done

**Epic:** 5 — v0.5 Incident lifecycle
**Story key:** `5-2-ulog-reopen-api`
**Implements:** FR106 (latest-wins).

## Story

As a team lead discovering that "the fix didn't work",
I want `ulog.reopen(incident_hash, reason)` to emit a `REOPENED`
record referencing the original,
so that the incident lifecycle accurately reflects reality.

## Acceptance Criteria

1. `ulog.reopen(incident_hash, reason="")` emits a new INFO record
   with `msg="REOPENED"`, `resolves=<full hex>`, `reason=...`,
   `commit_sha=...`, `incident_action="reopen"`.
2. Same FK rules as `resolve()` — unknown hash → `LookupError`.
3. Resolve → reopen → resolve chain → state walk returns `"closed"`
   (latest-wins per FR106).

## Dev Agent Record

### Completion Notes List

- Implemented alongside Story 5.1 in `ulog/_incidents.py`.
- Tests in `tests/test_incidents.py` (`test_reopen_*`,
  `test_compute_states_latest_wins_*`).

### File List

- `ulog/_incidents.py`
- `ulog/__init__.py` — re-export
- `tests/test_incidents.py`
