# Story 2.13: Viewer perf hotpath — memoize + GROUP BY for AuthorsSummary

Status: done

**Epic:** 2 — v0.4 Author attribution (POST-EPIC perf patch)
**Story key:** `2-13-perf-hotpath-authors-summary-memoize`
**Implements:** PRD-v0.4.1 (page-load < 3s)
**Source:** `docs/prds/PRD-v0.4.1-viewer-perf-hotpath.md`
**Discovered:** 2026-05-06 — user generated a 43K-record demo DB; page took 4.2s to load (cold) and 5.4s with author filter. The bottleneck was `compute_authors_summary` walking all records on every request.

## Story
As a viewer user with a realistic-size log dataset (10K-100K records), I want every page load to complete in under 3s, so the UI feels responsive.

## Acceptance Criteria

- **AC1** — Cold-cache `GET /` on 43K-record demo DB returns HTTP 200 in **< 3.0s**.
- **AC2** — Warm-cache subsequent requests on same DB+idx return in **< 1.0s**.
- **AC3** — `set_global_index(...)` invalidates the summary cache.
- **AC4** — DB file mtime change invalidates the cache (next request recomputes).
- **AC5** — All 266 prior tests still pass.
- **AC6** — `AuthorsSummary` content invariants preserved (sorted known-by-count desc, `<unknown>` last).

## Optimizations applied

1. **Module-level memoization** — `_AUTHORS_SUMMARY_CACHE: tuple[(db_mtime, id(idx)), AuthorsSummary] | None`. Hit on every request after the first.
2. **Iterate `(file, line, count)` tuples instead of records** — `Adapter.file_line_record_counts()` (SQL `GROUP BY file, line` for SQLite, `Counter` for JSONL/CSV). Reduces 43K iterations to ~5878 unique pairs.
3. **`invalidate_authors_summary_cache()` public helper** — for tests and any future hook that knows the DB content has changed.

## Measurements (43K-record demo DB)

| Path | Before | After | Speedup |
|---|---|---|---|
| Cold cache `GET /` | 4.2s | **0.65s** | 6.4× |
| Warm cache `GET /` | 4.0s | **0.12s** | 35× |
| `GET /?level=ERROR` (warm) | 4.0s | **0.12s** | 35× |
| `GET /?author=alice@globex.io` (warm) | 5.4s | **1.68s** | 3.2× |
| `GET /r/100/` (detail view) | n/a | **0.03s** | — |
| `GET /?page=10` (pagination) | n/a | **0.15s** | — |

## Tasks
- [x] Add `Adapter.file_line_record_counts()` to base + 3 impls (SQLite GROUP BY; JSONL/CSV Counter)
- [x] Refactor `compute_authors_summary` to iterate `(file, line, count)` tuples
- [x] Add module-level `_AUTHORS_SUMMARY_CACHE` keyed by `(db_mtime, id(idx))`
- [x] Wire `set_global_index` to call `invalidate_authors_summary_cache()`
- [x] Patch `tests/test_authors_summary.py::test_summary_unknown_always_last` — line numbers start at 1 (Python logging convention; matches the `r.line > 0` adapter filter)
- [x] Verify suite green + curl benchmark < 3s

## Dev Agent Record

### File List
- `ulog/web/viewer/adapters.py` — `Adapter.file_line_record_counts` + 3 implementations
- `ulog/web/viewer/blame.py` — `_AUTHORS_SUMMARY_CACHE`, `_adapter_db_mtime`, `invalidate_authors_summary_cache`, refactored `compute_authors_summary`; `set_global_index` invalidates
- `tests/test_authors_summary.py` — patched line range from `range(5)` → `range(1, 6)`
- `docs/prds/PRD-v0.4.1-viewer-perf-hotpath.md` — NEW PRD

### Completion Notes
266/266 green. Curl benchmark on 43K-record demo DB confirmed:
- cold 0.65s, warm 0.12s, author-filter 1.68s — all under the 3s target.

The author-filter path (1.68s) is dominated by `adapter.query(page_size=10_000_000)` loading all records for post-filter pagination (not by author resolution). v0.5 will push this to SQL `JOIN authors` — out of scope for v0.4.1.

### Risk Assessment
- **Cache staleness**: keyed by file mtime. If a process holds an open SQLite connection that buffers writes (e.g. WAL), mtime may lag. Mitigation: explicit `invalidate_authors_summary_cache()` on `set_global_index` covers the singleton-swap path; an explicit DB-write would have to invalidate too if added in v0.5+.
- **Memory**: cache holds one `AuthorsSummary` (≤ ~50 KB even for 1000-author fleets). Bounded.
- **Correctness**: ghost-count semantics (FR79) preserved — summary is invariant across filter axes, so caching is safe.
