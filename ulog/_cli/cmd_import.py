"""`ulog import` — log file ingestion (PRD-v0.17)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ulog._import.importer import ImportOptions, import_files
from ulog._import.parsers import PARSER_REGISTRY


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "import",
        help="Ingest external log files into a ulog SQLite DB (PRD-v0.17).",
    )
    sp.add_argument("inputs", nargs="+", type=Path, help="Input file paths.")
    sp.add_argument("--db", required=True, type=Path, help="Output SQLite DB path.")
    sp.add_argument(
        "--format",
        default="auto",
        help=(
            f"Source format. Recognised: auto, {','.join(sorted(PARSER_REGISTRY))}, csv, "
            "or regex:<pattern>. Default: auto (detect)."
        ),
    )
    sp.add_argument("--strict", action="store_true", help="Abort on first parse error.")
    sp.add_argument("--encoding", default="utf-8", help="Input file encoding (default UTF-8).")
    sp.add_argument(
        "--source-tag",
        default="",
        help="Constant `context.import_source=<tag>` attached to each row.",
    )
    sp.add_argument("--batch-size", type=int, default=500, help="SQL batch insert size.")
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    for p in args.inputs:
        if not p.exists():
            print(f"ulog import: input not found: {p}", file=sys.stderr)
            return 2
    opts = ImportOptions(
        output_db=args.db,
        format=args.format,
        strict=args.strict,
        encoding=args.encoding,
        source_tag=args.source_tag,
        batch_size=args.batch_size,
    )
    from ulog._import.parsers import ParseError

    try:
        result = import_files(list(args.inputs), opts)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    except ParseError as e:
        print(f"ulog import: invalid format: {e}", file=sys.stderr)
        return 2
    return 0 if result.skipped == 0 or not args.strict else 1
