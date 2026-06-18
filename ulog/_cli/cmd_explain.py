"""`ulog explain` — span waterfall tree (PRD-v0.7 phase 3).

Walks all `logger='ulog.span'` records in a DB and prints a tree
reconstructed from `parent_span_id`. Indented; each line carries
name + duration + status. Like `EXPLAIN ANALYZE` for tests.

Usage:
    ulog explain --db ./logs.sqlite              # all root spans
    ulog explain --db ./logs.sqlite --root 4f2a  # one specific tree
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "explain",
        help="Print a waterfall tree of recorded spans (PRD-v0.7).",
    )
    sp.add_argument("--db", required=True, type=Path)
    sp.add_argument(
        "--root",
        default="",
        help="Render only the tree rooted at this span_id (hex prefix OK).",
    )
    sp.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max number of root trees to render (default 20).",
    )
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"ulog explain: DB not found: {args.db}", file=sys.stderr)
        return 2

    spans = _load_spans(args.db)
    if not spans:
        print("ulog explain: no span records found.", file=sys.stderr)
        return 1

    children: dict[str | None, list[dict[str, Any]]] = {}
    for s in spans:
        children.setdefault(s["parent_span_id"], []).append(s)
    for kids in children.values():
        kids.sort(key=lambda s: s["chain_pos"])

    if args.root:
        prefix = args.root.lower()
        roots = [s for s in spans if s["span_id"].startswith(prefix)]
        if not roots:
            print(f"ulog explain: no span matches prefix {args.root!r}.", file=sys.stderr)
            return 1
    else:
        roots = children.get(None, [])
    if len(roots) > args.limit:
        print(
            f"ulog explain: showing {args.limit} of {len(roots)} root spans "
            f"(pass --limit to override).",
            file=sys.stderr,
        )
        roots = roots[: args.limit]

    for root in roots:
        _render(root, children, depth=0)
    return 0


def _load_spans(db: Path) -> list[dict[str, Any]]:
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, chain_pos, context FROM logs "
                "WHERE logger='ulog.span' ORDER BY id"
            )
        ).all()
    engine.dispose()
    out: list[dict[str, Any]] = []
    for r in rows:
        ctx = json.loads(r[2]) if r[2] else {}
        if "span_name" not in ctx:
            continue
        out.append(
            {
                "id": r[0],
                "chain_pos": r[1] or 0,
                "span_id": ctx.get("span_id", ""),
                "parent_span_id": ctx.get("parent_span_id"),
                "span_name": ctx.get("span_name", ""),
                "span_ms": ctx.get("span_ms", 0),
                "span_status": ctx.get("span_status", "ok"),
            }
        )
    return out


def _render(
    node: dict[str, Any],
    children: dict[str | None, list[dict[str, Any]]],
    depth: int,
) -> None:
    bar = "│ " * depth
    glyph = "─" if not children.get(node["span_id"]) else "┬"
    status = node["span_status"]
    marker = "✗" if status == "fail" else " "
    print(
        f"{bar}└{glyph} {marker} {node['span_name']:<30} "
        f"{node['span_ms']:>8.2f}ms  id={node['span_id']}"
    )
    for child in children.get(node["span_id"], []):
        _render(child, children, depth + 1)
