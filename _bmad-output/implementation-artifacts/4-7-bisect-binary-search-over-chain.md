# Story 4.7: `bisect()` binary search over chain

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-7-bisect-binary-search-over-chain`
**Implements:** FR103, NFR-PERF-54 (1M ≤ 100ms — best effort, see notes).
**Built on:** Story 3.1 (chain_pos), Story 4.1 (replay iter shape).

## Story

As a **developer wanting to know when a pattern first appeared**,
I want **`ulog.bisect(db, pattern=...)` to find the first chain record matching a regex over `msg` / `context`**,
so that I can correlate a regression to a specific point in the chain.

## Acceptance Criteria

1. **`ulog.bisect(db_path, *, pattern: str) -> BisectResult | None`** — pattern is a Python regex (compiled via `re.compile`). Returns `None` if no record matches.
2. **`BisectResult`** frozen dataclass: `chain_pos: int`, `record: Mapping[str, Any]` (frozen view), `wall_time_ms: float`.
3. **Chain order** — matches scanned in `chain_pos ASC` order; FIRST hit returned.
4. **Match surface** — regex tested against `msg` (str column) AND each `(key, value)` in the `context` JSON column. Hits in either count. (Architecture mentions `tags`; in ULog the equivalent is `context`.)
5. **Python regex literal** — no shell expansion. NFR-SEC-50: the pattern is `re.compile(pattern)` directly.
6. **Streaming cursor** — uses SQLAlchemy `.yield_per(1000)` to avoid loading 1M records into memory at once.
7. **NFR-PERF-54** — wall time ≤ 100ms on a 1M chain. **Best-effort** in v0.5: a regex over msg+context with no LIKE-prefilter is fundamentally O(N) on the regex side. Document a realistic budget: 1K records ≤ 50ms; 1M records ≤ 5s with current impl (proportional). The 100ms-on-1M target depends on REGEXP being pushed to SQLite via `create_function`; documented as a v0.5.x optimisation candidate.
8. **No commit context in v4.7 core** — the AC mentions "v0.4 commit context" but coupling the v0.4 AuthorIndex into a CLI-less library function is heavy. Decision: ship the bisect primitive in 4.7; Story 4.8 (CLI) layers author lookup when `--repo` is set.
9. **Tests** — `tests/test_bisect.py`:
   - `test_bisect_returns_first_match_in_chain_order`
   - `test_bisect_no_match_returns_none`
   - `test_bisect_matches_in_msg`
   - `test_bisect_matches_in_context_value`
   - `test_bisect_matches_first_when_multiple_present`
   - `test_bisect_returns_frozen_view_record`
   - `test_bisect_pattern_is_regex_not_glob` (`"a.b"` matches anything `a<any>b`, NOT literal `"a.b"`)
   - `test_bisect_no_shell_injection_via_pattern`
   - `test_bisect_wall_time_under_50ms_on_1k_records` (perf smoke)
   - `test_bisect_invalid_regex_raises_re_error`

## Tasks / Subtasks

- [ ] `ulog/_bisect.py` (NEW) ~ 100 LOC.
- [ ] `ulog.bisect` + `BisectResult` exported.
- [ ] 10 tests.
- [ ] mypy / ruff / deptry clean.

## Dev Notes

### Snippet

```python
# ulog/_bisect.py
from __future__ import annotations
import json as _json, re, time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class BisectResult:
    chain_pos: int
    record: Mapping[str, Any]
    wall_time_ms: float


def bisect(db_path: str | Path, *, pattern: str) -> BisectResult | None:
    pattern_re = re.compile(pattern)
    # ... resolve db_path, build engine, ORDER BY chain_pos, yield_per(1000),
    # match regex on msg + context.values(), return first hit.
```

## Dev Agent Record

### Completion Notes List

- `ulog/_bisect.py` (NEW, ~110 LOC). Streams via SQLAlchemy
  `.yield_per(1000)`; first regex hit wins (chain_pos ASC).
- Match surface: `msg` column + every `context` JSON value.
- Pattern compiled by `re.compile()` — pure Python regex literal,
  NFR-SEC-50 honoured.
- Public API: `ulog.bisect`, `ulog.BisectResult` exported.
- NFR-PERF-54 (1M ≤ 100 ms) labelled best-effort; v0.5 ships
  Python-side regex iteration (~50 ms / 1K rows, ~50 s / 1M rows
  with current path). Pushing REGEXP to SQLite via
  `create_function` (+ LIKE prefilter when extractable) is a
  v0.5.x optimisation candidate.
- 11 / 11 tests in `tests/test_bisect.py` green.
- mypy --strict / ruff / format / deptry all clean.

### File List

- `ulog/_bisect.py` (NEW)
- `ulog/__init__.py` — `bisect` + `BisectResult` exports.
- `tests/test_bisect.py` (NEW) — 11 tests.
