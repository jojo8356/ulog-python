# Story 9.7: PRD, changelog, and BMAD alignment

Status: done

**Epic:** 9 — BMAD catch-up ledger (v0.7 → v0.9)

## Scope Recorded

- Align BMAD implementation tracking with already-shipped PRDs v0.7, v0.8, v0.8.1, and v0.9.
- Add `_bmad-output/planning-artifacts/epic-9.md`.
- Add Story 9.1 through 9.6 artifacts.
- Update `_bmad-output/implementation-artifacts/sprint-status.yaml`.

## Source-of-Truth Checks

- `CHANGELOG.md` contains shipped sections for:
  - v0.7.0
  - v0.8.0
  - v0.8.1
  - v0.9.0
- `docs/prds/index.md` marks those PRDs shipped.
- Tests exist for each shipped surface.

## Decision

Epic 9 is intentionally a catch-up ledger, not a new implementation epic. It prevents future planning from treating v0.7-v0.9 as untracked work while keeping the historical commits intact.

## Verification

No production code was changed for this story. Verification is documentation/traceability-only:

- new BMAD artifacts exist for Story 9.1 through Story 9.7
- `sprint-status.yaml` includes `epic-9: done`
