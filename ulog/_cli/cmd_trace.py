"""`ulog trace <trace_id> --db DB` CLI (Story 6.2 / FR110).

Lists all records sharing the given trace_id, sorted chronologically.
Uses SQLite's `json_extract` to pull `trace_id` from the JSON context
column.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "trace",
        help="List all records sharing a trace_id chronologically.",
    )
    sp.add_argument("trace_id", help="The W3C trace_id (32-hex string).")
    sp.add_argument("--db", required=True, help="Path to the SQLite DB.")
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        print(f"ulog trace: DB not found: {args.db}", file=sys.stderr)
        return 2

    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{args.db}", future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT ts, level, logger, msg FROM logs "
                "WHERE json_extract(context, '$.trace_id') = :tid "
                "ORDER BY ts ASC"
            ),
            {"tid": args.trace_id},
        ).all()
    engine.dispose()

    if not rows:
        print(f"No records for trace_id {args.trace_id}.")
        return 0

    print(f"{len(rows)} record(s) for trace_id {args.trace_id}:")
    for ts, level, logger, msg in rows:
        print(f"  {ts}  {level:<8}  {logger:<20}  {msg}")
    return 0
