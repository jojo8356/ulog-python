# Story 7.2: `ulog/_cli/__init__.py` argparse subparser dispatcher

Status: done

**Epic:** 7 — v0.5 release consolidation
**Implements:** Decision C1.

## Completion Notes

- Dispatcher already in place from earlier sprints (verify/repair/etc.).
- Added `cmd_web.py` shim delegating to `ulog.web.cli.main` so
  `ulog web <args>` is now the canonical entry point.
- `ulog --help` lists all 9 subcommands.

## File List

- `ulog/_cli/cmd_web.py` (NEW)
- `ulog/_cli/__init__.py` — register cmd_web
