"""`ulog verify [--range A-B]` — walk the chain offline (Story 3.7).

Reads the `logs` table in chain_pos order, recomputes each record's
hash, compares against stored values. Reports OK or BROKEN-at-N on
stdout, with POSIX exit codes 0 (clean) / 1 (broken).

Reuses `ulog._chain.canonical_record_json` + `sha256_record` so the
verifier and the writer never drift.
"""

from __future__ import annotations

import argparse
import datetime
import json
import time
from pathlib import Path
from typing import Any

from .._chain import parse_stored_ts as _parse_ts


def _parse_range(s: str) -> tuple[int, int]:
    """Accept `A-B` or `A,B` (inclusive). Used as argparse `type=`."""
    sep = "-" if "-" in s else ("," if "," in s else None)
    if sep is None:
        raise argparse.ArgumentTypeError(f"range must be 'A-B' or 'A,B', got {s!r}")
    try:
        a_s, b_s = s.split(sep, 1)
        a, b = int(a_s), int(b_s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"range must be integers, got {s!r}") from exc
    if a > b:
        raise argparse.ArgumentTypeError(f"range A must be <= B, got {a}-{b}")
    return (a, b)


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "verify",
        help="Walk the chain offline and report OK or BROKEN.",
    )
    sp.add_argument("db_path", nargs="?", help="Path to the SQLite DB.")
    sp.add_argument("--db", dest="db", default=None, help="Alternate way to specify DB path.")
    sp.add_argument(
        "--range",
        dest="range_",
        type=_parse_range,
        default=None,
        help="Walk only chain_pos in [A,B] (inclusive). Format A-B or A,B.",
    )
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    from sqlalchemy import create_engine, text

    from .._chain import sha256_record

    db = args.db_path or args.db
    if not db:
        print(
            "ulog verify: --db PATH or positional db_path required", file=__import__("sys").stderr
        )
        return 2
    if not Path(db).exists():
        print(f"ulog verify: DB not found: {db}", file=__import__("sys").stderr)
        return 2

    url = f"sqlite:///{db}"
    engine = create_engine(url, future=True)
    where_parts = ["record_hash IS NOT NULL"]
    params: dict[str, Any] = {}
    if args.range_:
        a, b = args.range_
        where_parts.append("chain_pos BETWEEN :a AND :b")
        params = {"a": a, "b": b}
    where_sql = " AND ".join(where_parts)

    t0 = time.perf_counter()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT chain_pos, ts, level, logger, msg, file, line, "
                "exc, context, immutable, record_hash, prev_hash, is_replay "
                f"FROM logs WHERE {where_sql} ORDER BY chain_pos"
            ),
            params,
        ).all()

        # For partial ranges starting at A > 1, the expected prev_hash
        # is the record_hash of (A-1), not the zero hash.
        expected_prev = b"\x00" * 32
        if args.range_ and args.range_[0] > 1:
            prev_row = conn.execute(
                text(
                    "SELECT record_hash FROM logs WHERE chain_pos = :p AND record_hash IS NOT NULL"
                ),
                {"p": args.range_[0] - 1},
            ).first()
            if prev_row and prev_row[0] is not None:
                expected_prev = bytes(prev_row[0])
    engine.dispose()

    last_good_pos = 0
    for row in rows:
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
        actual_record_hash = bytes(row[10])
        actual_prev_hash = bytes(row[11])
        if actual_prev_hash != expected_prev:
            print(
                f"✗ BROKEN at record #{row[0]}: "
                f"expected prev_hash={expected_prev.hex()[:8]}..., "
                f"got {actual_prev_hash.hex()[:8]}..."
            )
            _maybe_write_state(
                args,
                db,
                status="BROKEN",
                broken_at=int(row[0]),
                verified_up_to=last_good_pos,
                walk_time_s=time.perf_counter() - t0,
            )
            return 1
        recomputed = sha256_record(rec, actual_prev_hash)
        if recomputed != actual_record_hash:
            print(
                f"✗ BROKEN at record #{row[0]}: "
                f"recomputed record_hash={recomputed.hex()[:8]}... "
                f"!= stored {actual_record_hash.hex()[:8]}..."
            )
            _maybe_write_state(
                args,
                db,
                status="BROKEN",
                broken_at=int(row[0]),
                verified_up_to=last_good_pos,
                walk_time_s=time.perf_counter() - t0,
            )
            return 1
        expected_prev = actual_record_hash
        last_good_pos = int(row[0])

    walk_time_s = time.perf_counter() - t0
    print(f"✓ Integrity verified\n  records: {len(rows)}\n  wall_time: {walk_time_s * 1000:.1f}ms")
    _maybe_write_state(
        args,
        db,
        status="OK",
        broken_at=None,
        verified_up_to=last_good_pos,
        walk_time_s=walk_time_s,
    )
    return 0


def _maybe_write_state(
    args: argparse.Namespace,
    db: Any,
    *,
    status: str,
    broken_at: int | None,
    verified_up_to: int,
    walk_time_s: float,
) -> None:
    """Write `<db>.verify_state.json` ONLY for full-chain walks (no
    --range). Partial walks would mislead the UI badge into thinking
    the whole chain was checked."""
    if args.range_:
        return
    from .._verify_state import write_verify_state

    write_verify_state(
        Path(db),
        {
            "status": status,
            "broken_at": broken_at,
            "verified_up_to_chain_pos": verified_up_to,
            "last_check_ts": datetime.datetime.now(datetime.UTC).isoformat(),
            "walk_time_s": round(walk_time_s, 4),
        },
    )
