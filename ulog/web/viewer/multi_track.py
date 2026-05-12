"""Multi-track aggregation primitives (Story 6.4 / FR112, Decision D1).

The "multi-track" view shows four horizontal SVG strips
(`level` / `service` / `author` / `file`) over a shared time axis. Each
strip is a bucketed count per category value.

This module ships the storage-agnostic dataclasses + the list of
supported track names. The actual aggregation is implemented per
adapter in `adapters.py` — SQLite via SQL `GROUP BY strftime(...)`,
JSONL/CSV via `collections.Counter`.

`author` is not resolvable from the raw records alone — Story 6.5
plumbs the blame index into the view layer; the adapter layer returns
`[]` for that track.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# v0.5 supports a single bucket granularity (per-minute). Kept as a
# parameter on `multi_track(...)` for future grain-flexibility.
BUCKET_SIZE_S: int = 60

# Tracks the adapter layer aggregates natively. `author` is exposed by
# the API but resolved by the view (it needs the blame index).
SUPPORTED_TRACKS: frozenset[str] = frozenset({"level", "service", "file", "author"})


@dataclass(frozen=True)
class BucketCount:
    """One (bucket, category-value) → count cell on a strip."""

    bucket: str  # ISO minute key, e.g. "2026-05-12T07:00"
    value: str  # category value — level="ERROR", service="api", ...
    count: int


@dataclass(frozen=True)
class MultiTrackResult:
    """Result of `Adapter.multi_track(...)`."""

    tracks: dict[str, list[BucketCount]]
    window: tuple[datetime, datetime]
    bucket_size_s: int
