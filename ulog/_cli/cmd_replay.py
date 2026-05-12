"""`ulog replay <filter> --db DB [--to-pytest PATH]` CLI (Story 4.8 / FR104).

Without `--to-pytest`: prints each matching record (one line).
With `--to-pytest`: delegates to `replay_to_pytest()` (Story 4.3).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .._filter_dsl import FilterParseError
from ..replay import replay, replay_to_pytest


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "replay",
        help="Iterate / print matching chain records, or generate a regression test.",
    )
    sp.add_argument("filter", help="DSL filter string (Story 4.4).")
    sp.add_argument("--db", required=True, help="Path to the SQLite DB.")
    sp.add_argument(
        "--to-pytest",
        dest="to_pytest",
        default=None,
        help="If set, write a regression test file (Story 4.3) and exit.",
    )
    sp.add_argument("--topic", default="incident", help="Slug for the generated test name.")
    sp.add_argument("--incident-hash", default="", help="Slug for the generated test name.")
    sp.add_argument("--force", action="store_true", help="Overwrite existing --to-pytest file.")
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        print(f"ulog replay: DB not found: {args.db}", file=sys.stderr)
        return 2

    if args.to_pytest:
        try:
            count = replay_to_pytest(
                args.db,
                where=_compile_to_sql_str(args.filter),  # 4.3 takes raw SQL
                output_path=args.to_pytest,
                incident_hash=args.incident_hash,
                topic=args.topic,
                force=args.force,
            )
        except FilterParseError as exc:
            print(f"ulog replay: invalid filter — {exc}", file=sys.stderr)
            return 2
        except FileExistsError as exc:
            print(f"ulog replay: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote {args.to_pytest} ({count} records snapshotted).")
        return 0

    try:
        count = replay(args.db, where_dsl=args.filter, on=_print_record)
    except FilterParseError as exc:
        print(f"ulog replay: invalid filter — {exc}", file=sys.stderr)
        return 2
    print(f"\n{count} records replayed.")
    return 0


def _compile_to_sql_str(dsl: str) -> str:
    """Compile a DSL filter to a literal SQL fragment WITH bind values
    inlined (for replay_to_pytest where the v4.3 API takes a `where`
    string only — bind params would need protocol changes deferred to
    v0.5.x). Used ONLY for the CLI subprocess path; user input never
    flows here from the network.

    SAFETY: this re-interpolates values into SQL. Acceptable because:
    (1) the CLI is the user's own shell; (2) the DSL parser already
    rejected `;` / shell metachars; (3) replay_to_pytest is a code-
    generator, not a queryable surface.
    """
    from .._filter_dsl import parse as _parse

    clause, params = _parse(dsl).to_sql()
    for name, value in params.items():
        clause = clause.replace(f":{name}", _sql_literal(value))
    return clause


def _sql_literal(value: Any) -> str:
    if isinstance(value, str):
        # Escape single quotes by doubling.
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _print_record(record: Any) -> None:
    """Print a one-line summary of each replayed record."""
    print(
        f"chain_pos={record['chain_pos']}  "
        f"{record['ts']}  "
        f"{record['level']:<8}  "
        f"{record['logger']}  "
        f"{record['msg']}"
    )
