"""First-match scan over the chain in chain_pos order (Story 4.7).

`bisect(db, pattern="...")` walks records in chain_pos ascending order
and returns the first one whose `msg` OR any `context` value matches
the regex. Streams via SQLAlchemy `.yield_per(1000)` so a 1M-record
chain doesn't load into memory.

Performance note: NFR-PERF-54 targets ≤ 100 ms on 1M records. The
current implementation runs the regex Python-side; realistic budget
is proportional to chain length (~50 ms / 1K rows). Pushing REGEXP
to SQLite via `create_function` (and combining with a LIKE prefilter
when the pattern allows) is a v0.5.x optimisation — documented as
out of v0.5.0 core scope.

The pattern is a Python regex literal — no shell expansion, no eval
(NFR-SEC-50).
"""

from __future__ import annotations

import json as _json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class BisectResult:
    """First chain record matching the pattern + wall-time."""

    chain_pos: int
    record: Mapping[str, Any]
    wall_time_ms: float


def bisect(db_path: str | Path, *, pattern: str) -> BisectResult | None:
    """Return the first chain record whose msg / context matches `pattern`.

    Args:
        db_path: SQLite path (Path / str) OR `sqlite:///...` URL.
        pattern: Python regex (compiled via `re.compile`).

    Returns:
        `BisectResult` for the first hit (ordered by chain_pos ASC),
        or `None` if no record matches.

    Raises:
        re.error: invalid regex pattern.
        FileNotFoundError: db_path doesn't exist.
    """
    pattern_re = re.compile(pattern)
    url = _resolve_db_url(db_path)

    from sqlalchemy import create_engine, text

    from ._chain import parse_stored_ts

    engine = create_engine(url, future=True)
    t0 = time.perf_counter()
    sql = (
        "SELECT id, chain_pos, ts, level, logger, msg, file, line, "
        "exc, context, immutable, record_hash, prev_hash "
        "FROM logs ORDER BY chain_pos ASC"
    )
    result: BisectResult | None = None
    with engine.connect() as conn:
        for row in conn.execute(text(sql)).yield_per(1000):
            if _matches(row, pattern_re):
                record: dict[str, Any] = {
                    "id": row[0],
                    "chain_pos": row[1],
                    "ts": parse_stored_ts(row[2]),
                    "level": row[3],
                    "logger": row[4],
                    "msg": row[5],
                    "file": row[6],
                    "line": row[7],
                    "exc": _json.loads(row[8]) if isinstance(row[8], str) else row[8],
                    "context": _json.loads(row[9]) if isinstance(row[9], str) else row[9],
                    "immutable": row[10],
                    "record_hash": bytes(row[11]) if row[11] is not None else None,
                    "prev_hash": bytes(row[12]) if row[12] is not None else None,
                }
                result = BisectResult(
                    chain_pos=int(row[1]),
                    record=MappingProxyType(record),
                    wall_time_ms=(time.perf_counter() - t0) * 1000,
                )
                break
    engine.dispose()
    return result


def _matches(row: Any, pattern_re: re.Pattern[str]) -> bool:
    """Test the regex against `msg` and any `context` value."""
    msg = row[5]
    if msg is not None and pattern_re.search(str(msg)):
        return True
    ctx_raw = row[9]
    if ctx_raw is None:
        return False
    ctx = _json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
    if not isinstance(ctx, Mapping):
        return False
    return any(pattern_re.search(str(v)) for v in ctx.values())


def _resolve_db_url(db_path: str | Path) -> str:
    if isinstance(db_path, str) and db_path.startswith("sqlite:///"):
        return db_path
    p = Path(db_path) if not isinstance(db_path, Path) else db_path
    if not p.exists():
        raise FileNotFoundError(f"bisect(): DB not found at {p}")
    return f"sqlite:///{p}"
