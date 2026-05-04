# Storage handlers (SQL / JSON / CSV)

ULog v0.2 ships three persistent handlers. Each is a stdlib
`logging.Handler` subclass — they coexist with the v0.1 stream handler
and with any user-installed handlers (file rotation, syslog, Sentry…).

## SQL — `ulog.SQLHandler` (recommended)

Backed by SQLAlchemy. SQLite by default — single file, no daemon. Postgres
or MySQL via the URL.

### Schema (single table, indexed)

```sql
CREATE TABLE logs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      DATETIME NOT NULL,
    level   VARCHAR(10) NOT NULL,
    logger  VARCHAR(255) NOT NULL,
    msg     TEXT NOT NULL,
    file    VARCHAR(255) NOT NULL,
    line    INTEGER NOT NULL,
    exc     JSON NULL,
    context JSON NULL
);
CREATE INDEX ix_logs_ts ON logs(ts);
CREATE INDEX ix_logs_level ON logs(level);
CREATE INDEX ix_logs_logger ON logs(logger);
CREATE INDEX ix_logs_file ON logs(file);
```

### Configuration

```python
ulog.setup(
    handlers=['sql'],
    sql_url='sqlite:///./logs.sqlite',  # or postgresql://, mysql://
    sql_table='logs',
    sql_batch_size=100,  # flush threshold
)
```

### Example query

```sql
-- All ERRORs from the audio renderer in the last hour:
SELECT ts, msg, context FROM logs
WHERE level = 'ERROR' AND logger LIKE 'qlnes.audio.renderer%'
  AND ts >= datetime('now', '-1 hour')
ORDER BY ts DESC;
```

## JSON — `ulog.JSONLineHandler`

One JSON object per line, appended to a file. Schema matches the
v0.1 `JsonFormatter` byte-for-byte.

```python
ulog.setup(handlers=['json'], json_path='./logs.jsonl')
```

### Example with jq

```bash
# all ERRORs in a file:
jq 'select(.level=="ERROR")' logs.jsonl

# pluck only msg + context.rom_sha:
jq '{msg, rom: .rom_sha}' logs.jsonl
```

## CSV — `ulog.CSVHandler`

RFC 4180. Bound context and exception serialized as JSON-stringified
columns, so spreadsheets see them as raw text but a JSON parser can
re-hydrate.

Columns: `ts, level, logger, msg, file, line, context_json, exc_json`.

```python
ulog.setup(handlers=['csv'], csv_path='./logs.csv')
```

### Gotcha: messages with commas

CSV quoting is honored — a `msg` containing `,` or `"` will be
properly quoted. Use `dialect='unix'` for stricter quoting if you're
piping through tools that disagree on dialect.

## Multi-handler

All three compose:

```python
ulog.setup(
    handlers=['stream', 'sql', 'json', 'csv'],
    sql_url='sqlite:///./logs.sqlite',
    json_path='./logs.jsonl',
    csv_path='./logs.csv',
)
```

Every record is emitted to terminal AND persisted to all three storage
backends. Useful when you want to give the user a CSV they can open in
Excel AND a SQLite for `ulog-web` triage.
