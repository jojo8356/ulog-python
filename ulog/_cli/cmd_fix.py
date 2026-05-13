"""`ulog fix` — local fix database CLI (PRD-v0.13)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ulog._fixes import (
    fixes_db_path,
    list_fixes,
    lookup_fix,
    resolve_fix,
    signature,
    unresolve_fix,
)


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "fix",
        help="Resolve / list / show / unresolve entries in the local fix DB.",
    )
    sub = sp.add_subparsers(dest="fix_subcommand")
    sp.set_defaults(run=run)

    rs = sub.add_parser("resolve", help="Mark a record's signature as resolved with a writeup.")
    rs.add_argument("--db", required=True, type=Path)
    rs.add_argument("--record-id", type=int, help="Record id (computes signature from it).")
    rs.add_argument("--signature", default="", help="Explicit signature (skips record lookup).")
    rs.add_argument("--writeup", required=True, help="What you fixed + how.")
    rs.add_argument("--by", required=True)
    rs.add_argument("--commit-sha", default="")
    rs.set_defaults(run_sub=_resolve)

    ls = sub.add_parser("list", help="List every fix entry in the sidecar DB.")
    ls.add_argument("--db", required=True, type=Path)
    ls.set_defaults(run_sub=_list)

    sh = sub.add_parser("show", help="Show one fix entry by signature.")
    sh.add_argument("--db", required=True, type=Path)
    sh.add_argument("signature")
    sh.set_defaults(run_sub=_show)

    un = sub.add_parser("unresolve", help="Drop a fix entry by signature.")
    un.add_argument("--db", required=True, type=Path)
    un.add_argument("signature")
    un.set_defaults(run_sub=_unresolve)


def run(args: argparse.Namespace) -> int:
    sub = getattr(args, "run_sub", None)
    if sub is None:
        print("ulog fix: missing subcommand (resolve / list / show / unresolve)", file=sys.stderr)
        return 2
    return int(sub(args))


# ---- subcommand handlers ------------------------------------------------


def _resolve_signature_for_record(main_db: Path, record_id: int) -> str:
    """Look up the record by id and compute its signature."""
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{main_db}", future=True)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT msg, context FROM logs WHERE id = :id"), {"id": record_id}
        ).first()
    engine.dispose()
    if row is None:
        raise SystemExit(f"ulog fix: no record id={record_id} in {main_db}")
    msg = row[0]
    ctx_raw = json.loads(row[1]) if row[1] else None
    ctx = ctx_raw if isinstance(ctx_raw, dict) else {}
    stack = ctx.get("stack")
    return signature(msg, stack if isinstance(stack, list) else None)


def _resolve(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"ulog fix: db not found: {args.db}", file=sys.stderr)
        return 2
    if args.signature:
        sig = args.signature
    elif args.record_id is not None:
        try:
            sig = _resolve_signature_for_record(args.db, args.record_id)
        except SystemExit as e:
            print(str(e), file=sys.stderr)
            return 2
    else:
        print("ulog fix resolve: provide --record-id or --signature", file=sys.stderr)
        return 2
    resolve_fix(args.db, sig, args.writeup, args.by, args.commit_sha)
    print(f"ulog fix: resolved signature {sig[:16]}… (by {args.by})", file=sys.stderr)
    return 0


def _list(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"ulog fix: db not found: {args.db}", file=sys.stderr)
        return 2
    entries = list_fixes(args.db)
    for e in entries:
        line1 = f"#{e['signature'][:8]}  {e['ts']}  by {e['by']}"
        line2 = f"  {e['writeup'][:120]}"
        print(line1)
        print(line2)
    print(f"\n{len(entries)} fix(es) in {fixes_db_path(args.db)}", file=sys.stderr)
    return 0


def _show(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"ulog fix: db not found: {args.db}", file=sys.stderr)
        return 2
    entry = lookup_fix(args.db, args.signature)
    if entry is None:
        print(f"ulog fix: no entry for {args.signature}", file=sys.stderr)
        return 1
    print(f"signature: {entry['signature']}")
    print(f"by: {entry['by']}")
    print(f"ts: {entry['ts']}")
    if entry["commit_sha"]:
        print(f"commit: {entry['commit_sha']}")
    print(f"\n{entry['writeup']}")
    return 0


def _unresolve(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"ulog fix: db not found: {args.db}", file=sys.stderr)
        return 2
    if unresolve_fix(args.db, args.signature):
        print(f"ulog fix: dropped {args.signature[:16]}…", file=sys.stderr)
        return 0
    print(f"ulog fix: no entry for {args.signature}", file=sys.stderr)
    return 1
