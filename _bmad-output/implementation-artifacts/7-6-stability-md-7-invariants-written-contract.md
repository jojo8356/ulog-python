# Story 7.6: STABILITY.md — 7 invariants written contract

Status: done

**Epic:** 7 — v0.5 release consolidation

## Completion Notes

- Repo-root `STABILITY.md` lists I1-I7 (auto-class, local-first,
  verify-offline, immutable-hard, stdlib-compat, untagged-works,
  no-phone-home) with one-paragraph rationale each.
- Contract-scope section clarifies what's vs not under the
  guarantee (core, storage, chain integrity → IN; web UI layout,
  PRDs, pre-1.0 minors → OUT).
- "Where this is enforced" table maps each invariant to the test
  file / CI gate that mechanically checks it.

## File List

- `STABILITY.md` (NEW)
