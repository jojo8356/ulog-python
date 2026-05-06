# Story 2.5: `<unknown>` author handling

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-5-unknown-author-handling`
**Implements:** FR75 (records referencing files not in repo → `<unknown>`)
**Source:** PRD-v0.4 §3.1 FR75; epics.md Story 2.5
**Built on:** Stories 2.1, 2.3, 2.4

## Story
As a viewer user with logs that reference files not in `--repo`, I want those records to show `<unknown>` author with a separate sidebar entry, so I can include or exclude them deliberately.

## Acceptance Criteria
- **AC1** — `compute_authors_summary(adapter, idx) -> AuthorsSummary` aggregates records into a list of `(Author | None, count)` pairs, where `None` represents `<unknown>`.
- **AC2** — Sort: known authors by count desc, then `<unknown>` last.
- **AC3** — Records where `idx.author_for(file, line)` returns `None` (untracked file or line OOR) are aggregated under the `None` key.
- **AC4** — Records where `idx is None` (no indexer at all — Story 2.2 `--no-author-index` or no-git case) are still summarized but ALL records map to `<unknown>`.
- **AC5** — Tests cover empty, all-known, mixed, and idx-None cases.

## Tasks
- [x] `AuthorsSummary` dataclass + `compute_authors_summary()` in `blame.py`
- [x] Tests in `tests/test_authors_summary.py`
- [x] Suite green

## Dev Agent Record
### File List
- `ulog/web/viewer/blame.py` — added `AuthorsSummary`, `compute_authors_summary`
- `tests/test_authors_summary.py` — NEW, 5 tests

### Completion Notes
Suite at 221 + 5 = 226/226. The aggregation walks all records via the adapter's `query()` with empty filters, then maps each record's `(file, line)` through `idx.author_for(...)`. For 100K records this is O(N) but every lookup is O(1) (cache hit) — should comfortably fit within NFR-PERF-30.
