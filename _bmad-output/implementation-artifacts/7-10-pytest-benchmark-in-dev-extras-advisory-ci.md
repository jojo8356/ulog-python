# Story 7.10: pytest-benchmark in `[dev]` extras + advisory CI

Status: done

**Epic:** 7 — v0.5 release consolidation
**Implements:** Decision E3.

## Completion Notes

- `pyproject.toml` `[dev]` extra now includes `pytest-benchmark>=4.0`.
- Deptry rules updated: `DEP002` lists `pytest-benchmark` (plugin
  registered via entry point, never imported); module map adds
  `pytest-benchmark = "pytest_benchmark"`.
- CI workflow `benchmarks` job runs `pytest -m slow -q tests/bench_*.py`
  with `continue-on-error: true` — advisory for first 2 v0.5 runs.
- Follow-up PR after baselines stabilize: flip to strict (drop the
  `||` fallback and `continue-on-error`).

## File List

- `pyproject.toml`
- `.github/workflows/ci.yml`
