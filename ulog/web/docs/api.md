# Python API reference

ULog re-exports everything you need from the top-level `ulog` namespace.

## Setup

### `ulog.setup(...)`

Configure a managed handler on the named (or root) logger. Idempotent
— call it as many times as you want; subsequent calls replace the
previous configuration.

Arguments:
- `level: str | int` — minimum level to emit. Defaults to `'INFO'`.
- `format: str` — formatter name. Built-ins: `qlnes`, `simple`,
  `verbose`, `json`. Custom: register via `register_formatter()`.
- `color: 'auto' | 'always' | 'never'` — TTY-detect by default,
  honors `NO_COLOR` env.
- `stream` — defaults to `sys.stderr`. Tests inject `io.StringIO`.
- `name: str | None` — logger to configure. `None` = root.
- `propagate: bool` — bubble to parent. Default `False` for named.
- `handlers: list[str]` — list of handler kinds. Default `['stream']`.
  Recognized: `stream`, `sql`, `json`, `csv`.
- `sql_url, sql_table, sql_batch_size` — SQLHandler.
- `json_path` — JSONLineHandler.
- `csv_path` — CSVHandler.
- `**formatter_kwargs` — forwarded to the formatter (e.g. `prefix='myapp'`).

Returns the configured `logging.Logger`.

### `ulog.get_logger(name=None)`

Thin passthrough to `logging.getLogger(name)`. Works whether or not
`setup()` has been called.

### `ulog.set_level(level, name=None)`

Adjust an existing logger's level without re-running setup.

### `ulog.is_configured(name=None)`

True if `setup()` has been called for that logger name.

## Context binding

### `ulog.bind(**fields)`, `ulog.unbind(*keys)`, `ulog.clear()`

Push key/value pairs onto a `contextvars.ContextVar`. The JSON
formatter (and verbose, and the SQL/JSON/CSV handlers) merge the
bound dict into every emitted record.

### `with ulog.context(**fields):`

Block-scoped binding. Restores the previous bound dict on exit
(including exception paths).

### `ulog.get_bound() -> dict`

Snapshot of the currently bound fields (read-only copy).

## Formatters

- `QlnesFormatter(color_on, prefix='qlnes')` — `<prefix>: <level>: <msg>`
- `SimpleFormatter(color_on)` — `[<LEVEL>] <msg>`
- `VerboseFormatter(color_on)` — timestamps + logger + bound fields + file:line
- `JsonFormatter()` — one JSON object per record

### `ulog.register_formatter(name, cls)`

Register a custom `logging.Formatter` subclass.

## Storage handlers

- `SQLHandler(url, table='logs', batch_size=100)` — SQLAlchemy persistence
- `JSONLineHandler(path, append=True)` — one JSON object per line
- `CSVHandler(path, dialect='excel')` — RFC 4180 CSV

## Constants

- `ulog.LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')`

## Exceptions

- `ulog.SchemaError` — raised by `SQLHandler` when an existing DB
  schema doesn't match what ULog expects. v0.2 doesn't ship
  migrations; v0.5 emits a copy-paste `ALTER TABLE` SQL block.

## v0.5 — chain integrity APIs

- `ulog.replay(db, where_dsl=None, on=callback)` — iterate records
  in chain order. Records are `MappingProxyType` — mutation raises.
- `ulog.is_replaying()` → `bool` — True inside a `replay()` callback
  / `replay_records(...)` block.
- `ulog.testing.replay_records(records)` — context manager for tests.
- `ulog.correlate(filter_dsl, db)` → `CorrelationReport` with `top_over`
  / `bottom_under` rows by lift.
- `ulog.bisect(pattern, db)` → `BisectResult | None` — first match.

## v0.5 — incidents APIs

- `ulog.resolve(incident_hash, by, note="")` — emits RESOLVED record.
  Hex prefix ≥4 chars. Raises `LookupError` if hash absent /
  ambiguous, `RuntimeError` if no SQLHandler configured.
- `ulog.reopen(incident_hash, reason="")` — emits REOPENED record.
- `ulog.compute_states(records)` → `dict[hash, IncidentState]` — chain
  walk, latest-wins state per FR106.
- `ulog.IncidentState(incident_hash, state, last_action, opened_ts,
  last_action_ts)` — frozen dataclass; `state ∈ {open, closed, reopened}`.

## v0.5 — setup() new keyword args

| Arg | Default | Purpose |
|---|---|---|
| `integrity` | `None` | `"hash-chain"` enables Epic 3 features. |
| `min_retention_days` | `0` | Trigger flips `immutable=1` after N days. |
| `issue_template_url` | `None` | URL with `{msg}` / `{body}` / `{level}` etc. placeholders for the detail-page "Open issue" button. |
