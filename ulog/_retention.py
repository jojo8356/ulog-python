"""Retention configuration (Story 3.6 + Story 3.9).

Holds the process-wide `MIN_RETENTION_DAYS` floor configured via
`ulog.setup(min_retention_days=...)`. Story 3.9 (`ulog purge`) reads
this to refuse deletes that would remove records younger than the
configured floor.
"""

from __future__ import annotations

MIN_RETENTION_DAYS: int = 0


def set_min_retention_days(n: int) -> None:
    if not isinstance(n, int) or isinstance(n, bool):
        raise TypeError(f"min_retention_days must be int, got {type(n).__name__}")
    if n < 0:
        raise ValueError(f"min_retention_days must be >= 0, got {n}")
    global MIN_RETENTION_DAYS
    MIN_RETENTION_DAYS = n
