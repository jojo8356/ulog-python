# Story 6.2: `ulog trace <id>` CLI subcommand

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-2-ulog-trace-id-cli-subcommand`
**Implements:** FR110.
**Built on:** Story 6.1 (trace_id stamped in context), Story 4.8 (CLI scaffolding).

## Story

As an engineer debugging a distributed bug,
I want `ulog trace <trace_id> --db ./logs.sqlite` to list all records sharing that trace_id chronologically,
so that I see the full causal chain across services in one view.

## Acceptance Criteria

1. `ulog trace <trace_id> --db DB` lists records where `context.trace_id == <trace_id>`, sorted by `ts ASC`.
2. Output columns: `ts  level  logger  msg` aligned.
3. No match → "No records for trace_id <id>." + exit 0.
4. `--db` is required; missing → exit 2 with stderr.
5. Tests cover happy path / no-match / missing-db.

## Implementation sketch

```python
# ulog/_cli/cmd_trace.py
def run(args):
    # SELECT … FROM logs WHERE json_extract(context, '$.trace_id') = :tid ORDER BY ts ASC
```

## Dev Agent Record

### Completion Notes List

- `ulog/_cli/cmd_trace.py` (NEW). SQLite `json_extract(context, '$.trace_id')`
  filter + ORDER BY ts ASC.
- Registered in dispatcher.
- 3 / 3 tests green (happy path, no-match exit 0, missing DB exit 2).

### File List

- `ulog/_cli/cmd_trace.py` (NEW)
- `ulog/_cli/__init__.py` — registered.
- `tests/test_cli_trace.py` (NEW)
