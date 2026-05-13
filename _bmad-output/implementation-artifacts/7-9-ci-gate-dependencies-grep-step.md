# Story 7.9: CI gate — `dependencies = []` grep step

Status: done

**Epic:** 7 — v0.5 release consolidation
**Implements:** Decision E2 (NFR-DEP-50 / SC4).

## Completion Notes

- `.github/workflows/ci.yml` added with 3 jobs:
  - `test` (matrix py3.10-3.13: ruff, ruff format, mypy --strict,
    deptry, pytest).
  - `regression-gate-zero-deps` — fails if `pyproject.toml`'s
    `dependencies` line isn't `[]`.
  - `benchmarks` (advisory; depends on `test`).

## File List

- `.github/workflows/ci.yml` (NEW)
