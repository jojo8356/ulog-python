---
docType: component-inventory
project_name: ulog-python
date: 2026-05-05
note: "ULog is a library, not a UI app — 'components' here means the building blocks: formatters, handlers, storage adapters, Django views/templates."
---

# Component Inventory

## Formatters

`ulog/formatters.py`. Four built-ins + a registry.

| Formatter | Class | Output shape | Notes |
|---|---|---|---|
| qlnes | `QlnesFormatter` | `<prefix>: <level>: <msg>` for non-INFO; bare `<msg>` for INFO/DEBUG | Default. Bare INFO is the qlnes contract — keeps progress markers clean. `prefix='qlnes'` overridable via `setup(format='qlnes', prefix='myapp')`. |
| simple | `SimpleFormatter` | `[<LEVEL>] <msg>` | Universal — all levels prefixed (incl. INFO). |
| verbose | `VerboseFormatter` | `<ts> <LEVEL> [<logger>] <msg> <bound> (file:line)\n<traceback>` | ISO-8601 UTC timestamp, bound context appended as `key='val'` pairs. Includes traceback when `record.exc_info`. |
| json | `JsonFormatter` | one JSON object per record | Stable schema (see `data-models.md`). UTF-8, compact, jq-friendly. |

`_ColorAwareFormatter` is the internal base for the first three (it
holds the `color_on` decision and `_decorate(level, prefix)` helper).
`JsonFormatter` ignores colour by design.

`register_formatter(name, cls)` adds/replaces a formatter at any name.
Built-ins can be overridden.

## Storage handlers

`ulog/handlers/`. Each is a `logging.Handler` (or `FileHandler`)
subclass — composable with stdlib + user-installed handlers.

| Handler | File | Output | Behavior |
|---|---|---|---|
| `SQLHandler` | `handlers/sql.py` | SQLAlchemy → any SQL backend (sqlite by default) | Single `logs` table with 4 indexes. Lazy schema create. In-memory buffer flushed in batches (default 100), on `flush()`, on `atexit`. `SchemaError` on column drift (no migrations in v0.2). |
| `JSONLineHandler` | `handlers/json_line.py` | one JSON object per line, appended | Inherits `logging.FileHandler`. Uses `JsonFormatter` regardless of `setup(format=)`. UTF-8. |
| `CSVHandler` | `handlers/csv_file.py` | RFC 4180 CSV rows | Lazy header write on first `emit()`. Columns: `ts, level, logger, msg, file, line, context_json, exc_json`. `dialect="excel"` default. |

All three reuse the same JSON shape for nested data (`context`,
`exc`). Reserved-keys frozenset is duplicated across them — see
`data-models.md` for the canonical list.

## Storage adapters (Django viewer side)

`ulog/web/viewer/adapters.py`. Read-only counterpart to the storage
handlers. One uniform `Adapter` interface, three impls.

| Adapter | File extensions | Filter strategy |
|---|---|---|
| `SQLiteAdapter` | `.sqlite`, `.sqlite3`, `.db` | filter pushed down as SQL `WHERE`. Uses `MetaData.reflect` to support custom-extended schemas. JSON path filtering via `func.json_extract`. |
| `JSONLAdapter` | `.jsonl`, `.ndjson` | loads whole file into memory; `_filter_and_paginate()` runs a Python predicate per record. Malformed lines silently skipped. |
| `CSVAdapter` | `.csv` | same shape as JSONL — full load, in-memory filter. |

Common contract: `query(filters, page, page_size) -> QueryResult`,
`get(record_id) -> Record | None`. `detect_kind(path)` maps extension
→ adapter type.

### Dataclasses

| Class | Fields |
|---|---|
| `Record` | `id, ts, level, logger, msg, file, line, context, exc` — uniform shape |
| `Filters` | `levels, loggers, files, search, bound, ts_from, ts_to` — query input |
| `QueryResult` | `records, total, page, page_size, sector_counts, file_counts, level_counts, bound_keys` — query output |

### Helpers

- `_payload_to_record` — JSONL/CSV row → `Record`
- `_filter_and_paginate` — shared in-memory filter + ghost-count loop
- `_build_sector_counts` — rolls `logger_counts` up by `.`-split prefixes
  (e.g. `myapp.audio.renderer:5` ⇒ `myapp:5, myapp.audio:5, myapp.audio.renderer:5`)

## Django views

`ulog/web/viewer/views.py`. All read-only.

| View | URL | Renders |
|---|---|---|
| `list_view` | `/` | `templates/ulog/list.html` — sidebar + records table |
| `detail_view` | `/r/<id>/` | `templates/ulog/detail.html` — single record detail |
| `api_records` | `/api/records/` | JSON (filter + ghost counts) |
| `docs_index` | `/docs/` | `templates/ulog/docs_index.html` — pages list |
| `docs_page` | `/docs/<slug>/` | `templates/ulog/docs_page.html` — markdown rendered via `_markdown_to_html()` |

Module-level `_adapter` singleton — built once on first request,
reused. Reset to `None` between tests via `_views._adapter = None`
when fixtures change.

`_markdown_to_html` is a ~60-LOC in-house renderer (no external
markdown lib). Supports `#`/`##`/`###` headings, fenced code blocks
with language class, lists, paragraphs, inline `code`/`**bold**`/
`[link](url)`, with Tailwind classes baked in.

## Templates

`ulog/web/templates/ulog/`. Tailwind via CDN (`<script
src="https://cdn.tailwindcss.com">`). lucide icons via the
`{% lucide "name" %}` template tag (project-wide builtin loaded in
`settings.TEMPLATES.OPTIONS.builtins`).

| Template | LOC | Role |
|---|---|---|
| `base.html` | 99 | header, nav, dark-mode bootstrap (set BEFORE Tailwind paints to avoid FOUC), 500ms theme-fade transition, sun/moon crossfade |
| `list.html` | 266 | filter sidebar + records table + pagination |
| `detail.html` | 66 | single record (JSON pretty-print, traceback, context) |
| `docs_index.html` | 31 | docs landing |
| `docs_page.html` | 25 | rendered markdown wrapper |

## In-app doc pages

`ulog/web/docs/`. Five markdown files served via `/docs/<slug>/`.

| Slug | Subject |
|---|---|
| `quickstart` | First-time use |
| `storage` | SQL / JSON / CSV storage handlers |
| `api` | Python API reference |
| `troubleshooting` | Common errors |
| `sectors-and-files` | What sectors are (rolled-up logger names) and how files differ |

These are the **runtime** docs (consumed by the inspection UI). The
**developer-side** docs (architecture, PRDs, this file) live under
`docs/` at the repo root.

## CLI utilities

| Tool | Source | Purpose |
|---|---|---|
| `ulog-web` | `ulog/web/cli.py` | Console-script — opens the Django UI on a log file |
| `run.sh` | `run.sh` (bash) | Local-dev launcher — setup / prod / test / dev / demo / clean |

`run.sh` resolves a python interpreter from `.venv` (own or parent
project's), sniffs missing deps in ONE python invocation (~34ms), and
forwards extra args to the underlying tool.
