# Story 9.5: v0.9 resource validation CLI

Status: done

**Epic:** 9 — BMAD catch-up ledger (v0.7 → v0.9)
**PRD:** `docs/prds/PRD-v0.9-resource-validity.md`
**Shipped as:** v0.9.0 phase 1

## Scope Recorded

- `ulog validate-resources --path <dir>`.
- JSON/TOML/CSV/INI parsing via stdlib.
- Optional YAML parsing when PyYAML is installed.
- `--types`, `--exclude`, and verbose output handling.
- Exit code equals number of broken resources, capped by process exit-code behavior.

## Implementation Evidence

- Commit: `03e17de` — `feat(v0.9): ulog validate-resources CLI (PRD-v0.9 phase 1)`
- Files:
  - `ulog/_cli/cmd_validate_resources.py`
  - `ulog/_cli/__init__.py`

## Regression Tests

- `tests/test_validate_resources.py`

## Notes

This artifact regularizes already-shipped work. No production code was changed while creating this BMAD record.
