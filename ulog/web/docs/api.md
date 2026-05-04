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
  migrations.
