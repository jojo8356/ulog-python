---
docType: source-tree
project_name: ulog-python
date: 2026-05-05
---

# Source Tree — annotated

```
ulog-python/
├── pyproject.toml          # build + extras + console_scripts; mypy --strict
├── Makefile                # test / mypy / check / build / clean
├── run.sh                  # local launcher (setup/prod/test/dev/demo/clean)
├── README.md               # install + quick tour + submodule discipline
├── LICENSE                 # MIT
├── uv.lock                 # uv-managed lockfile (when uv is in use)
│
├── ulog/                   # the package proper — zero PyPI runtime deps
│   ├── __init__.py         # public API surface (`__all__`); thin re-exports
│   ├── setup.py            # `setup()`, `get_logger()`, `set_level()`,
│   │                       # `is_configured()`, `default_db_path()`,
│   │                       # `_build_handler()` (lazy-imports SQL/JSON/CSV
│   │                       # handler classes); profile auto-detection
│   ├── formatters.py       # 4 built-ins: qlnes / simple / verbose / json
│   │                       # + `register_formatter()` + `_resolve_formatter()`
│   │                       # + `_RESERVED` frozenset (mirrors handlers/sql.py
│   │                       # + handlers/csv_file.py)
│   ├── context.py          # `bind / unbind / clear / context / get_bound`
│   │                       # backed by a single `contextvars.ContextVar`
│   ├── _color.py           # `resolve_color()` (TTY/NO_COLOR/--color);
│   │                       # `color_level()` — ucolor truecolor with
│   │                       # 8-color ANSI fallback
│   │
│   ├── handlers/           # v0.2 storage handlers (FR21-FR31)
│   │   ├── __init__.py     # re-exports SQL/JSON/CSV + SchemaError
│   │   ├── sql.py          # SQLHandler — SQLAlchemy 2.x; lazy-create schema;
│   │   │                   # batch-flush; `atexit` safe-flush; SchemaError on drift
│   │   ├── json_line.py    # JSONLineHandler (FileHandler subclass)
│   │   └── csv_file.py     # CSVHandler — RFC 4180; lazy header write
│   │
│   └── web/                # v0.2 Django inspection UI — only loaded
│       │                   # when the [web] extra is installed
│       ├── __init__.py     # docstring (no code)
│       ├── cli.py          # `ulog-web` console-script entry point;
│       │                   # bypasses runserver, drives WSGI directly
│       ├── settings.py     # minimal Django settings, `:memory:` stub DB,
│       │                   # `MIGRATION_MODULES = {"contenttypes": None}`
│       ├── urls.py         # 6 routes (list / detail / api / docs / favicon)
│       ├── docs/           # 5 in-app markdown doc pages rendered at runtime
│       │   ├── quickstart.md
│       │   ├── storage.md
│       │   ├── api.md
│       │   ├── troubleshooting.md
│       │   └── sectors-and-files.md
│       ├── templates/ulog/ # Django templates (Tailwind via CDN, lucide icons)
│       │   ├── base.html       # header, dark-mode bootstrap, theme fade
│       │   ├── list.html       # filter sidebar + records table
│       │   ├── detail.html     # single-record JSON pretty-print
│       │   ├── docs_index.html
│       │   └── docs_page.html
│       ├── static/         # static-files dir (Tailwind CDN means empty in v0.2)
│       └── viewer/         # the Django app
│           ├── __init__.py
│           ├── apps.py     # AppConfig (label="ulog_viewer")
│           ├── views.py    # list_view / detail_view / api_records / docs_*
│           │               # + `_markdown_to_html()` (in-house, ~60 LOC)
│           └── adapters.py # storage-agnostic `Adapter` interface;
│                           # SQLiteAdapter / JSONLAdapter / CSVAdapter;
│                           # `Record`, `Filters`, `QueryResult` dataclasses;
│                           # ghost-count logic (PRD-v0.2.1)
│
├── tests/                  # pytest, ~70 tests
│   ├── __init__.py         # empty
│   ├── test_setup.py       # setup / idempotency / profiles / pytest auto-detect
│   ├── test_formatters.py  # qlnes / simple / verbose / json + registration
│   ├── test_context.py     # bind / unbind / context / contextvar discipline
│   ├── test_handlers.py    # SQL / JSONL / CSV + multi-handler composition
│   └── test_web.py         # adapters + Django views + ghost-count regression
│
├── docs/                   # documentation (this directory)
│   ├── index.md            # master index (this DP run)
│   ├── project-overview.md # this DP run
│   ├── architecture.md
│   ├── source-tree-analysis.md  # ← you are here
│   ├── development-guide.md
│   ├── data-models.md
│   ├── api-contracts.md
│   ├── component-inventory.md
│   ├── project-scan-report.json # DP state file
│   └── prds/               # PRD roadmap (predates the DP run)
│       ├── index.md
│       ├── PRD-v0.1-core.md
│       ├── PRD-v0.2-storage-and-ui.md
│       ├── PRD-v0.2.1-ui-bugfixes.md
│       ├── PRD-v0.3-test-integration.md
│       ├── PRD-v0.4-commit-author-filter.md
│       ├── PRD-v0.5-forensic-archive.md
│       └── validation/     # PRD validation reports
│
├── vendor/
│   └── ucolor-python/      # GIT SUBMODULE — clone with --recursive
│                           # provides 24-bit truecolor when available
│
└── _bmad/                  # BMad Method framework files (installed)
    ├── _config/            # bmad-help.csv, manifest, skill-manifest
    ├── bmm/config.yaml     # planning_artifacts, project_knowledge paths
    └── ...                 # (skill machinery — not edited by hand)

_bmad-output/               # BMad workflow outputs (per BMM config)
├── brainstorming/          # 2026-05-04 session that emerged PRD-v0.5
├── planning-artifacts/     # (populated by future PRD/architecture skills)
├── implementation-artifacts/
└── project-context.md      # GPC scaffold (technology stack section)
```

## Critical folders explained

- **`ulog/`** — pure Python library, **zero runtime PyPI deps**. Every
  optional-dep import (sqlalchemy, django, ucolor) is performed
  *inside* the function/handler that needs it. Adding a top-level
  third-party import here would break `import ulog` for users without
  the matching extra.
- **`ulog/web/`** — only loaded when the `[web]` extra is installed.
  The Django settings deliberately use a `:memory:` stub DB and silence
  contenttypes migrations because the viewer reads external log files
  via adapters, not Django's ORM.
- **`vendor/ucolor-python/`** — git submodule. The codebase functions
  without it (8-color fallback in `_color.py`), but truecolor styling
  requires `pip install -e ./vendor/ucolor-python` after cloning
  `--recursive`.
- **`docs/prds/`** — versioned PRDs, ground-truth roadmap. Each PRD
  has frontmatter (`docType: prd`, `version`, `status`, `parent_prd`).
  `docs/prds/index.md` is the canonical entry point.
- **`_bmad-output/brainstorming/`** — captures of brainstorming
  sessions (one exists for the v0.5 forensic-archive PRD).
- **`_bmad/`** — BMad Method installation. Skills live under
  `.claude/skills/bmad-*` and are invoked via `/bmad-*` commands.

## Entry points

| Entry | Definition | What it does |
|---|---|---|
| `import ulog` | `ulog/__init__.py` | Library API |
| `ulog-web` (CLI) | `ulog.web.cli:main` (via `[project.scripts]` in `pyproject.toml`) | Spins up the Django inspection UI |
| `./run.sh` | `run.sh` (bash) | Local-dev launcher: setup / prod / test / dev / demo / clean |
| `make test` / `make mypy` / `make check` | `Makefile` | CI-ish targets |
