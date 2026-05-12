"""`ulog repair --confirm <db>` — truncate the chain at the last
valid record and archive orphans to a JSONL sidecar (Story 3.8 /
FR97).

Refuses to remove immutable rows (invariant I4) — manual forensic
review is required when an immutable orphan is detected.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

from .._chain import parse_stored_ts as _parse_ts


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "repair",
        help="Truncate broken chain + archive orphans (destructive; requires --confirm).",
    )
    sp.add_argument("db_path", nargs="?", help="Path to the SQLite DB.")
    sp.add_argument("--db", dest="db", default=None, help="Alternate way to specify DB path.")
    sp.add_argument(
        "--confirm",
        action="store_true",
        help="Required — repair is destructive of the live chain.",
    )
    sp.set_defaults(run=run)


def _find_first_break(conn: Any) -> int | None:
    """Walk the chain; return the chain_pos of the first broken row,
    or None if the chain is healthy. Same algorithm as `cmd_verify`
    but returns a position instead of printing."""
    from sqlalchemy import text

    from .._chain import sha256_record

    rows = conn.execute(
        text(
            "SELECT chain_pos, ts, level, logger, msg, file, line, "
            "exc, context, immutable, record_hash, prev_hash, is_replay "
            "FROM logs WHERE record_hash IS NOT NULL ORDER BY chain_pos"
        )
    ).all()

    expected_prev = b"\x00" * 32
    for row in rows:
        actual_prev = bytes(row[11])
        if actual_prev != expected_prev:
            return int(row[0])
        rec = {
            "ts": _parse_ts(row[1]),
            "level": row[2],
            "logger": row[3],
            "msg": row[4],
            "file": row[5],
            "line": row[6],
            "exc": json.loads(row[7]) if isinstance(row[7], str) else row[7],
            "context": json.loads(row[8]) if isinstance(row[8], str) else row[8],
            "immutable": row[9],
            "is_replay": row[12],  # Story 4.2 — part of the canonical hash
        }
        if sha256_record(rec, actual_prev) != bytes(row[10]):
            return int(row[0])
        expected_prev = bytes(row[10])
    return None


def _sidecar_path(db_path: Path) -> Path:
    """`logs.sqlite` -> `logs.chain_break_<UTC-no-colons>.log`."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    return db_path.with_suffix(f".chain_break_{stamp}.log")


def _row_to_jsonl(row: Any) -> str:
    """Convert a SQL row tuple to a JSONL-friendly dict + serialise."""
    ts = row[1]
    if isinstance(ts, datetime.datetime):
        ts = ts.isoformat()
    return json.dumps(
        {
            "chain_pos": row[0],
            "ts": ts,
            "level": row[2],
            "logger": row[3],
            "msg": row[4],
            "file": row[5],
            "line": row[6],
            "exc": json.loads(row[7]) if isinstance(row[7], str) else row[7],
            "context": json.loads(row[8]) if isinstance(row[8], str) else row[8],
            "immutable": row[9],
            "record_hash": bytes(row[10]).hex() if row[10] is not None else None,
            "prev_hash": bytes(row[11]).hex() if row[11] is not None else None,
        }
    )


def run(args: argparse.Namespace) -> int:
    from sqlalchemy import create_engine, text

    db_str = args.db_path or args.db
    if not db_str:
        print("ulog repair: --db PATH or positional db_path required", file=sys.stderr)
        return 2
    db = Path(db_str)
    if not db.exists():
        print(f"ulog repair: DB not found: {db}", file=sys.stderr)
        return 2
    if not args.confirm:
        print(
            "Use --confirm to proceed; this is destructive of the live chain.",
            file=sys.stderr,
        )
        return 2

    url = f"sqlite:///{db}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        break_pos = _find_first_break(conn)
        if break_pos is None:
            print("✓ Chain is healthy — nothing to repair.")
            engine.dispose()
            return 0

        # Pull every row from break_pos onwards (orphans).
        orphans = conn.execute(
            text(
                "SELECT chain_pos, ts, level, logger, msg, file, line, "
                "exc, context, immutable, record_hash, prev_hash "
                "FROM logs WHERE chain_pos >= :p ORDER BY chain_pos"
            ),
            {"p": break_pos},
        ).all()

        # Immutable refusal — invariant I4.
        for row in orphans:
            if row[9] == 1:
                print(
                    f"✗ Cannot repair: immutable orphan at #{row[0]}. "
                    "Invariant I4 forbids removal. Manual forensic review "
                    "required.",
                    file=sys.stderr,
                )
                engine.dispose()
                return 1

        # Archive to sidecar JSONL.
        sidecar = _sidecar_path(db)
        with sidecar.open("w", encoding="utf-8") as f:
            for row in orphans:
                f.write(_row_to_jsonl(row) + "\n")

        # Delete from live DB (trigger doesn't fire — all immutable=0).
        conn.execute(
            text("DELETE FROM logs WHERE chain_pos >= :p"),
            {"p": break_pos},
        )
    engine.dispose()

    # Story 3.12 AC5 — clear the stale BROKEN verify-state sidecar so
    # the next SQLHandler bootstrap doesn't refuse to open in chain
    # mode. Next `ulog verify` will write a fresh OK state.
    from .._verify_state import sidecar_path

    sidecar_path(db).unlink(missing_ok=True)

    print(f"✓ Repaired: archived {len(orphans)} orphans to {sidecar}")
    return 0
