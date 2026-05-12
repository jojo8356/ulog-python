# Story 5.4: `ulog incidents --status` CLI + exit code

Status: done

**Epic:** 5 — v0.5 Incident lifecycle
**Story key:** `5-4-ulog-incidents-status-cli-exit-code`
**Implements:** FR107 (CI gate).

## Story

As a CI gate enforcer,
I want `ulog incidents --status open` to print all open incidents
and return an exit code = open count,
so that I can fail the build if open incidents exceed a threshold.

## Acceptance Criteria

1. `ulog incidents --db <db>` (no flags) prints a summary line and
   returns exit code = open count.
2. `--status open|closed|reopened|all` filters and prints one
   incident per line: `#<short-hash>  <ts>  [<state>]  age=<rel>`.
3. Exit code is always the open count (CI-friendly).
4. Missing DB → exit 2, "not found" message.

## Dev Agent Record

### Completion Notes List

- New module `ulog/_cli/cmd_incidents.py` (shared with Story 5.5).
- Wired into `ulog/_cli/__init__.py`.
- 4 / 4 tests for status mode green.

### File List

- `ulog/_cli/cmd_incidents.py` (NEW)
- `ulog/_cli/__init__.py` — register
- `tests/test_incidents_cli.py` (NEW; shared with 5.5)
