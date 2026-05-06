---
docType: prd
project_name: ulog-python
version: 0.4.1
date: 2026-05-06
author: jojo8356
status: implementing
parent_prd: PRD-v0.4-commit-author-filter.md
---

# ULog v0.4.1 — Viewer perf hotpath (page-load < 3s)

> Post-Epic 2 perf patch. The Author attribution feature shipped with
> a `compute_authors_summary` walk over **all records** on every page
> load — for a 43K-record demo DB this dominates wall-time at ~4s.
> Target: every page load under **3s**, including first-hit.

## 0. Problem

Profile of `/` on the 43K-record demo DB (after the negative-cache fix):

| Component | Time |
|---|---|
| `adapter.query(page=1, page_size=100)` | 60ms |
| `compute_authors_summary` | **4 150ms** ← dominant |
| Template render + misc | ~150ms |
| **Total wall-time** | **~4.4s** |

`compute_authors_summary` does:
1. `adapter.query(Filters(), page=1, page_size=10_000_000)` — loads ALL 43K records into memory
2. for each record, `idx.author_for(record.file, record.line)` — 43K dict lookups + 43K mtime stats

Both are O(N) over total records. The aggregation is invariant across filter axes (per FR79 ghost-count rule), so it's wasted work on every request.

## 1. Vision

Two structural fixes:

### 1.1 Memoize `AuthorsSummary` per (DB-mtime, idx) pair

The summary depends only on the underlying log dataset + index — NOT on the user's filter selection. Cache it at module scope, invalidate when the DB file's mtime changes (or when `set_global_index(...)` swaps the idx).

Expected gain: **~4 000ms → <5ms** on cache hit (i.e. every request after the first).

### 1.2 Iterate unique `(file, line)` pairs via SQL `GROUP BY`, not records

The summary aggregates by author. Multiple records sharing the same `(file, line)` resolve to the same author. Walking 43K records to look up 5878 unique pairs is 7× wasted work.

Add `Adapter.file_line_record_counts() -> Iterable[(file, line, count)]` so `compute_authors_summary` walks 5878 pairs (not 43K records) and multiplies counts.

Expected gain on cold-cache: **~4 000ms → ~600ms** (proportional to unique-pair / record ratio).

## 2. Scope

### 2.1 In scope

1. `_AUTHORS_SUMMARY_CACHE: tuple[Key, AuthorsSummary] | None` module-level, keyed by `(db_mtime, id(idx))`.
2. `set_global_index(...)` invalidates the summary cache as a side effect.
3. `Adapter.file_line_record_counts()` — abstract method.
4. `SQLiteAdapter` impl: SQL `SELECT file, line, COUNT(*) FROM logs GROUP BY file, line`.
5. `JSONLAdapter` / `CSVAdapter` impl: `Counter` over the in-memory record list.
6. `compute_authors_summary` rewrite: walk pairs+counts instead of records.

### 2.2 Out of scope (deferred)

- SQL `JOIN` with `authors` table for the author filter post-query path (still walks 43K to filter). v0.5 candidate; current 1.15s is acceptable for the budget.
- Any change to the indexer cache layer.
- Any UI change.

## 3. Acceptance

- **AC1** — `time curl http://localhost:NNNN/` on 43K-record DB returns HTTP 200 in **< 3.0s** (cold cache, first request).
- **AC2** — Subsequent requests on same DB+idx return in **< 1.0s** (cache hit).
- **AC3** — `set_global_index(None)` invalidates the cache; next `compute_authors_summary(...)` rebuilds.
- **AC4** — Touching the DB file's mtime invalidates the cache.
- **AC5** — All 266 existing tests still pass.
- **AC6** — New tests cover memoization (hit/invalidate paths) and the new `file_line_record_counts` adapter method.

## 4. Non-functional

- **NFR-DEP**: zero new dependencies (preserves SC4).
- **NFR-CORRECTNESS**: ghost-count semantics (FR79) preserved — summary is still computed against all-filters-MINUS-author.
- **NFR-MEMORY**: cache holds one `AuthorsSummary` ≤ ~50 KB for typical fleets; bounded.

## 5. Implementation plan

1. Add `file_line_record_counts()` to base `Adapter` + 3 impls.
2. Refactor `compute_authors_summary` to iterate counts.
3. Add module-level memoization with `(db_mtime, id(idx))` key.
4. Wire `set_global_index` to invalidate.
5. Test: cache hit, mtime invalidation, idx swap.
6. Verify on demo DB via curl: < 3s cold, < 1s warm.

## 6. Definition of Done

✅ All ACs pass
✅ Demo DB curl < 3s cold, < 1s warm
✅ 266 + new tests green
✅ Story 2-13 spec filed in `_bmad-output/implementation-artifacts/`
