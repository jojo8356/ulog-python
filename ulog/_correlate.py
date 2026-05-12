"""Correlate a filter against record dimensions to find over-represented tags.

Implements FR101 / NFR-PERF-53 / SC2 (Story 4.5).

`correlate(db_path, where_dsl=...)` runs a single SQL query that:

1. Labels each row with `is_filtered ∈ {0,1}` via the DSL → SQL
   compilation (Story 4.4, named bind params — NO injection surface).
2. Expands the row across tag axes (top-level `level` / `logger` /
   `file` columns + every `(key, value)` pair from the `context` JSON
   via `json_each`).
3. `GROUP BY` tag + value with `SUM(is_filtered)` /
   `SUM(1 - is_filtered)` to get per-(tag,value) counts in the two
   populations.

Lift = P(tag=v | filter) / P(tag=v | ¬filter). The report's
`top_over` shows the most over-represented dimensions (highest lift);
`bottom_under` the most under-represented. Self-tautology rows
(`level=ERROR` lift on a `level=ERROR` filter) are removed.

Requires SQLite ≥ 3.38 for the bundled `json_each` JSON1 extension
(stdlib since 3.38, released 2022-02). Older SQLite raises
`RuntimeError` at call time.
"""

from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Story 4.6 — small-sample threshold (frequentist convention: < 30).
SMALL_SAMPLE_THRESHOLD = 30


@dataclass(frozen=True)
class CorrelationRow:
    """One (tag, value) outcome — counts in the filter vs baseline + lift.

    `warning` (Story 4.6):
      - "small_sample" → `in_filter < 30` (lift is unreliable).
      - "axis"         → row IS the filter axis (excluded from rank).
      - None           → unannotated.
    """

    tag: str
    value: Any
    in_filter: int
    in_baseline: int
    lift: float
    warning: str | None = None


@dataclass(frozen=True)
class CorrelationReport:
    """Result of a `correlate(...)` run — top-over / bottom-under + counts.

    `axis_rows` (Story 4.6): rows excluded from rank because they ARE
    the filter axis (e.g. `level=ERROR` row on a `level=ERROR` filter).
    Exposed for inspection — uninformative but not hidden.
    """

    top_over: tuple[CorrelationRow, ...]
    bottom_under: tuple[CorrelationRow, ...]
    filter_count: int
    baseline_count: int
    wall_time_ms: float
    axis_rows: tuple[CorrelationRow, ...] = ()


def correlate(
    db_path: str | Path,
    *,
    where: str | None = None,
    where_dsl: str | None = None,
    top: int = 10,
    bottom: int = 5,
) -> CorrelationReport:
    """Compute lift for every (tag, value) dimension against a filter.

    Args:
        db_path: SQLite path (Path/str) or `sqlite:///...` URL.
        where: raw SQL WHERE fragment (no params; user's responsibility).
            Mutually exclusive with `where_dsl`.
        where_dsl: filter DSL string (Story 4.4). Compiled to a
            parameterised SQL clause — recommended for any user input.
        top: max rows in `top_over` (sorted by lift DESC).
        bottom: max rows in `bottom_under` (sorted by lift ASC).

    Returns:
        `CorrelationReport` with `top_over`, `bottom_under`, totals + ms.

    Raises:
        ValueError: both `where` and `where_dsl` set, or neither.
        FileNotFoundError: DB path doesn't exist.
        RuntimeError: SQLite < 3.38 (no `json_each`).
    """
    if (where is None) == (where_dsl is None):
        raise ValueError("correlate() requires exactly one of `where` / `where_dsl`")
    if sqlite3.sqlite_version_info < (3, 38):
        raise RuntimeError(
            f"SQLite {sqlite3.sqlite_version} lacks json_each; "
            "correlate() requires ≥ 3.38 (stdlib since 2022-02)."
        )

    db_str = _resolve_path(db_path)

    if where_dsl is not None:
        from ._filter_dsl import parse as _parse_dsl

        expr = _parse_dsl(where_dsl)
        filter_sql, params = expr.to_sql()
        # Build the self-tautology removal set: any Cmp top-level node
        # at the OR-AND tree whose `op == '='` should be excluded.
        excluded = _collect_eq_pairs(expr.root)
    else:
        assert where is not None
        filter_sql = where
        params = {}
        excluded = set()

    t0 = time.perf_counter()
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db_str}", future=True)
    with engine.begin() as conn:
        totals_row = conn.execute(
            text(
                f"SELECT SUM(CASE WHEN {filter_sql} THEN 1 ELSE 0 END), "
                f"COUNT(*) - SUM(CASE WHEN {filter_sql} THEN 1 ELSE 0 END) "
                "FROM logs"
            ),
            params,
        ).first()
        assert totals_row is not None
        in_filter_total = int(totals_row[0] or 0)
        in_baseline_total = int(totals_row[1] or 0)

        if in_filter_total == 0:
            engine.dispose()
            return CorrelationReport(
                top_over=(),
                bottom_under=(),
                filter_count=0,
                baseline_count=in_baseline_total,
                wall_time_ms=(time.perf_counter() - t0) * 1000,
            )

        rows = conn.execute(
            text(
                "WITH labeled AS ("
                "  SELECT level, logger, file, context, "
                f"  CASE WHEN {filter_sql} THEN 1 ELSE 0 END AS is_filtered "
                "  FROM logs"
                "), expanded AS ("
                "  SELECT 'level' AS tag, level AS value, is_filtered FROM labeled"
                "  UNION ALL"
                "  SELECT 'logger', logger, is_filtered FROM labeled"
                "  UNION ALL"
                "  SELECT 'file', file, is_filtered FROM labeled"
                "  UNION ALL"
                "  SELECT 'context.' || je.key, je.value, labeled.is_filtered "
                "  FROM labeled, json_each(labeled.context) AS je "
                "  WHERE labeled.context IS NOT NULL"
                ") "
                "SELECT tag, value, "
                "SUM(is_filtered), SUM(1 - is_filtered) "
                "FROM expanded "
                "GROUP BY tag, value"
            ),
            params,
        ).all()
    engine.dispose()

    rankable: list[CorrelationRow] = []
    axis_rows: list[CorrelationRow] = []
    for tag, value, in_filter_n, in_baseline_n in rows:
        in_f = int(in_filter_n or 0)
        in_b = int(in_baseline_n or 0)
        lift = _compute_lift(in_f, in_b, in_filter_total, in_baseline_total)
        is_axis = (tag, _coerce_value(value)) in excluded
        # Story 4.6 — axis warning wins over small_sample (more
        # actionable to know "this is your filter").
        if is_axis:
            warning: str | None = "axis"
        elif in_f < SMALL_SAMPLE_THRESHOLD:
            warning = "small_sample"
        else:
            warning = None
        row = CorrelationRow(
            tag=tag,
            value=value,
            in_filter=in_f,
            in_baseline=in_b,
            lift=lift,
            warning=warning,
        )
        if is_axis:
            axis_rows.append(row)
        else:
            rankable.append(row)

    top_over = tuple(sorted(rankable, key=lambda r: (-r.lift, r.tag, str(r.value)))[:top])
    bottom_under = tuple(sorted(rankable, key=lambda r: (r.lift, r.tag, str(r.value)))[:bottom])

    return CorrelationReport(
        top_over=top_over,
        bottom_under=bottom_under,
        filter_count=in_filter_total,
        baseline_count=in_baseline_total,
        wall_time_ms=(time.perf_counter() - t0) * 1000,
        axis_rows=tuple(axis_rows),
    )


def _resolve_path(db_path: str | Path) -> Path:
    if isinstance(db_path, str) and db_path.startswith("sqlite:///"):
        return Path(db_path.removeprefix("sqlite:///"))
    p = Path(db_path) if not isinstance(db_path, Path) else db_path
    if not p.exists():
        raise FileNotFoundError(f"correlate(): DB not found at {p}")
    return p


def _compute_lift(in_filter: int, in_baseline: int, ft: int, bt: int) -> float:
    if ft == 0:
        return 0.0
    p_in = in_filter / ft
    if bt == 0 or in_baseline == 0:
        return math.inf if in_filter > 0 else 0.0
    p_out = in_baseline / bt
    if p_out == 0:
        return math.inf
    return p_in / p_out


def _collect_eq_pairs(node: Any) -> set[tuple[str, Any]]:
    """Walk the DSL AST and harvest (key, value) pairs from `=` Cmps.

    Used to filter out self-tautology rows from the report (e.g.
    when the filter is `level=ERROR`, the row `tag="level", value="ERROR"`
    is uninformative — exclude it).
    """
    from ._filter_dsl import And as _And
    from ._filter_dsl import Cmp as _Cmp
    from ._filter_dsl import Or as _Or

    out: set[tuple[str, Any]] = set()
    if isinstance(node, _Cmp):
        if node.op == "=":
            out.add((node.key, node.value))
    elif isinstance(node, _And | _Or):
        out.update(_collect_eq_pairs(node.left))
        out.update(_collect_eq_pairs(node.right))
    return out


def _coerce_value(v: Any) -> Any:
    """SQLite returns JSON values as strings; the DSL may store them
    as int/float/str. Normalise for self-tautology set-membership."""
    if isinstance(v, str):
        # Try to round-trip numeric strings to their typed form.
        try:
            if "." in v:
                return float(v)
            return int(v)
        except (ValueError, TypeError):
            return v
    return v
