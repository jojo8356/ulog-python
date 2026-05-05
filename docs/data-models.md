---
docType: data-models
project_name: ulog-python
date: 2026-05-05
---

# Data Models

ULog persists log records to one of three storage shapes. The SQL
schema is the most opinionated; JSONL and CSV are flat per-record
formats with the same field set.

## SQL schema — `logs` table

Defined in [`ulog/handlers/sql.py`](../ulog/handlers/sql.py) under
`SQLHandler.__init__`. Single table, lazy-created on first `emit()`
via `metadata.create_all()`.

| Column | Type | Nullable | Indexed | Notes |
|---|---|---|---|---|
| `id` | `Integer` (PK, autoincrement) | no | (PK) | row identifier; also used as record-id by the viewer |
| `ts` | `DateTime(timezone=False)` | no | yes (`ix_logs_ts`) | UTC, naive — timezone stripped before insert via `_ts_aware()` |
| `level` | `String(10)` | no | yes (`ix_logs_level`) | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `logger` | `String(255)` | no | yes (`ix_logs_logger`) | dotted name from `record.name` |
| `msg` | `Text` | no | — | rendered message (`record.getMessage()`) |
| `file` | `String(255)` | no | yes (`ix_logs_file`) | source filename (`record.filename`) |
| `line` | `Integer` | no | — | source line number (`record.lineno`) |
| `exc` | `JSON` | yes | — | `{type, msg, tb: [str, …]}` or `null` |
| `context` | `JSON` | yes | — | bound contextvars + record `extra=` payload, or `null` |

**Indexes (4)** — one per common filter axis: `ts`, `level`,
`logger`, `file`. Aligned with PRD-v0.2 NFR-PERF-11 (filter
push-down).

**Backends** — SQLite by default (sqlalchemy URL
`sqlite:///./logs.sqlite`). Postgres / MySQL via URL. SQLAlchemy
`JSON` columns transparently serialise dicts on SQLite (via
`json.dumps`), as native `jsonb` on Postgres.

## Schema versioning

v0.2 **does not ship migrations**. Behavior on existing DB:

- **Fresh DB** — `metadata.create_all(engine)` creates the table.
- **Existing matching schema** — used as-is.
- **Existing schema with missing columns** — `SchemaError` raised
  (in `_verify_or_create_schema`) with the list of missing column
  names. The handler tells the user to delete the DB or add the
  columns manually.

When extending the schema in a future minor version, the upgrade
path needs:

1. A new column added to `Table(…)` AND
2. A migration (e.g. via Alembic) OR documentation that prior DBs
   need a one-time SQL `ALTER TABLE`. The `SchemaError` mechanism
   already surfaces this — the message will list the new column
   names so users know what to add.

## JSON Line schema (`*.jsonl`)

One JSON object per line, written by [`ulog.JsonFormatter`](../ulog/formatters.py)
or [`JSONLineHandler`](../ulog/handlers/json_line.py). Stable schema:

```json
{
  "ts":     "2026-05-05T12:34:56Z",
  "level":  "ERROR",
  "logger": "myapp.audio.engine",
  "msg":    "ROM not found",
  "file":   "engine.py",
  "line":   142,
  "request_id": "abc-123",
  "rom_sha": "deadbeef",
  "exc": {
    "type": "ValueError",
    "msg":  "nope",
    "tb":   ["  File \"…\", line …, in …\n    …"]
  }
}
```

- Top-level fields are the canonical record fields (`ts`, `level`,
  `logger`, `msg`, `file`, `line`).
- Bound contextvars and `extra=` kwargs are merged into the SAME
  level (flat). `request_id`, `rom_sha` above are bound fields, not
  nested under `context`. This matches the v0.1 `JsonFormatter`
  contract (jq-friendly).
- `exc` is the only nested object, present only when the record
  carries `exc_info`.
- UTF-8, no ASCII escaping (`ensure_ascii=False`).
- Compact separators (no spaces) — `separators=(",", ":")`.

## CSV schema (`*.csv`)

Header row written lazily on first `emit()` — see
[`CSVHandler`](../ulog/handlers/csv_file.py). Columns:

```
ts, level, logger, msg, file, line, context_json, exc_json
```

- `context_json` and `exc_json` are JSON-encoded strings (or empty
  string for `None`). The flat-row contract of CSV requires nested
  data to live in single cells.
- RFC 4180; default dialect `"excel"`. UTF-8.
- `newline=""` per stdlib `csv` docs (prevents extra `\r` on Windows).

## Reserved-keys frozenset

When a `LogRecord` carries `extra={…}`, the kwargs become attributes
on the record object alongside stdlib-set attributes. Output
formatters/handlers must distinguish "real `extra=` payload" from
"stdlib bookkeeping". The reserved set:

```python
{
  "args", "asctime", "created", "exc_info", "exc_text", "filename",
  "funcName", "levelname", "levelno", "lineno", "message", "module",
  "msecs", "msg", "name", "pathname", "process", "processName",
  "relativeCreated", "stack_info", "thread", "threadName",
  "taskName",  # py3.12+
}
```

Defined in:
- `ulog/formatters.py:JsonFormatter._RESERVED`
- `ulog/handlers/sql.py:_RESERVED`
- `ulog/handlers/csv_file.py:_RESERVED`

**These three copies must stay in lockstep.** Adding a new merging
path requires another copy. When stdlib introduces a new bookkeeping
attribute (next: when?), all three must be updated.

## Cache file paths (default profiles)

`ulog.default_db_path(profile)` resolves canonical SQLite paths:

| Profile | Path | Auto-selected when |
|---|---|---|
| `prod` | `${XDG_CACHE_HOME or ~/.cache}/ulog/prod.sqlite` | `profile='auto'` and not in pytest |
| `test` | `${XDG_CACHE_HOME or ~/.cache}/ulog/test.sqlite` | `profile='auto'` and pytest is running (detected via `PYTEST_CURRENT_TEST` env var or `pytest in sys.modules`) |

Unknown profiles → `ValueError("unknown profile …")`. Only `prod` and
`test` are valid in the tuple `PROFILES = ("prod", "test")`. `auto`
is a third caller-side choice that resolves to one of the two
defined profiles.
