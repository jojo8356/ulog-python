"""`ulog bisect <pattern> --db DB` CLI subcommand (Story 4.8 / FR104).

Prints the first chain record whose `msg` or `context` value matches
the regex. No match → "No record matched pattern." + exit 0.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from .._bisect import bisect


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "bisect",
        help="Find the first chain record matching a regex pattern.",
    )
    sp.add_argument("pattern", help="Python regex (re.compile).")
    sp.add_argument("--db", required=True, help="Path to the SQLite DB.")
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        print(f"ulog bisect: DB not found: {args.db}", file=sys.stderr)
        return 2
    try:
        result = bisect(args.db, pattern=args.pattern)
    except re.error as exc:
        print(f"ulog bisect: invalid regex — {exc}", file=sys.stderr)
        return 2

    if result is None:
        print("No record matched pattern.")
        return 0

    rec = result.record
    print(f"Found at chain_pos={result.chain_pos} (wall {result.wall_time_ms:.1f} ms)")
    print(f"  ts:     {rec['ts']}")
    print(f"  level:  {rec['level']}")
    print(f"  logger: {rec['logger']}")
    print(f"  file:   {rec['file']}:{rec['line']}")
    print(f"  msg:    {rec['msg']}")
    ctx = rec.get("context") or {}
    if ctx:
        print("  context:")
        for k, v in ctx.items():
            print(f"    {k} = {v!r}")
    return 0
