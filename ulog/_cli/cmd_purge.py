"""`ulog purge --before <date>` — delete rotable rows older than the
given date (Story 3.9 / FR93).

Honors:
- I4: immutable rows are filtered out of the DELETE (the trigger would
  block them anyway; this avoids stderr noise).
- FR92: `min_retention_days` (set via Story 3.6's
  `ulog.setup(min_retention_days=...)`) refuses purges within the
  retention floor.
- Gap G8: pre-chain backfilled rows (record_hash IS NULL) are rotable
  by default — included in the candidate set.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import Any


def _parse_iso_date(s: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"date must be ISO YYYY-MM-DD, got {s!r}") from exc


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "purge",
        help="Delete rotable rows older than --before (immutable rows are spared).",
    )
    sp.add_argument("db_path", nargs="?", help="Path to the SQLite DB.")
    sp.add_argument("--db", dest="db", default=None, help="Alternate DB path.")
    sp.add_argument(
        "--before",
        type=_parse_iso_date,
        required=True,
        help="ISO date YYYY-MM-DD. Rows with ts < <date> are candidates.",
    )
    sp.add_argument(
        "--confirm",
        action="store_true",
        help="Required to actually delete. Without it, behaves as --dry-run.",
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Count candidates without deleting (exit 0).",
    )
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    from sqlalchemy import create_engine, text

    from .. import _retention

    db_str = args.db_path or args.db
    if not db_str:
        print("ulog purge: --db PATH or positional db_path required", file=sys.stderr)
        return 2
    db = Path(db_str)
    if not db.exists():
        print(f"ulog purge: DB not found: {db}", file=sys.stderr)
        return 2

    # Retention-floor check (FR92).
    if _retention.MIN_RETENTION_DAYS > 0:
        earliest_allowed = datetime.date.today() - datetime.timedelta(
            days=_retention.MIN_RETENTION_DAYS
        )
        if args.before > earliest_allowed:
            print(
                f"✗ Refused: --before {args.before.isoformat()} is within the "
                f"{_retention.MIN_RETENTION_DAYS}-day retention floor "
                f"(earliest allowed: {earliest_allowed.isoformat()}).",
                file=sys.stderr,
            )
            return 1

    url = f"sqlite:///{db}"
    engine = create_engine(url, future=True)
    before_dt = datetime.datetime.combine(args.before, datetime.time.min)
    with engine.begin() as conn:
        candidates = conn.execute(
            text("SELECT COUNT(*) FROM logs WHERE immutable = 0 AND ts < :b"),
            {"b": before_dt},
        ).scalar_one()
        is_dry = args.dry_run or not args.confirm
        if not is_dry:
            conn.execute(
                text("DELETE FROM logs WHERE immutable = 0 AND ts < :b"),
                {"b": before_dt},
            )
    engine.dispose()

    suffix = " (dry-run)" if is_dry else ""
    print(
        f"✓ Purge {args.before.isoformat()}{suffix}: "
        f"{candidates} rotable rows {'would be ' if is_dry else ''}deleted."
    )
    return 0
