"""`ulog web` — Django viewer subcommand (Story 7.2 / Decision C1).

Replaces the standalone `ulog-web` console_script (removed in 7.3).
All argument parsing + serving logic lives in `ulog.web.cli` —
this module is a thin shim that delegates to it.
"""

from __future__ import annotations

import argparse
from typing import Any


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "web",
        help="Open the inspection UI for a stored log file.",
        # `add_help=False` so the inner parser owns the --help message;
        # users typing `ulog web --help` get the full ulog-web help text.
        add_help=False,
    )
    # Capture every arg verbatim — `ulog.web.cli.main` re-parses them
    # with its own argparse setup. This keeps a single source of truth.
    sp.add_argument("args", nargs=argparse.REMAINDER)
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    from ulog.web.cli import main as web_main

    forwarded: list[str] = list(args.args or [])
    return web_main(forwarded)
