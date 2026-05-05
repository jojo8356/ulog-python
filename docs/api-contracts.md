---
docType: api-contracts
project_name: ulog-python
date: 2026-05-05
---

# API Contracts

ULog ships two API surfaces:

1. **Python public API** — `import ulog` (the library proper).
2. **HTTP endpoints** — `ulog-web` Django viewer (read-only).

---

## 1. Python public API

Defined by `ulog/__init__.py:__all__`. Stable through v1.0 (PRD-v0.5
§2.4 freeze contract).

### Setup

```python
ulog.setup(
    *,
    level: "DEBUG"|"INFO"|"WARNING"|"ERROR"|"CRITICAL"|int = "INFO",
    format: str = "qlnes",                              # any registered formatter
    color: "auto"|"always"|"never" = "auto",
    stream: IO[str] | None = None,                      # default sys.stderr
    name: str | None = None,                            # None = root logger
    propagate: bool = False,                            # default False for named, True for root
    handlers: list[str] | None = None,                  # ['stream','sql','json','csv']
    profile: "prod"|"test"|"auto" | None = None,
    sql_url: str | None = None,
    sql_table: str = "logs",
    sql_batch_size: int = 100,
    json_path: str | None = None,
    csv_path: str | None = None,
    **formatter_kwargs: Any,                            # forwarded to stream formatter
) -> logging.Logger
```

**Contract:**
- Idempotent (FR2). Subsequent calls remove `_ulog_managed=True`
  handlers and reinstall.
- Returns the configured `logging.Logger` (root by default, named
  when `name=…`).
- Raises `ValueError` on unknown level, profile, color mode,
  formatter name, or handler kind.
- `handlers=['json']` requires `json_path=`; `handlers=['csv']`
  requires `csv_path=`.
- `profile=…` defaults `handlers=['stream', 'sql']` and
  `sql_url=sqlite:///~/.cache/ulog/<profile>.sqlite`. Explicit
  `sql_url=` wins.

### Logger API (stdlib passthrough)

```python
ulog.get_logger(name: str | None = None) -> logging.Logger
ulog.set_level(level: str|int, name: str|None = None) -> None
ulog.is_configured(name: str | None = None) -> bool
```

`get_logger` is a thin wrapper around `logging.getLogger` —
**works without `setup()`**. Library code can use it freely; if the
host application never calls `setup()`, Python's `logging` defaults
apply.

`is_configured` is true iff the named logger has at least one handler
with `_ulog_managed=True`. User-installed handlers don't count.

### Context binding

```python
ulog.bind(**fields: Any) -> None              # add/update bound fields
ulog.unbind(*keys: str) -> None
ulog.clear() -> None
ulog.context(**fields) -> ContextManager      # block-scoped bind
ulog.get_bound() -> dict[str, Any]            # COPY of current bound dict
```

Backed by a single `contextvars.ContextVar`. Mutation creates a fresh
dict copy each time so concurrent tasks see consistent state.
`get_bound()` returns a copy — mutating the result does NOT affect
bound state (regression-tested).

### Formatters

```python
ulog.QlnesFormatter      # qlnes: error: msg (INFO bare)
ulog.SimpleFormatter     # [INFO] msg
ulog.VerboseFormatter    # ts LEVEL [logger] msg ctx (file:line) + tb
ulog.JsonFormatter       # one JSON object per record
ulog.register_formatter(name: str, cls: type[logging.Formatter]) -> None
```

`register_formatter` raises `TypeError` if `cls` is not a
`logging.Formatter` subclass. Replaces any prior registration at that
name (built-ins included — overrides allowed).

### Storage handlers (v0.2)

```python
ulog.SQLHandler(url: str | None = None, *, table: str = "logs", batch_size: int = 100)
ulog.JSONLineHandler(path: str | Path, *, append: bool = True)
ulog.CSVHandler(path: str | Path, *, dialect: str = "excel")
ulog.SchemaError                          # raised on column drift
```

All three inherit `logging.Handler` (CSV/SQL) or `logging.FileHandler`
(JSONL). They can be attached directly to any stdlib logger:

```python
log = ulog.get_logger()
log.addHandler(ulog.SQLHandler("sqlite:///./logs.sqlite"))
```

…or composed via `setup(handlers=[…])`.

### Constants

```python
ulog.LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
ulog.PROFILES = ("prod", "test")
ulog.LogLevel    # Literal["DEBUG", ..., "CRITICAL"]
ulog.Profile     # Literal["prod", "test", "auto"]
ulog.default_db_path(profile: str = "prod") -> Path
ulog.__version__
```

`default_db_path` raises `ValueError` for unknown profiles.

---

## 2. HTTP API — `ulog-web` Django viewer

URL prefix: root (`/`). Routes registered in
[`ulog/web/urls.py`](../ulog/web/urls.py).

### `GET /`  → list view (HTML)

Main filter + record list. Renders `ulog/templates/ulog/list.html`.

**Query parameters** (all optional, all repeatable except `q`/`page`/`from`/`to`):

| Param | Repeatable | Effect |
|---|---|---|
| `level` | yes | filter by log level (`DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL`) |
| `logger` | yes | filter by logger-name prefix (sectors). E.g. `?logger=myapp.audio` matches all `myapp.audio.*` |
| `file` | yes | filter by source filename (exact match) |
| `bound` | yes | filter by bound contextvar key=value: `?bound=request_id=abc-123` |
| `q` | no | full-text search in `msg` (case-insensitive `LIKE %q%` for SQLite) |
| `from` | no | ISO-8601 lower bound on `ts` |
| `to` | no | ISO-8601 upper bound on `ts` |
| `page` | no | 1-based page number; `page_size` is fixed at 100 |

**Returns:** rendered HTML, status `200`. Includes the per-axis
ghost counts (PRD-v0.2.1 contract — see `architecture.md`).

### `GET /r/<int:record_id>/` → detail view (HTML)

Single-record detail page. Renders `ulog/templates/ulog/detail.html`.

**Returns:** `200` with the full record (level, logger, msg, file,
line, ts, JSON-pretty-printed context, traceback if `exc_info`).
`404` if `record_id` not found.

### `GET /api/records/` → JSON

Same query parameters as `GET /`. JS-driven UI consumer.

**Response shape:**

```json
{
  "records": [
    {
      "id": 1, "ts": "...", "level": "INFO", "logger": "...",
      "msg": "...", "file": "...", "line": 12,
      "context": {...}, "exc": null
    }
  ],
  "total": 5,
  "page": 1,
  "level_counts": {"INFO": 3, "WARNING": 1, "ERROR": 1},
  "file_counts": {"foo.py": 4, "bar.py": 1},
  "sector_counts": {"myapp": 5, "myapp.audio": 4, ...}
}
```

`level_counts` / `sector_counts` / `file_counts` are
**ghost counts** — each computed against all-filters-EXCEPT-this-axis
(see `architecture.md`).

### `GET /docs/` → docs index (HTML)

Lists the 5 in-app doc pages. Renders
`ulog/templates/ulog/docs_index.html`.

### `GET /docs/<slug:page>/` → doc page (HTML)

Renders `ulog/web/docs/<page>.md` through the in-house
`_markdown_to_html()`. Valid slugs:

- `quickstart`, `storage`, `api`, `troubleshooting`, `sectors-and-files`

`404` for any other slug or if the markdown file is missing.

### `GET /favicon.ico` → 204

Empty response to silence browser auto-requests.

---

## CLI — `ulog-web`

```
ulog-web <path>
         [--port PORT]      # default: random free port
         [--host HOST]      # default: 127.0.0.1; warns on stderr if non-loopback
         [--no-open]        # don't auto-open a browser tab
```

- `<path>` ends in `.sqlite`/`.sqlite3`/`.db`, `.jsonl`/`.ndjson`,
  or `.csv` (storage kind sniffed from extension).
- Configures Django via env vars (`DJANGO_SETTINGS_MODULE`,
  `ULOG_LOGS_PATH`, `ULOG_LOGS_KIND`) before importing django.
- Bypasses `manage.py runserver` and runs WSGI directly via
  `django.core.servers.basehttp.run` (skips banner + migration check).

Exit codes:
- `0` — clean shutdown
- `2` — file not found or unrecognized extension
- `127` — `ulog-web` not on PATH

---

## Versioning & stability

The Python API is **frozen through v1.0** for the items listed in
PRD-v0.5 §2.4. New v0.X versions add surfaces; they don't break
existing ones. The HTTP API is younger (v0.2) — the JSON shape may
evolve in v0.3+ but the URL routes are stable.
