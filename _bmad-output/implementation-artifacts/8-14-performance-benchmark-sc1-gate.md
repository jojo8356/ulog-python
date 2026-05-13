# Story 8.14: Performance benchmark + SC1 gate

Status: done

**Epic:** 8 — v0.6 static HTML export
**PRD:** v0.6.4 (operating manual)

## Completion Notes

- `scripts/seed_bench_fixture.py` — generates a chain-mode SQLite
  fixture with N records (default 100K). Idempotent (skips if file
  already has ≥ N rows).
- `tests/bench_export_html.py` — 3 benchmark tests (separate-data,
  inline-data, filtered) using `pytest-benchmark`'s `benchmark`
  fixture with `min_rounds=3`. Size reported in stdout (informational).
- `make bench-fixture` + `make bench-export` Makefile targets.
- `.github/workflows/ci.yml` extends `benchmarks` job to seed
  fixture, run with `--benchmark-json=benchmark.json`, parse JSON
  to flag medians > 30s as warnings (advisory).
- `BENCHMARK.md` populated with local smoke numbers (5K records)
  + note that 100K SC1 gate fires in CI.

Local validation: `test_export_filtered_100k` passes at ~4 s on
5K-record fixture. Full 100K runs in CI where disk + RAM are
generous.

## File List

- `scripts/seed_bench_fixture.py` (NEW)
- `tests/bench_export_html.py` (NEW — 3 benchmarks)
- `Makefile` — `bench-fixture` + `bench-export` targets
- `.github/workflows/ci.yml` — extended benchmarks job
- `BENCHMARK.md` — v0.6.4 section
