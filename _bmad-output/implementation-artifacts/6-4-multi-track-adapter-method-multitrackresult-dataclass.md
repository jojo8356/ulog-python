# Story 6.4: Multi-track adapter method + `MultiTrackResult` dataclass

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-4-multi-track-adapter-method-multitrackresult-dataclass`
**Implements:** FR112 (data layer), Decision D1.

## Story

As a viewer backend,
I want each adapter (SQLite/JSONL/CSV) to expose
`multi_track(filters, tracks, window_start, window_end, bucket_size_s) -> MultiTrackResult`,
so that the multi-track view stays storage-agnostic.

## Acceptance Criteria

1. `MultiTrackResult(tracks: dict[str, list[BucketCount]], window:
   tuple[datetime, datetime], bucket_size_s: int)` is defined.
2. `BucketCount(bucket: str, value: str, count: int)` is defined (`bucket`
   = ISO minute key, `value` = the category value, `count` = number of
   records).
3. SQLite adapter uses SQL `GROUP BY strftime('%Y-%m-%dT%H:%M', ts),
   <track>` per Decision D1.
4. JSONL/CSV adapters use `collections.Counter` (in-Python).
5. Requested tracks always present in `result.tracks`, even when empty
   (UI shows `(no data)` placeholder per PRD-v0.5 §2.1.6).
6. Supported tracks: `level`, `service`, `file` natively. `author`
   returns `[]` from the adapter layer — Story 6.5 plumbs via blame.
7. `bucket_size_s` stored on result; v0.5 supports `60` (per-minute).
8. Tests cover SQLite/JSONL/CSV; window edges; empty result; unknown
   track name → KeyError.

## Dev Agent Record

### Completion Notes List

- New module `ulog/web/viewer/multi_track.py` exporting
  `BucketCount`, `MultiTrackResult`, `SUPPORTED_TRACKS`.
- Adapter base `multi_track(...)` raises NotImplementedError.
- SQLite uses SQL `GROUP BY strftime('%Y-%m-%dT%H:%M', ts), <track>`,
  with `service` resolved via `json_extract(context, '$.service')`.
- JSONL/CSV iterate in-process with `Counter`.
- 10 / 10 tests green.

### File List

- `ulog/web/viewer/multi_track.py` (NEW)
- `ulog/web/viewer/adapters.py` — `multi_track(...)` on each adapter
- `tests/test_multi_track_adapter.py` (NEW)
