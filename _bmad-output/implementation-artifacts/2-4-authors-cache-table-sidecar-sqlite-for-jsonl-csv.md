# Story 2.4: `authors` cache table + sidecar SQLite for JSONL/CSV

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-4-authors-cache-table-sidecar-sqlite-for-jsonl-csv`
**Implements:** FR72 (cache table schema), Decision A3 (sidecar `<logs>.authors.sqlite` for JSONL/CSV)
**Source:** PRD-v0.4 §3.1 FR72, architecture.md A3 + line 349
**Built on:** Stories 2.1, 2.3

## Story
As a viewer user reloading the same log file, I want author attribution loaded from a cache instead of re-blaming git, so subsequent loads are instant.

## Acceptance Criteria
- **AC1** — `authors` table schema: `(file TEXT, line INTEGER, author_name TEXT, author_email TEXT, commit_sha TEXT, commit_ts INTEGER, PRIMARY KEY (file, line))`. Created on first persist. SQLite-backed.
- **AC2** — For SQLite log sources, `authors` lives in the SAME DB as `logs`.
- **AC3** — For JSONL/CSV log sources, `authors` lives in a sidecar `<logs>.authors.sqlite` next to the source.
- **AC4** — `AuthorIndex.persist(db_path)` writes the in-memory cache to the table (REPLACE on conflict).
- **AC5** — `AuthorIndex.load(db_path)` populates the in-memory cache from the table, returns `True` if any rows loaded.
- **AC6** — `build_index_at_startup` tries `load(...)` first; on empty cache (or `--rebuild-author-index`), runs the fresh build then `persist(...)`.
- **AC7** — `cache_path_for(adapter)` returns the right path: the SQLite log DB itself for SQLiteAdapter, the sidecar `.authors.sqlite` for JSONL/CSV.
- **AC8** — Tests cover persist+reload roundtrip, sidecar resolution, rebuild flag.

## Tasks
- [x] Add `Author` persist/load helpers to `blame.py`
- [x] Add `cache_path_for(adapter) -> Path` helper
- [x] Wire `build_index_at_startup` to try-load → build → persist
- [x] Honor `ULOG_AUTHOR_INDEX_REBUILD` env (passed by Story 2.2 CLI)
- [x] Tests in `tests/test_author_cache.py`

## Dev Agent Record
### File List
- `ulog/web/viewer/blame.py` — `_persist_authors`, `_load_authors`, `cache_path_for`, plus build orchestration update
- `tests/test_author_cache.py` — NEW

### Completion Notes
SQLite store uses raw `sqlite3` (stdlib, no SQLAlchemy round-trip) since the schema is fixed and the operation is bulk insert/select. Suite: 213 + 7 new = 220/220.
