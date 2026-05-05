---
docType: project-overview
project_name: ulog-python
date: 2026-05-05
generator: bmad-document-project (exhaustive scan)
---

# ULog — Project Overview

## What it is

ULog is a thin, drop-in upgrade for Python's stdlib `logging`. It ships
sensible defaults, four built-in formatters, terminal colour via the
vendored [`ucolor`](https://github.com/jojo8356/ucolor-python) submodule
(graceful 8-color fallback when ucolor isn't installed), and
`contextvars`-based field binding for structured logging.

**Core invariant:** ULog never forks the logger hierarchy. Code that
already does `logging.getLogger(__name__)` keeps working unchanged —
including third-party libs (`requests`, `urllib3`, `boto3`, …) whose
records flow through the same handlers ULog installs on the root logger.

```python
import ulog
ulog.setup(format='qlnes', color='auto')
log = ulog.get_logger(__name__)
log.error("boom")   # → "qlnes: error: boom" in red on a TTY
```

## Repository type

**Monolith / single part.** One Python package (`ulog/`) with an embedded
Django web viewer at `ulog/web/`. Everything ships under one
`pyproject.toml` and one PyPI distribution.

## Tech stack

| Category | Technology | Version | Notes |
|---|---|---|---|
| Language | Python | `>=3.10` | matrix: 3.10 / 3.11 / 3.12 / 3.13 |
| Build | setuptools | `>=68.0` | `pyproject.toml` only |
| Type-check | mypy | `>=1.0` | `--strict` enforced |
| Tests | pytest | `>=7.0` | ~70 tests across 5 files |
| Storage (extra) | SQLAlchemy | `>=2.0` | only loaded when `[storage]` extra installed |
| Web (extra) | Django | `>=5.0` | only loaded when `[web]` extra installed |
| Web (extra) | django-lucide | `>=1.3` | SVG icons via `{% lucide %}` template tag |
| CSS | Tailwind | CDN script | v0.2 prototype; standalone-CLI build planned (PRD-v0.2 §3.5) |
| Vendor | ucolor | git submodule | `vendor/ucolor-python/` — truecolor; falls back to 8-color ANSI |

## Public surfaces

ULog ships three surfaces from one package:

1. **Python API** (`import ulog`) — the library proper. Exports
   `setup`, `get_logger`, `bind`, `context`, formatters, storage
   handlers (`SQLHandler`, `JSONLineHandler`, `CSVHandler`),
   `register_formatter`, `default_db_path`, `is_configured`,
   `set_level`. See `api-contracts.md`.
2. **`ulog-web` console-script** — Django HTTP server that opens any
   `.sqlite` / `.jsonl` / `.csv` log file in a browser-based
   inspection UI. Routes documented in `api-contracts.md`.
3. **`ulog/web/docs/*.md`** — five in-app markdown doc pages
   (quickstart, storage, api, troubleshooting, sectors-and-files)
   rendered by a tiny in-house markdown→HTML pass at runtime
   (`ulog/web/viewer/views.py:_markdown_to_html`).

## Architecture (one-liner)

`setup()` builds `logging.Handler` subclasses (one per `kind` in
`handlers=[…]`), tags each with `_ulog_managed=True`, and installs them
on the named-or-root stdlib logger. Formatters and storage handlers
share the same `record → row` shape (reserved-keys frozenset duplicated
across `JsonFormatter`, `CSVHandler`, `SQLHandler`). The Django viewer
reflects/reads back the same SQL schema (or parses JSONL/CSV) through
adapters that produce a uniform `Record` dataclass.

See `architecture.md` for the full breakdown.

## Profiles & cache layout

ULog auto-segregates application logs from test logs:

- `profile='prod'` → `~/.cache/ulog/prod.sqlite`
- `profile='test'` → `~/.cache/ulog/test.sqlite` (auto-selected when
  pytest is in charge: detected via `PYTEST_CURRENT_TEST` env var
  OR `pytest in sys.modules`)
- `profile='auto'` → `prod` or `test` based on the same heuristic
- `profile=None` (the v0.1 default) → no SQL handler, stream-only

`XDG_CACHE_HOME` is honored on Linux/macOS.

## Status & versioning

| Version | Status | Subject |
|---|---|---|
| v0.1.0 | shipped | Core API + 4 formatters + ucolor + contextvars |
| v0.2.0 | shipped | Storage handlers (SQL/JSONL/CSV) + Django inspection UI |
| v0.2.1 | shipped | UI bugfixes — ghost counts, sidebar spacing, theme fade |
| v0.3.0 | draft v1 | pytest plugin + UI section "tests vs logs" |
| v0.4.0 | draft v1 | git-blame author enrichment + sidebar "By author" |
| v0.5.0 | draft v1 | Forensic black box — immutable hash-chain, replay, incidents ledger |

`docs/prds/index.md` is the canonical roadmap. PRD frontmatter convention:
`docType: prd`, `version`, `status`, `parent_prd` (except v0.1).

## Quick links

- [`README.md`](../README.md) — install + quick tour
- [`docs/prds/index.md`](./prds/index.md) — PRD roadmap & filiation
- [`architecture.md`](./architecture.md) — full architecture write-up
- [`source-tree-analysis.md`](./source-tree-analysis.md) — annotated directory map
- [`development-guide.md`](./development-guide.md) — local setup, build, test
- [`api-contracts.md`](./api-contracts.md) — Python API + Django HTTP routes
- [`data-models.md`](./data-models.md) — SQL `logs` table schema
- [`component-inventory.md`](./component-inventory.md) — formatters / handlers / adapters catalog
