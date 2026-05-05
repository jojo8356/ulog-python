---
docType: architecture
project_name: ulog-python
date: 2026-05-05
project_type: library
---

# ULog — Architecture

## Executive summary

ULog is a **thin layer on Python's stdlib `logging`**. Three rules
shape the architecture:

1. **Stdlib-compatible by construction.** ULog never forks the logger
   hierarchy — every `setup()` call installs handlers on the named
   stdlib logger (or root). Code that already does
   `logging.getLogger(__name__)` keeps working unchanged, and so do
   third-party libs (`requests`, `urllib3`, `boto3`, …).
2. **Zero PyPI runtime deps in the core.** Every optional-dep import
   (`sqlalchemy`, `django`, `ucolor`) is *lazy* — performed inside
   the function/handler that needs it. `import ulog` works on a fresh
   Python install with no extras.
3. **Idempotent setup.** Each handler ULog installs gets the
   `_ulog_managed = True` attribute. Subsequent `setup()` calls remove
   only those handlers (preserving user-installed ones) before
   re-installing.

## Technology stack

See [`project-overview.md`](./project-overview.md) for the
full version table. Key constraints:

- Python `>=3.10` (uses PEP 604 union types `X | None`, `tuple[…]`,
  `dict[…]`, `Literal` from `typing`).
- `from __future__ import annotations` on every module to keep those
  types working at runtime on 3.10.
- `mypy --strict` enforced.

## High-level shape

```
                          ┌───────────────────────────────────────────────┐
                          │                  user code                    │
                          │   import ulog                                 │
                          │   ulog.setup(handlers=['stream','sql','json'])│
                          │   log = ulog.get_logger(__name__)             │
                          │   log.error("boom", extra={...})              │
                          └─────────────────────┬─────────────────────────┘
                                                │ stdlib logging.LogRecord
                                                ▼
                          ┌───────────────────────────────────────────────┐
                          │ logging.Logger (root or named, stdlib)        │
                          │ handlers: [_ulog_managed=True ...]            │
                          └───────┬─────────┬─────────┬─────────┬─────────┘
                                  │         │         │         │
                                  ▼         ▼         ▼         ▼
                          StreamHandler  SQLHandler JSONLine  CSVHandler
                              + qlnes/    sqlalchemy core    rfc4180
                              simple/    JSON columns       header lazy
                              verbose/   atexit flush       on first emit
                              json
                              formatter
                                  │         │         │         │
                                  ▼         ▼         ▼         ▼
                              stderr     ~/.cache/  *.jsonl   *.csv
                                         ulog/<profile>.sqlite

   ───── observation surface (ulog-web) ─────────────────────────────────
                                            │
                                            ▼
                          ┌───────────────────────────────────────────────┐
                          │ ulog-web → Django (ulog.web.viewer)           │
                          │   adapters: SQLiteAdapter / JSONLAdapter /    │
                          │             CSVAdapter (uniform Record)       │
                          │   views: list / detail / api / docs           │
                          └───────────────────────────────────────────────┘
```

## Component model

Each module has a single responsibility. Lazy boundaries protect the
zero-deps invariant.

| Module | Role | Notes |
|---|---|---|
| `ulog.setup` | `setup()` orchestrator | Dispatches `handlers=[…]` to `_build_handler(kind)`. Lazy-imports each handler module. Auto-detects `profile` from `pytest in sys.modules` / `PYTEST_CURRENT_TEST`. |
| `ulog.formatters` | 4 built-ins + registry | `_RESERVED` frozenset is the canonical reserved-keys list (mirrored in `handlers/sql.py` + `handlers/csv_file.py`). |
| `ulog._color` | Colour decision + ANSI emission | `resolve_color()` honors `NO_COLOR`, `TERM=dumb`, `isatty()`. `color_level()` uses ucolor truecolor when available, falls back to 8-color ANSI. |
| `ulog.context` | contextvars-based binding | One `ContextVar[dict]`. Mutation is via fresh-dict copy so concurrent tasks see consistent state. |
| `ulog.handlers.sql` | SQLAlchemy `SQLHandler` | Lazy-import sqlalchemy in `__init__`. Lock-protected buffer flushed at `batch_size`, on `flush()`, on `atexit`. `SchemaError` on column drift — no migrations in v0.2. |
| `ulog.handlers.json_line` | JSONL append handler | `logging.FileHandler` subclass. Always uses `JsonFormatter` regardless of `setup(format=)`. |
| `ulog.handlers.csv_file` | CSV append handler | RFC 4180. Lazy-opens on first `emit`, so a missing parent dir errors at write-time, not handler construction. |
| `ulog.web.cli` | `ulog-web` CLI | Bypasses `runserver` (skips banner + migration check) by driving WSGI directly via `django.core.servers.basehttp.run`. |
| `ulog.web.settings` | Minimal Django settings | `:memory:` stub DB + `MIGRATION_MODULES = {"contenttypes": None}` (silences the migrations warning). |
| `ulog.web.viewer.adapters` | Storage-agnostic read layer | One `Adapter` interface, three impls. SQLite filters at SQL level; JSONL/CSV load fully into memory. |
| `ulog.web.viewer.views` | Django views | List / detail / api-records / docs. In-house `_markdown_to_html()` (~60 LOC) renders `ulog/web/docs/*.md` so no markdown lib is required. |

## Architectural patterns & invariants

### Idempotent handler installation

`setup()` is contract-bound to be idempotent (FR2). The mechanism:

```python
# ulog/setup.py — install path
for h in list(logger.handlers):
    if getattr(h, "_ulog_managed", False):
        h.close()                # release file/DB connections
        logger.removeHandler(h)
# ... build new handler ...
handler._ulog_managed = True
logger.addHandler(handler)
```

User-installed handlers (file rotators, syslog, Sentry…) are
**preserved**. Tests in `tests/test_setup.py` lock this contract.

### Reserved-keys frozenset triplication

`record.__dict__` contains many stdlib-set attributes (`args`,
`created`, `levelname`, …) that must NOT be merged into output as
`extra=` payload. The `_RESERVED` frozenset enumerates them. It is
duplicated **verbatim** in three places:

- `ulog/formatters.py:_RESERVED` (used by `JsonFormatter`)
- `ulog/handlers/sql.py:_RESERVED`
- `ulog/handlers/csv_file.py:_RESERVED`

When stdlib introduces a new reserved attribute (e.g. `taskName` in
3.12), all three copies must update in lockstep. **Adding a new
extra-merging code path requires adding a new `_RESERVED` copy.**

### Profile auto-detection

`profile='auto'` resolves at `setup()` time (`ulog/setup.py:_auto_profile`):

```python
if os.environ.get("PYTEST_CURRENT_TEST"):
    return "test"
if "pytest" in sys.modules:
    return "test"
return "prod"
```

Reasoning: `PYTEST_CURRENT_TEST` is per-test (set after fixtures), but
`pytest in sys.modules` covers fixture-setup time and pytest-internal
calls. Both checks together cover the lifecycle.

This is what enforces the cache split: prod runs land in
`~/.cache/ulog/prod.sqlite`, pytest runs in
`~/.cache/ulog/test.sqlite`. Tests verify `auto` lands in `test`
because pytest is itself running.

### Lazy optional-dep imports

The library is `import`-safe with zero PyPI deps. The pattern:

```python
# ulog/setup.py:_build_handler
if kind == "sql":
    from .handlers.sql import SQLHandler   # ← lazy
    return SQLHandler(...)
```

```python
# ulog/handlers/sql.py:SQLHandler.__init__
self._lock = threading.Lock()              # ← initialise lock + buffer
self._buffer = []                          #   FIRST so a degraded
                                           #   handler (e.g. sqlalchemy
                                           #   import error below) is
from sqlalchemy import (...)               #   still safe to flush()
self._engine = create_engine(...)
```

Reason for the `_lock`/`_buffer` ordering: `logging.Handler.__init__`
already registers the handler in the global handler list. If the
sqlalchemy import below fails, `logging.shutdown()` will still iterate
this instance and call `flush()`. Without the early init, `flush()`
would crash on a missing `_lock`. The hard-won fix is documented in
the file's docstring and preserved across edits.

### Non-blocking logging

Per stdlib `logging.Handler.emit` contract — handlers MUST NOT raise.
Three places have explicit exception swallows with `# noqa: BLE001`:

- `ulog/setup.py:169` — handler-cleanup `close()` failures
- `ulog/handlers/sql.py:129` — `emit()` errors → `self.handleError(record)`
- `ulog/handlers/sql.py:144` — DB unreachable → drop batch
- `ulog/handlers/sql.py:214` — `_safe_flush()` (atexit hook)
- `ulog/handlers/csv_file.py:107` — same shape

The DB-unreachable drop (`sql.py:144`) is documented as a future-improvable
choice: a `FUTURE: capture into a fallback FileHandler` comment marks
the place. v0.2 chose throughput-and-survival over delivery-guarantee.

### Adapter shape — uniform `Record`

Three `Adapter` impls (`SQLite` / `JSONL` / `CSV`) all return a
`QueryResult` dataclass with the same shape:

```python
QueryResult(
    records=[Record(id, ts, level, logger, msg, file, line, context, exc)],
    total=int,
    page=int,
    page_size=int,
    sector_counts={"app": 5, "app.audio": 4, ...},  # rolled-up logger prefixes
    file_counts={"foo.py": 3, ...},
    level_counts={"INFO": 3, ...},
    bound_keys=["request_id", "rom_sha", ...],     # auto-detected
)
```

This lets the Django views stay storage-agnostic — they call
`adapter.query(filters, page)` and render the result identically
regardless of where the logs live.

### Ghost counts (PRD-v0.2.1)

In the inspection UI, ticking a level filter (say `INFO`) must NOT
zero out the counts of WARNING / ERROR. Each per-axis count is
computed against a where-clause that **excludes** that axis's own
filter:

- `level_counts` ← all-filters-EXCEPT-level
- `sector_counts` (rolled up from `logger_counts`) ← all-filters-EXCEPT-loggers
- `file_counts` ← all-filters-EXCEPT-files

The `records` list and `total` use the FULL filter (correct).

Both adapters (SQLite via SQL `WHERE`, JSONL/CSV in Python with
`Counter`) implement this contract. Tests in `tests/test_web.py`
explicitly regression-test it on each axis (PRD-v0.2.1 was a patch
that fixed the missing behavior).

## Performance posture

- Stream handler: stdlib `StreamHandler`, no overhead beyond stdlib.
- SQL handler: in-memory buffer, batched insert (default `batch_size=100`),
  `atexit` flush. Indexes on `ts`, `level`, `logger`, `file` for
  the four common filter axes.
- JSONL/CSV adapters in the viewer load the whole file once into a
  Python list. For million-record files, this gets slow — PRD-v0.3
  notes streaming as a possible future improvement.
- `_markdown_to_html` is ~60 LOC, no third-party markdown lib. Trades
  feature completeness for zero-deps and predictable behavior.

## Testing strategy

- pytest-only, ~70 tests, `testpaths = ["tests"]`.
- Hermetic: every test that touches the SQL handler uses `tmp_path`.
  Adapters & Django views are tested against per-test SQLite fixtures
  built via `ulog.setup(handlers=['sql'], …)` itself — so the test
  suite exercises the full record-build path, not a hand-rolled mock
  schema.
- The `_isolate_logging` autouse fixture in each test module strips
  `_ulog_managed` handlers post-test so suite ordering doesn't leak.
- Django views are exercised via `django.test.Client` after a
  `django.setup()` triggered through env vars (`DJANGO_SETTINGS_MODULE`,
  `ULOG_LOGS_PATH`, `ULOG_LOGS_KIND`). The module-level
  `_adapter` cache in `views.py` is reset between tests via
  `_views._adapter = None`.

## Trade-offs the codebase already made

| Decision | Trade-off |
|---|---|
| Tailwind via CDN in v0.2 | quick to ship; no `npm` for users; offline use is broken — PRD-v0.2 §FR41 plans the standalone-CLI compile |
| In-house `_markdown_to_html` (~60 LOC) | zero markdown deps; misses edge-cases (tables, nested lists) — `markdown-it-py` is a future swap if needed |
| `:memory:` stub DB + skip contenttypes migrations | the viewer reads external files, not Django's ORM, so there's nothing to migrate — keeps `runserver` quiet |
| `ALLOWED_HOSTS = ['127.0.0.1','localhost','*']` | wildcard accepted because `cli.py` warns explicitly when binding non-loopback; the wildcard is convenience for local dev |
| In-memory buffer with on-error drop in `SQLHandler.flush` | logging never blocks the host process; lost-batch on DB outage is documented as a future fallback-handler |
| No migrations in v0.2 | `SchemaError` is raised when reflected columns drift — user is told to delete the DB or use a fresh URL |

## Frozen contracts (v1.0 freeze)

PRD-v0.5 §2.4 enumerates 7 invariants that are **non-negotiable**
through v1.0 and forever:

1. Stdlib-`logging` compatibility (no parallel hierarchy)
2. Zero PyPI runtime deps in the core
3. Idempotent `setup()` via `_ulog_managed`
4. Byte-stable formatter output for `qlnes` / `simple` / `verbose` / `json`
5. Profile cache layout (`~/.cache/ulog/<profile>.sqlite`)
6. Library-friendly `get_logger()` (works without `setup()`)
7. The 4 reserved-keys frozenset semantics across formatters & handlers

Refer to PRD-v0.5 for the full prose. New surfaces ship without
breaking these — the v0.5 forensic archive is layered ON TOP of the
existing schema rather than rewriting it.
