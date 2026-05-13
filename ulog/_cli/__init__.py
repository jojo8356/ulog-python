"""ULog unified CLI dispatcher (Decision C1).

Single `ulog` console-script entry point. Subcommands live in
`ulog/_cli/cmd_<name>.py` modules and register themselves via
`register(subparsers)`. Each subcommand exposes `run(args) -> int`
returning a POSIX exit code.

Currently shipped subcommands (Story 7.2):
  - web       — open the inspection UI for a stored log file (Story 7.2)
  - verify    — walk the chain and report OK/BROKEN (Story 3.7)
  - repair    — archive orphans + truncate the chain (Story 3.8)
  - purge     — delete rotable rows older than --before (Story 3.9)
  - correlate — over/under-represented dimensions for a filter (Story 4.8)
  - bisect    — first chain record matching a regex (Story 4.8)
  - replay    — iterate matching records or generate a regression test (Story 4.8)
  - trace     — list all records sharing a trace_id (Story 6.2)
  - incidents — CI-gate status + Markdown KPI report (Stories 5.4 / 5.5)
"""

from __future__ import annotations

import argparse
import sys

from . import (
    cmd_bisect,
    cmd_bug_cache,
    cmd_correlate,
    cmd_enable_fts5,
    cmd_export_html,
    cmd_fix,
    cmd_import,
    cmd_incidents,
    cmd_purge,
    cmd_repair,
    cmd_replay,
    cmd_snapshot,
    cmd_solutions,
    cmd_trace,
    cmd_validate_resources,
    cmd_verify,
    cmd_web,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ulog",
        description="ULog forensic archive CLI (v0.5+).",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    cmd_web.register(subparsers)
    cmd_verify.register(subparsers)
    cmd_repair.register(subparsers)
    cmd_purge.register(subparsers)
    cmd_correlate.register(subparsers)
    cmd_bisect.register(subparsers)
    cmd_replay.register(subparsers)
    cmd_trace.register(subparsers)
    cmd_incidents.register(subparsers)
    cmd_export_html.register(subparsers)
    cmd_snapshot.register(subparsers)
    cmd_validate_resources.register(subparsers)
    cmd_import.register(subparsers)
    cmd_fix.register(subparsers)
    cmd_enable_fts5.register(subparsers)
    cmd_bug_cache.register(subparsers)
    cmd_solutions.register(subparsers)

    args = parser.parse_args(argv)
    if args.subcommand is None:
        parser.print_help()
        return 2
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
