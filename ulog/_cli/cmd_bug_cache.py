"""`ulog bug-cache` CLI (PRD-v0.14).

Phase 1: storage + manual JSON import. Phase 2 (later) adds the
actual SO Data Dump / GitHub issues / docs scraper invoked by
`ulog bug-cache refresh`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ulog._bug_cache import clear, count, default_cache_path, import_from_json, search_by_signature


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "bug-cache",
        help="Manage the local known-bugs cache (PRD-v0.14).",
    )
    sub = sp.add_subparsers(dest="bug_subcommand")
    sp.set_defaults(run=run)

    rs = sub.add_parser("refresh", help="Refresh the cache (scraper deferred; --source-file for now).")
    rs.add_argument("--source-file", type=Path, help="JSON file of curated entries.")
    rs.add_argument("--cache", type=Path, default=None)
    rs.set_defaults(run_sub=_refresh)

    sh = sub.add_parser("search", help="Search the cache by signature.")
    sh.add_argument("signature")
    sh.add_argument("--cache", type=Path, default=None)
    sh.set_defaults(run_sub=_search)

    ls = sub.add_parser("status", help="Print cache row count + path.")
    ls.add_argument("--cache", type=Path, default=None)
    ls.set_defaults(run_sub=_status)

    cl = sub.add_parser("clear", help="Drop the cache file.")
    cl.add_argument("--cache", type=Path, default=None)
    cl.set_defaults(run_sub=_clear)


def run(args: argparse.Namespace) -> int:
    sub = getattr(args, "run_sub", None)
    if sub is None:
        print("ulog bug-cache: missing subcommand (refresh/search/status/clear)", file=sys.stderr)
        return 2
    return int(sub(args))


def _resolve_cache(args: argparse.Namespace) -> Path:
    return Path(args.cache) if args.cache else default_cache_path()


def _refresh(args: argparse.Namespace) -> int:
    cache = _resolve_cache(args)
    if not args.source_file:
        print(
            "ulog bug-cache refresh: the full scraper is deferred. "
            "Pass --source-file <curated.json> to bulk-import known matches.",
            file=sys.stderr,
        )
        return 2
    if not args.source_file.exists():
        print(f"ulog bug-cache: source not found: {args.source_file}", file=sys.stderr)
        return 2
    n = import_from_json(cache, args.source_file)
    print(f"ulog bug-cache: imported {n} entries into {cache}", file=sys.stderr)
    return 0


def _search(args: argparse.Namespace) -> int:
    cache = _resolve_cache(args)
    matches = search_by_signature(cache, args.signature)
    if not matches:
        print("ulog bug-cache: no matches.", file=sys.stderr)
        return 1
    for m in matches:
        flag = "★ accepted" if m["accepted"] else "  "
        print(f"{flag}  [{m['source']}] {m['title']}")
        if m["url"]:
            print(f"    {m['url']}")
    return 0


def _status(args: argparse.Namespace) -> int:
    cache = _resolve_cache(args)
    n = count(cache)
    state = "present" if cache.exists() else "absent"
    print(f"ulog bug-cache: {n} entries · {state} · {cache}", file=sys.stderr)
    return 0


def _clear(args: argparse.Namespace) -> int:
    cache = _resolve_cache(args)
    clear(cache)
    print(f"ulog bug-cache: cleared {cache}", file=sys.stderr)
    return 0
