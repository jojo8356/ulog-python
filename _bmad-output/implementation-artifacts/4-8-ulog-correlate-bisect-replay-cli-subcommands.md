# Story 4.8: `ulog correlate` / `bisect` / `replay` CLI subcommands

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-8-ulog-correlate-bisect-replay-cli-subcommands`
**Implements:** FR104 (CLI subcommands).
**Built on:** Stories 4.1, 4.3, 4.4, 4.5, 4.6, 4.7.

## Story

Expose three new subcommands under the consolidated `ulog` binary:

- `ulog correlate '<filter>' --db PATH` → prints CorrelationReport.
- `ulog bisect '<pattern>' --db PATH` → prints first-match record.
- `ulog replay '<filter>' --db PATH [--to-pytest PATH]` → iterates or generates.

## Acceptance Criteria

1. **`ulog correlate <filter> --db DB [--top N] [--bottom M]`** — filter is a DSL string. Output: ASCII table with `top_over` first, then `bottom_under`, then `axis_rows`, and a summary line (`filter: N, baseline: M, wall: <ms>`). Warning rows annotated with `⚠ small_sample` / `(axis)`.
2. **`ulog bisect <pattern> --db DB`** — pattern is a regex. Output: `Found at chain_pos=N: <msg>` + context table. No match → `No record matched pattern.` + exit 0.
3. **`ulog replay <filter> --db DB [--to-pytest PATH] [--topic SLUG] [--force]`** — filter is a DSL string. Without `--to-pytest`: prints each matching record (one line). With `--to-pytest`: generates the regression test (Story 4.3) at PATH.
4. **Exit codes**: 0 on success, 1 on a "not found" condition that the user might care about (bisect no-match is exit 0 by convention), 2 on usage error.
5. **`python -m ulog._cli <subcommand>`** works alongside the installed `ulog` console-script.
6. **Tests** — `tests/test_cli_queryability.py`:
   - `test_correlate_cli_prints_report`
   - `test_correlate_cli_invalid_filter_exit_2`
   - `test_bisect_cli_prints_first_match`
   - `test_bisect_cli_no_match_exit_0`
   - `test_bisect_cli_invalid_regex_exit_2`
   - `test_replay_cli_prints_records`
   - `test_replay_cli_to_pytest_generates_file`
   - `test_subcommands_registered_in_dispatcher` (smoke).

## Tasks / Subtasks

- [ ] `ulog/_cli/cmd_correlate.py` (NEW).
- [ ] `ulog/_cli/cmd_bisect.py` (NEW).
- [ ] `ulog/_cli/cmd_replay.py` (NEW).
- [ ] Register all 3 in `ulog/_cli/__init__.py`.
- [ ] 8 tests.

## Dev Agent Record

### Completion Notes List

- 3 new CLI subcommands: `correlate`, `bisect`, `replay`. All
  registered in `ulog/_cli/__init__.py` alongside verify/repair/purge.
- `cmd_correlate` prints the CorrelationReport as an ASCII table
  with `top_over` / `bottom_under` / `axis_rows` sections + summary.
  ⚠ small_sample / (axis) annotations on warning rows. `∞` glyph
  for infinite lift.
- `cmd_bisect` prints first match with chain_pos + ts + level +
  logger + file:line + msg + context table. No-match → exit 0 with
  "No record matched pattern."
- `cmd_replay`: without `--to-pytest` prints each matching record
  one-line; with `--to-pytest PATH` delegates to `replay_to_pytest`
  (Story 4.3). Internally compiles DSL → SQL literal for 4.3's
  `where=` API (acceptable: CLI is user's own shell + DSL parser
  pre-rejects shell metachars).
- Exit codes: 0 success, 2 on usage / parse / file errors.
- 9 / 9 tests in `tests/test_cli_queryability.py` green: correlate
  prints report + invalid filter + nonexistent DB; bisect prints
  match + no-match + invalid regex; replay prints records +
  to-pytest generates file; dispatcher smoke.
- mypy --strict / ruff check / ruff format / deptry all clean.

### File List

- `ulog/_cli/cmd_correlate.py` (NEW)
- `ulog/_cli/cmd_bisect.py` (NEW)
- `ulog/_cli/cmd_replay.py` (NEW)
- `ulog/_cli/__init__.py` — 3 new subcommands registered.
- `tests/test_cli_queryability.py` (NEW) — 9 tests.
