"""ULog unified CLI dispatcher (Decision C1).

Single `ulog` console-script entry point. Subcommands live in
`ulog/_cli/cmd_<name>.py` modules and register themselves via
`register(subparsers)`. Each subcommand exposes `run(args) -> int`
returning a POSIX exit code.

Currently shipped subcommands (Story 3.7+):
  - verify   — walk the chain and report OK/BROKEN (Story 3.7)
  - repair   — archive orphans + truncate the chain (Story 3.8)
  - purge    — delete rotable rows older than --before (Story 3.9)
"""

from __future__ import annotations

import argparse
import sys

from . import cmd_purge, cmd_repair, cmd_verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ulog",
        description="ULog forensic archive CLI (v0.5+).",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    cmd_verify.register(subparsers)
    cmd_repair.register(subparsers)
    cmd_purge.register(subparsers)

    args = parser.parse_args(argv)
    if args.subcommand is None:
        parser.print_help()
        return 2
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
