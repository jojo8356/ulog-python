"""`ulog correlate <filter> --db DB` CLI subcommand (Story 4.8 / FR104).

Prints a CorrelationReport as an ASCII table with `top_over`,
`bottom_under`, and `axis_rows` sections plus a summary line.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

from .._correlate import CorrelationReport, CorrelationRow, correlate
from .._filter_dsl import FilterParseError


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "correlate",
        help="Find over-represented dimensions for a filter (lift formula).",
    )
    sp.add_argument("filter", help="DSL filter string (Story 4.4).")
    sp.add_argument("--db", required=True, help="Path to the SQLite DB.")
    sp.add_argument("--top", type=int, default=10, help="Max top_over rows.")
    sp.add_argument("--bottom", type=int, default=5, help="Max bottom_under rows.")
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        print(f"ulog correlate: DB not found: {args.db}", file=sys.stderr)
        return 2
    try:
        report = correlate(args.db, where_dsl=args.filter, top=args.top, bottom=args.bottom)
    except FilterParseError as exc:
        print(f"ulog correlate: invalid filter — {exc}", file=sys.stderr)
        return 2

    _print_report(report)
    return 0


def _print_report(report: CorrelationReport) -> None:
    print(
        f"filter: {report.filter_count}  baseline: {report.baseline_count}  "
        f"wall: {report.wall_time_ms:.1f} ms"
    )
    if report.top_over:
        print("\n=== top_over (most over-represented) ===")
        _print_rows(report.top_over)
    if report.bottom_under:
        print("\n=== bottom_under (most under-represented) ===")
        _print_rows(report.bottom_under)
    if report.axis_rows:
        print("\n=== axis_rows (filter dimension; excluded from rank) ===")
        _print_rows(report.axis_rows)


def _print_rows(rows: tuple[CorrelationRow, ...]) -> None:
    for r in rows:
        lift_repr = "∞" if math.isinf(r.lift) else f"{r.lift:.2f}"
        warning = ""
        if r.warning == "small_sample":
            warning = "  ⚠ small_sample"
        elif r.warning == "axis":
            warning = "  (axis)"
        print(
            f"  {r.tag} = {r.value!r:<30}  "
            f"in_filter={r.in_filter:<6}  in_baseline={r.in_baseline:<6}  "
            f"lift={lift_repr}{warning}"
        )
