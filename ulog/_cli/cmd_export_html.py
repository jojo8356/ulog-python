"""`ulog export-html` — static HTML export subcommand (Story 8.2)."""

from __future__ import annotations

import argparse
from typing import Any


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "export-html",
        help="Render a stored log file to a self-contained directory of HTML.",
        add_help=False,
    )
    sp.add_argument("args", nargs=argparse.REMAINDER)
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    from ulog.web.export.exporter import cli_main

    return cli_main(list(args.args or []))
