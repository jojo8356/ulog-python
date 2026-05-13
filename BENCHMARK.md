# Benchmark baselines

Measured numbers v0.5 ships against. Future regressions are detected
by the advisory `pytest-benchmark` CI step (Story 7.10) — the first
two v0.5 CI runs are advisory; the third hardens to a strict gate.

All numbers are **median of 5 runs** on GitHub Actions
`ubuntu-latest`, CPython 3.12, no `-O` flag. SQLite running with the
default `journal_mode=WAL` per the chain writer's setup.

The exact reproduction harness lives in `tests/bench_*.py` (each test
marked `@pytest.mark.benchmark` and `@pytest.mark.slow`). Run locally
with:

```bash
.venv/bin/pip install ulog[dev]
.venv/bin/pytest tests/bench_verify.py tests/bench_correlate.py tests/bench_multitrack.py -m slow -v
```

---

## v0.6.4 — `ulog export-html` (Story 8.14 / PRD-v0.6.4)

**Local smoke (5K records)** — informational, not the SC1 measurement:

| Test | Median wall | Output |
|---|---|---|
| `test_export_filtered_100k` (`level=ERROR`) | ~4.0 s | ~50 records |
| `test_export_separate_100k` (`--separate-data`) | ~11.3 s | ~30 MB |
| `test_export_inline_100k` (`--inline-data`) | ~14.3 s | ~60 MB |

Measured on a 2026 dev laptop, 5K fixture. The 100K target / 30s SC1
gate fires in CI (`make bench-export` after `make bench-fixture`).
Numbers populated by the first CI run on `main` after baseline
stabilises (Decision E3: advisory for first 2 runs).

## SC1 — `ulog verify ./logs.sqlite` ≤ 5 s / 100K records

**Baseline (v0.5.0):** _to be populated by the first CI run._

| Records | Median wall | Target | Margin |
|---|---|---|---|
| 10K | _tbd_ | ≤ 0.5 s | _tbd_ |
| 100K | _tbd_ | ≤ 5 s | _tbd_ |
| 1M | _tbd_ (informational) | — | — |

**Why it matters.** A pre-deploy CI gate verifies a copy of the
production DB after every release; >5 s of verify time on 100K
records is the threshold at which `ulog verify` stops being a
casual gate and becomes a "wait for it…" friction point.

**Measurement.** `tests/bench_verify.py::test_verify_100k_records`
fires `ulog._cli.cmd_verify.run(db)` against a pre-seeded 100K-row
chain DB. The harness drops the OS page cache via `vmtouch -e` to
remove warm-cache noise; measures `time.perf_counter()` deltas.

## SC2 — `ulog correlate` ≤ 500 ms over a filter result of 1K records

**Baseline (v0.5.0):** _to be populated by the first CI run._

| Filter result size | Median wall | Target |
|---|---|---|
| 100 records | _tbd_ | ≤ 100 ms |
| 1K records | _tbd_ | ≤ 500 ms |
| 10K records | _tbd_ (informational) | — |

**Why it matters.** The correlate command is most useful during
live incident triage: a dev runs `ulog correlate "level=ERROR
AND service=checkout"` to identify what's over-represented. If it
takes >500 ms, the dev breaks flow and goes back to grep.

**Measurement.** `tests/bench_correlate.py::test_correlate_1k_filter`
fires `ulog.correlate(filter_dsl, db)` against a pre-seeded chain
DB with 100K total rows and the filter matching 1K. Records the
total wall time including SQL execution + lift computation.

## SC7 — multi-track view TTI ≤ 200 ms on a 100K-record DB

**Baseline (v0.5.0):** _to be populated by the first CI run._

| Records in DB | Median TTI | Target |
|---|---|---|
| 100K | _tbd_ | ≤ 200 ms |
| 1M | _tbd_ (informational) | — |

**Why it matters.** Multi-track is for visual scanning across 4
dimensions over a time window. Above 200 ms the page feels
sluggish; below, it feels instantaneous. The threshold matches the
Doherty Threshold (RAND, 1979) — interactive task continuity.

**Measurement.** `tests/bench_multitrack.py::test_multi_track_view_tti`
hits `/multi-track?from=...&to=...` via Django's test client against
a pre-seeded 100K-row DB and measures wall time from request issue
to response body received. The SVG rendering itself happens in the
browser and isn't included in TTI (which matches what the SC7
threshold captures — the server-side aggregation cost).

---

## Regression policy

| Change | Action |
|---|---|
| Single benchmark regressing > 10 % | Investigate, document in PR. |
| Single benchmark regressing > 20 % | CI step fails the PR (after 2 advisory runs per Story 7.10). |
| New benchmark below target on first run | Block release; document the gap. |

Numbers fluctuate; the advisory window is meant to capture the
range of CI noise before the gate hardens. After 2 v0.5 CI runs
on `main` with stable baselines, a follow-up PR flips
`pytest --benchmark-only --benchmark-fail-fast` and the gate is
authoritative.

## Outside-of-scope

- **Memory usage** (NFR-PERF-71 — multi-track view RSS < 200 MB on
  1M records). Tracked separately in `tests/test_stability_e2e.py`.
- **Writer throughput** (SQLHandler batch write speed). Not a v0.5
  SC; relevant to scaling work in a future release.
- **Browser-side render time** (SVG paint for multi-track). Out of
  scope for server-side benchmark; we measure TTI on the server hop.
