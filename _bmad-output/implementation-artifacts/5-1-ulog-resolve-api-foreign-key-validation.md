# Story 5.1: `ulog.resolve()` API + foreign-key validation

Status: done

**Epic:** 5 — v0.5 Incident lifecycle
**Story key:** `5-1-ulog-resolve-api-foreign-key-validation`
**Implements:** FR105, PRD-v0.5 §2.3 (FK validation).

## Story

As a team lead closing an incident,
I want `ulog.resolve(incident_hash, by, note)` to emit a new
immutable INFO record with `resolves=<hash>`,
so that the resolution is part of the chain and references the
original.

## Acceptance Criteria

1. `ulog.resolve(incident_hash, by, note="")` looks up the chain row
   whose `record_hash` starts with `incident_hash` (hex prefix ≥ 4).
2. Match found → emits a new INFO record with `msg="RESOLVED"` and
   context `resolves=<full hex>`, `by=...`, `note=...`,
   `commit_sha=<HEAD>`, `incident_action="resolve"`.
3. No match → raises `LookupError`, no record emitted.
4. Hex prefix matches >1 record → raises `LookupError` ("ambiguous").
5. No SQLHandler configured → raises `RuntimeError`.
6. The new record is in the chain with `chain_pos = previous + 1`
   and `immutable=1` (inherited from `integrity="hash-chain"`).
7. Tests cover all 5 paths above.

## Dev Agent Record

### Completion Notes List

- New module `ulog/_incidents.py` with `resolve` + `reopen` +
  `compute_states` (Stories 5.1 / 5.2 / 5.3).
- `ulog.resolve` / `ulog.reopen` / `ulog.compute_states` / `ulog.IncidentState`
  re-exported from `ulog/__init__.py`.
- Tests pass.

### File List

- `ulog/_incidents.py` (NEW)
- `ulog/__init__.py` — re-exports
- `tests/test_incidents.py` (NEW; Stories 5.1+5.2+5.3+5.6 share)
