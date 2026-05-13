"""`ulog solutions` — community site client CLI (PRD-v0.15)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ulog._solutions_client import (
    DEFAULT_ENDPOINT,
    DEFAULT_KEY_PATH,
    fetch_signature,
    keygen,
    publish,
)


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "solutions",
        help="Community-solutions client (publish / fetch / keygen). PRD-v0.15.",
    )
    sub = sp.add_subparsers(dest="solutions_subcommand")
    sp.set_defaults(run=run)

    kg = sub.add_parser("keygen", help="Generate an ed25519 keypair.")
    kg.add_argument("--path", type=Path, default=DEFAULT_KEY_PATH)
    kg.set_defaults(run_sub=_keygen)

    pu = sub.add_parser("publish", help="Publish a fix to the community site.")
    pu.add_argument("--signature", required=True)
    pu.add_argument("--writeup", required=True)
    pu.add_argument("--by", required=True)
    pu.add_argument("--key-path", type=Path, default=DEFAULT_KEY_PATH)
    pu.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    pu.set_defaults(run_sub=_publish)

    fe = sub.add_parser("fetch", help="Fetch matches for a signature (anonymous).")
    fe.add_argument("signature")
    fe.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    fe.set_defaults(run_sub=_fetch)


def run(args: argparse.Namespace) -> int:
    sub = getattr(args, "run_sub", None)
    if sub is None:
        print("ulog solutions: missing subcommand (keygen/publish/fetch)", file=sys.stderr)
        return 2
    return int(sub(args))


def _keygen(args: argparse.Namespace) -> int:
    try:
        path = keygen(args.path)
    except RuntimeError as e:
        print(f"ulog solutions: {e}", file=sys.stderr)
        return 2
    print(f"ulog solutions: wrote {path}", file=sys.stderr)
    return 0


def _publish(args: argparse.Namespace) -> int:
    try:
        result = publish(
            args.signature,
            args.writeup,
            args.by,
            private_key_path=args.key_path,
            endpoint=args.endpoint,
        )
    except RuntimeError as e:
        print(f"ulog solutions: {e}", file=sys.stderr)
        return 2
    if "error" in result:
        print(f"ulog solutions publish: {result['error']}", file=sys.stderr)
        return 1
    print(f"ulog solutions publish: {result}", file=sys.stderr)
    return 0


def _fetch(args: argparse.Namespace) -> int:
    results = fetch_signature(args.signature, endpoint=args.endpoint)
    if not results:
        print(f"ulog solutions: no matches for {args.signature}.", file=sys.stderr)
        return 1
    import json as _j
    for r in results:
        print(_j.dumps(r, indent=2))
    return 0
