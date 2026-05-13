"""`ulog tail` — `tail -f` equivalent for a stored log DB.

Polls the SQLite DB at a configurable interval and prints records
with `id > last_seen` to stdout. Supports `--filter <dsl>` (same
grammar as `ulog correlate`), `--levels ERROR,WARNING`, and a
qlnes-style output format.

Usage:
    ulog tail --db ./logs.sqlite                 # all new records
    ulog tail --db ./logs.sqlite --levels ERROR  # errors only
    ulog tail --db ./logs.sqlite --filter "logger=globex.payments"
    ulog tail --db ./logs.sqlite --interval 100  # 100ms polling
    ulog tail --db ./logs.sqlite --since-start   # also print past records
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "tail",
        help="Follow a stored log DB live — `tail -f` for ulog.",
    )
    sp.add_argument("--db", required=True, type=Path)
    sp.add_argument(
        "--filter",
        dest="filter_dsl",
        default="",
        help="DSL filter (same grammar as `ulog correlate`).",
    )
    sp.add_argument(
        "--levels",
        default="",
        help="Comma-separated levels to keep (e.g. ERROR,WARNING).",
    )
    sp.add_argument(
        "--interval",
        type=int,
        default=500,
        help="Polling interval in milliseconds (default 500).",
    )
    sp.add_argument(
        "--since-start",
        action="store_true",
        help="Print past records too (default: only new from now).",
    )
    sp.add_argument(
        "-n",
        "--lines",
        type=int,
        default=0,
        help="Print the last N records before going live (like `tail -n`).",
    )
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"ulog tail: DB not found: {args.db}", file=sys.stderr)
        return 2

    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{args.db}", future=True)

    # Resolve starting position.
    with engine.connect() as conn:
        max_id = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM logs")).scalar() or 0
    if args.since_start:
        last_seen = 0
    elif args.lines > 0:
        last_seen = max(0, int(max_id) - args.lines)
    else:
        last_seen = int(max_id)

    # Resolve filter axes.
    levels_set: set[str] = set()
    if args.levels:
        levels_set = {lv.strip().upper() for lv in args.levels.split(",") if lv.strip()}

    predicate = None
    if args.filter_dsl:
        from ulog._filter_dsl import FilterParseError, parse

        try:
            predicate = parse(args.filter_dsl).to_predicate()
        except FilterParseError as e:
            print(f"ulog tail: invalid --filter: {e}", file=sys.stderr)
            engine.dispose()
            return 2

    interval_s = max(0.05, args.interval / 1000.0)

    print(
        f"ulog tail: following {args.db} (interval={args.interval}ms, "
        f"starting from id>{last_seen}). Ctrl-C to exit.",
        file=sys.stderr,
    )

    try:
        while True:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, ts, level, logger, msg, context "
                        "FROM logs WHERE id > :id ORDER BY id ASC"
                    ),
                    {"id": last_seen},
                ).all()
            for r in rows:
                last_seen = max(last_seen, r[0])
                if levels_set and r[2] not in levels_set:
                    continue
                if predicate is not None:
                    rec_dict = {
                        "id": r[0],
                        "ts": r[1],
                        "level": r[2],
                        "logger": r[3],
                        "msg": r[4],
                        "context": json.loads(r[5]) if r[5] else {},
                    }
                    if not predicate(rec_dict):
                        continue
                print(_format_line(r[1], r[2], r[3], r[4]))
                sys.stdout.flush()
            time.sleep(interval_s)
    except KeyboardInterrupt:
        print("\nulog tail: stopped.", file=sys.stderr)
        return 0
    finally:
        engine.dispose()


def _format_line(ts: Any, level: str, logger: str, msg: str) -> str:
    """qlnes-style: bare msg on INFO/DEBUG, prefixed on WARNING+."""
    if level in ("INFO", "DEBUG"):
        return f"{ts}  {logger}  {msg}"
    return f"{ts}  {logger}: {level.lower()}: {msg}"
