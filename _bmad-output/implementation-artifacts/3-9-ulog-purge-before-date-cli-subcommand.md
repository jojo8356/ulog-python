# Story 3.9: `ulog purge --before <date>` CLI subcommand

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-9-ulog-purge-before-date-cli-subcommand`
**Implements:** FR93 (purge rotable records), I4 (immutable rows untouchable), FR92 + Gap G8 (min_retention_days enforcement + pre-chain backfilled rows treated as rotable).
**Built on:** 3.2 (triggers protect immutable), 3.6 (`MIN_RETENTION_DAYS` config), 3.7-3.8 (CLI scaffolding).

## Story

As an **operator running disk-cleanup against rotable records**,
I want **`ulog purge --before <date>`** to delete only rotable rows older than the date, refusing if `min_retention_days` would be violated,
so that **I clean up safely without breaching compliance or invariant I4**.

## Acceptance Criteria

1. **Rotable records older than the date** are deleted (`WHERE immutable=0 AND ts < :before`). Count of deletions printed (FR93).
2. **Immutable records** (`immutable=1`) are NEVER deleted — the trigger blocks them anyway, but the DELETE statement also filters with `immutable=0` so the trigger doesn't even fire (clean exit, no error log).
3. **`min_retention_days` floor**: if `today - <before_date> < min_retention_days`, purge REFUSES with exit code 1 + message `"✗ Refused: --before <date> is within the {n}-day retention floor."` `min_retention_days` comes from `ulog._retention.MIN_RETENTION_DAYS` (set via Story 3.6's setup param). When 0 (default), no refusal.
4. **`--before <ISO date>`** format: `YYYY-MM-DD`. Other formats → argparse error.
5. **Pre-chain backfilled rows** (`record_hash IS NULL` — Gap G8): treated as rotable by default. Purged when older than `--before` (Gap G8 resolution).
6. **`--dry-run`** flag: counts how many rows would be deleted but does NOT delete; exit 0. Useful for staging.
7. **`--confirm`** required for actual delete (mirror of `repair`). Without it, behaves like `--dry-run`. Exit 0 either way, message tagged with "(dry-run)" when not confirmed.
8. **Idempotent**: re-running purge on a freshly-cleaned DB drops 0 records, exit 0.
9. **Exit codes**: 0 success or dry-run; 1 refused (retention floor); 2 argparse/usage error.
10. **Tests** — `tests/test_cli_purge.py`:
    - `test_purge_before_drops_old_rotable_rows`
    - `test_purge_keeps_recent_rotable_rows`
    - `test_purge_keeps_immutable_rows_even_if_old`
    - `test_purge_keeps_pre_chain_null_hash_rows_when_recent` (just confirms NULL-hash rows are included in the rotable set)
    - `test_purge_drops_pre_chain_null_hash_rows_when_old`
    - `test_purge_dry_run_does_not_delete`
    - `test_purge_without_confirm_is_dry_run`
    - `test_purge_invalid_date_format_exits_2`
    - `test_purge_min_retention_floor_refuses_when_too_recent`
    - `test_purge_min_retention_floor_allows_when_safe`
    - `test_purge_python_m_invocation`

## Tasks / Subtasks

- [ ] `ulog/_cli/cmd_purge.py` (NEW) — `register/run` + `_parse_iso_date(s)`.
- [ ] Wire into `ulog/_cli/__init__.py`.
- [ ] Tests per AC10.
- [ ] mypy / ruff / deptry green.

## Dev Notes

### Purge SQL

```sql
DELETE FROM logs
WHERE immutable = 0
  AND ts < :before
```

The `immutable = 0` filter is the load-bearing protection AGAINST the chain trigger firing. Without it the trigger would error on every immutable row in the candidate set.

### Retention check

```python
from datetime import date, timedelta
from ulog._retention import MIN_RETENTION_DAYS

if MIN_RETENTION_DAYS > 0:
    earliest_allowed = date.today() - timedelta(days=MIN_RETENTION_DAYS)
    if before > earliest_allowed:
        # refuse
        ...
```

### References

- [Source: epics.md, lines 1213-1235] — Story 3.9 AC
- [Source: architecture.md, line 1264] — Gap G8 (pre-chain rows rotable)
- [Source: ulog/_retention.py] — `MIN_RETENTION_DAYS` (set by Story 3.6)
- [Source: ulog/_cli/cmd_repair.py] — pattern for CLI command

## Dev Agent Record

### Completion Notes List

- `ulog/_cli/cmd_purge.py` — argparse for `--before <ISO date>`,
  `--confirm`, `--dry-run`. Default (no --confirm and no --dry-run)
  is dry-run behaviour for safety.
- DELETE filtered by `immutable=0` so the chain trigger never fires.
- Retention-floor check uses `_retention.MIN_RETENTION_DAYS`
  (Story 3.6) — refuses with exit 1 when `--before` is within the
  floor.
- Pre-chain rows (record_hash IS NULL — Gap G8) are NOT filtered out
  separately: they satisfy `immutable=0` by default so they fall
  into the rotable purge set.
- 13 / 13 tests in `tests/test_cli_purge.py` green: argparse,
  old/recent rotable, immutable spared, pre-chain treated rotable,
  dry-run, no-confirm, retention floor refuse/allow, idempotent,
  `python -m`.
- 61 affected-area tests green. mypy --strict, ruff, deptry all
  clean.

### File List

- `ulog/_cli/cmd_purge.py` (NEW)
- `ulog/_cli/__init__.py` — imported + registered `cmd_purge`
- `tests/test_cli_purge.py` (NEW) — 13 tests
