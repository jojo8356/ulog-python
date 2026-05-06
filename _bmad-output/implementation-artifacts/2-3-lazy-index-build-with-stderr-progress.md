# Story 2.3: Lazy index build with stderr progress

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-3-lazy-index-build-with-stderr-progress`
**Implements:** FR71 (lazy build + progress), NFR-PERF-30 (≤5s for 100K records / 30 files)
**Source:** PRD-v0.4 §3.1 FR71, §4 NFR-PERF-30; epics.md Story 2.3
**Built on:** Stories 2.1 (`AuthorIndex.build_for_pairs`), 2.2 (CLI flags resolved before this runs)

## Story

As a **viewer user opening a 100K-record DB for the first time**,
I want **the index to build at startup with progress printed to stderr**,
so that **I see what's happening during the ≤5s startup budget rather than staring at a blank terminal.**

## Acceptance Criteria

### AC1 — Adapter exposes `unique_file_line_pairs()`

`SQLiteAdapter.unique_file_line_pairs()` runs `SELECT DISTINCT file, line FROM logs` and yields `(file: str, line: int)`. `JSONLAdapter` / `CSVAdapter` iterate records and deduplicate in memory.

### AC2 — `build_index_at_startup(adapter, repo)` populates the singleton

Helper `build_index_at_startup(adapter, repo, *, progress_stream=sys.stderr) -> AuthorIndex` collects pairs, groups by file, runs `idx.build_for_pairs(pairs)`, and stores the result in module-level `_AUTHOR_INDEX`. Returns the populated `AuthorIndex`.

### AC3 — Progress lines on stderr

While building, the function emits progress lines like `ulog: indexing authors... 30 files, 12500/100000 records (12%)`. Frequency: every ~10% of records OR every file boundary (whichever is sparser). Final line: `ulog: indexed 100000 records across 30 files in 4.21s` (mock-friendly with float).

### AC4 — `set_global_index` / `get_global_index` accessors

Module-level singleton accessors so Django views (Story 2.6+) can pick up the populated index without re-importing the build orchestrator.

### AC5 — CLI integration

`ulog/web/cli.py::main` calls `build_index_at_startup(...)` when `repo is not None and not args.no_author_index`. Errors during build do NOT abort the CLI — they print a stderr warning and continue with the index empty (records will show `<unknown>`).

### AC6 — Tests cover extract + build + progress

`tests/test_lazy_index_build.py` covers AC1-AC4. CLI integration is covered structurally (Story 2.2 already verified env-var plumbing).

## Tasks / Subtasks
- [x] Task 1 — Add `Adapter.unique_file_line_pairs()` to base + SQLiteAdapter + JSONLAdapter + CSVAdapter
- [x] Task 2 — Add `build_index_at_startup()`, `set_global_index()`, `get_global_index()` to `blame.py`
- [x] Task 3 — Wire CLI call after `_set_env_for_django(...)` and before Django setup
- [x] Task 4 — Tests covering AC1-AC4
- [x] Task 5 — Full suite green

## Dev Notes
- Singleton lives in `blame.py` as module-level `_AUTHOR_INDEX: AuthorIndex | None`. The viewer is single-process (Django dev runserver with `threading=True`) so a module-level attribute is shared across requests.
- Progress emit cadence: keep it bounded so we don't spam (e.g. every 10% of records, or every file boundary if files are < 10% of total).
- AC5: surround the build call with `try/except Exception` — the build path uses `subprocess.run`, file I/O, and the user's git binary; any of those can fail in unexpected environments. Print `ulog-web: author index build failed: <e>; records will show <unknown>` and continue.
- We do NOT persist to a cache table here — that's Story 2.4. For now the index is in-memory only; restarting the viewer rebuilds.

## Dev Agent Record
### File List
- `ulog/web/viewer/adapters.py` — added `unique_file_line_pairs()` to all three adapters
- `ulog/web/viewer/blame.py` — added `_AUTHOR_INDEX`, `set_global_index`, `get_global_index`, `build_index_at_startup`
- `ulog/web/cli.py` — wired `build_index_at_startup` call before Django setup
- `tests/test_lazy_index_build.py` — NEW, 7 tests

### Completion Notes
All ACs verified. Suite at 207 + 7 = 214 green.
