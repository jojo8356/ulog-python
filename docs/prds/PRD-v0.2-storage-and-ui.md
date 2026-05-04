---
docType: prd
project_name: ulog-python
version: 0.2.0
date: 2026-05-04
author: jojo8356
status: draft v1
parent_prd: PRD-v0.1-core.md
---

# ULog v0.2 — Storage Backends + Django Inspection UI

> ULog v0.1 emits log records to a stream (stdout, stderr, file). v0.2
> adds **persistent storage handlers** (SQL via SQLAlchemy, JSON
> Lines, CSV) and a **Django + Tailwind web UI** that browses,
> filters, and explains the stored logs. The UI documents itself —
> a built-in tutorial and per-field tooltips remove the "what does
> this column mean?" gap that every log viewer has.

---

## 0. The 30-second pitch

The v0.1 stdout-pipeline solved the "render logs for humans + CI"
problem. It didn't solve the "I shipped my CLI tool, a user
reproduces a bug, how do I get the relevant logs to me?"

v0.2 ships:
- **Three storage handlers** (`SQLHandler`, `JSONLineHandler`,
  `CSVHandler`) plug into stdlib `logging` exactly like the existing
  `StreamHandler` — drop them in via `setup(handlers=[...])`.
- **A Django web app** (`ulog_web/`) that reads from any of the three
  storage shapes, renders a Tailwind-styled UI for filtering by level
  / file / logger / sector / time-range / bound-context-fields, and
  ships **inline documentation** — every filter has a tooltip, every
  column has a "what does this mean?" link, and a tutorial overlay
  walks first-time users through the four common workflows.

The result: a shipped CLI tool can log to a SQLite file (zero infra),
the user reproduces a bug, sends you the `.sqlite`, and you click
through the UI to find what went wrong. No grep, no regex, no shell.

---

## 1. Vision

### 1.1 Why this exists

Existing log viewers fall into two camps:

- **Hosted SaaS** (Datadog, Splunk, Sentry, Grafana Loki) — overkill
  for a single-user CLI tool, expensive, requires shipping logs to a
  cloud service the user doesn't trust.
- **Local greppers** (`grep`, `lnav`, `ag`, `glogg`) — work on raw
  text files; lose the structure that ULog's JSON formatter provides;
  no UI for filtering by `bound_field`.

ULog v0.2 carves a middle path: persistent local storage (SQLite by
default — single file, no daemon) + a Django UI that runs locally
(`ulog-web /path/to/logs.sqlite` opens a browser tab). The UI is
**documented as it's used** — first-time visitors see a 30-second
overlay; every column header has a tooltip; the filter form has
inline examples.

### 1.2 What v0.2 isn't

- A multi-user log aggregator. No auth, no roles, no team views.
  Single-user local tool.
- A streaming UI. Logs are read at page-load; the UI doesn't tail
  in real time. v0.3 may add a tail mode.
- A log analyzer. No anomaly detection, no statistical alerts. Just
  filtering and viewing.
- A replacement for production observability (Sentry, Datadog,
  OpenTelemetry). Pair with those for production; ULog v0.2 is for
  local CLI tool diagnostics.

### 1.3 Target user (carried + new)

- **Marco** (carried) — runs `qlnes audio rom.nes` from the shell.
  v0.2: optionally adds `--log-file=/tmp/qlnes.sqlite` to persist
  logs. When he hits a bug, he runs `ulog-web /tmp/qlnes.sqlite`,
  the browser opens, he filters by `level=ERROR` and finds the
  divergence event.
- **Lin** (carried) — pipeline integrator. v0.2: configures
  `ulog.setup(handlers=['json'], json_path='./logs.jsonl')`. The
  pipeline post-render uploads `logs.jsonl` to a CI artifact bucket.
  When triage time comes, anyone can `ulog-web ./logs.jsonl` to
  inspect.
- **Sara** (carried) — library developer. Doesn't add storage
  herself; the host application's `setup(handlers=[...])` decides.
  Sara just keeps using `ulog.get_logger(__name__).info(...)`.
- **Erwan** (NEW) — packaged-app user. He installed qlnes via
  `pipx`, ran it, hit a bug. He opens
  `ulog-web ~/.config/qlnes/last-run.sqlite` and the UI's tutorial
  overlay walks him through finding the error in 30 seconds. He
  copy-pastes the relevant log records into a GitHub issue.

---

## 2. Scope (v0.2)

### 2.1 In scope

#### 2.1.1 Storage handlers

- **SQLHandler** — Persists log records to a SQLite (default) or any
  SQLAlchemy-supported DB (Postgres, MySQL, MariaDB). Schema is fixed
  for v0.2; ALTER TABLE migrations are out of scope (use a fresh DB
  if you need a new column).
- **JSONLineHandler** — Appends one JSON object per record to a file.
  Schema matches the `JsonFormatter` from v0.1 byte-for-byte. Cheap,
  zero deps, easy to inspect with `jq`.
- **CSVHandler** — Appends rows to a CSV file. Trades structured
  fields for spreadsheet-importable simplicity. Bound context fields
  serialized as JSON in the `context` column.

All three are stdlib `logging.Handler` subclasses → composable with
`setup(handlers=['stream', 'sql'])` to log to terminal AND DB
simultaneously.

#### 2.1.2 Django + Tailwind UI (`ulog_web/`)

- Single-page list of records with server-side pagination (100/page).
- Filters in a left sidebar:
  - **Level**: checkboxes (DEBUG, INFO, WARNING, ERROR, CRITICAL).
  - **Logger / sector**: hierarchical tree picker
    (`qlnes` → `qlnes.audio` → `qlnes.audio.in_process`).
  - **File**: dropdown of distinct `record.filename` values; supports
    multi-select.
  - **Time range**: from–to datetime pickers + quick presets ("last
    1h", "last 24h", "since startup").
  - **Bound context fields**: free-form key=value text input; the UI
    suggests known keys (auto-detected from the loaded data).
  - **Search**: full-text on `msg`.
- Right panel: detail view for the selected record (JSON pretty-print,
  exception traceback rendered, link "view session" — all records in
  the same time-window/PID).
- **Tutorial overlay**: first-time visitor sees a 30-second walkthrough
  ("filter by level → click a record → see detail → use sectors to
  drill in"). Dismissible; localStorage remembers.
- **Per-column tooltips**: hover a column header → tooltip explains
  what it is + an example.
- **Filter examples**: the bound-fields input has a 3-row examples
  panel ("`rom_sha=abc123`", "`engine=famitracker`", "`mode=oracle`").

#### 2.1.3 Comprehensive built-in doc

- `/docs` route in the Django app — full markdown-rendered manual.
- `/docs/quickstart` — 5-step quickstart (install, setup, log,
  open UI, filter).
- `/docs/storage` — schema reference for the three handlers.
- `/docs/api` — full ULog v0.1 + v0.2 Python API.
- `/docs/troubleshooting` — common gotchas (DB locked, JSON malformed,
  no records loading).
- All linked from a footer in every UI page.

#### 2.1.4 CLI launcher

- `ulog-web <path>` — auto-detects storage type (`.sqlite` /
  `.jsonl` / `.csv`), spins up the Django dev server on a random
  port, opens the browser. No daemon, no Docker.
- Flags: `--port`, `--no-open` (don't open browser), `--read-only`
  (default is read-only anyway).

### 2.2 Explicit non-goals (deferred to v0.3+)

- **Real-time tail**. v0.2 is page-load-snapshot. v0.3 may add a
  WebSocket tail.
- **Multi-source merge**. v0.2 reads ONE file at a time. Merging
  several `.sqlite` files into a single view is v0.3.
- **Auth/roles**. v0.2 binds to localhost only. Multi-user / team
  view is v0.4.
- **Export filters as queries**. The UI's filter state isn't
  re-applicable as a CLI command; v0.3 will add `--export-query`.
- **Custom dashboards**. No widgets, no graphs. Just lists +
  detail. Graphs in v1.0.
- **Alert rules**. Use Sentry / Datadog. ULog stays a local viewer.
- **Schema migrations**. v0.2 ships ONE schema; if it changes, you
  start a fresh DB.

---

## 3. Functional Requirements

### 3.1 SQL storage

| FR | Description |
|---|---|
| FR21 | `SQLHandler(url, table='logs', batch_size=100)` accepts any SQLAlchemy URL: `'sqlite:///path/to/logs.sqlite'` (default), `'postgresql://...'`, etc. Default URL is `sqlite:///<cwd>/ulog.sqlite`. |
| FR22 | Schema (single table, indexed): `id INTEGER PK, ts DATETIME INDEX, level VARCHAR(10) INDEX, logger VARCHAR(255) INDEX, msg TEXT, file VARCHAR(255) INDEX, line INTEGER, exc JSON NULL, context JSON NULL`. Bound context fields stored as a JSON blob; the UI extracts known keys at query time. |
| FR23 | Records flushed every `batch_size` writes OR on `handler.flush()` OR at process exit (via `atexit`). Default `batch_size=100` is the sweet spot between latency and throughput on local SQLite. |
| FR24 | Schema is created lazily on first `emit()` if absent; existing schemas are validated by checking the columns; a mismatch raises `ulog.SchemaError` with a hint to delete the file or use a fresh URL. |
| FR25 | Configurable via `setup(handlers=['sql'], sql_url='sqlite:///./logs.sqlite')`. Multiple handlers can co-exist: `setup(handlers=['stream', 'sql'])`. |

### 3.2 JSON Line storage

| FR | Description |
|---|---|
| FR26 | `JSONLineHandler(path, append=True)` writes one JSON object per record using the same schema as the v0.1 `JsonFormatter`. |
| FR27 | File rotation NOT included in v0.2; users wanting it pair with stdlib `logging.handlers.TimedRotatingFileHandler` and write a wrapping handler. |
| FR28 | Configurable via `setup(handlers=['json'], json_path='./logs.jsonl')`. |

### 3.3 CSV storage

| FR | Description |
|---|---|
| FR29 | `CSVHandler(path, dialect='excel')` writes columns: `ts, level, logger, msg, file, line, context_json, exc_json`. Bound context and exception serialized as JSON-stringified columns. |
| FR30 | First-write installs the header row if file is empty; subsequent writes append. |
| FR31 | Configurable via `setup(handlers=['csv'], csv_path='./logs.csv')`. |

### 3.4 Django web app (`ulog_web/`)

| FR | Description |
|---|---|
| FR32 | Single Django project rooted at `ulog/web/` (importable as `ulog.web`). One app: `ulog_web.viewer`. |
| FR33 | `ulog-web <path>` console-script (declared in `pyproject.toml [project.scripts]`) auto-detects file extension: `.sqlite`/`.db` → SQLAlchemy adapter, `.jsonl`/`.ndjson` → JSON adapter, `.csv` → CSV adapter. |
| FR34 | URL routes: `/` (filtered list), `/r/<id>` (record detail), `/docs/...` (built-in manual), `/api/records/?...` (JSON endpoint for the JS filter UI). |
| FR35 | Filter UI sidebar (left, sticky) — Level checkboxes, logger/sector tree, file dropdown, time-range, bound-fields input, full-text search. State persisted in URL query string; back/forward buttons work. |
| FR36 | List view (right, scrollable) — paginated 100/page, columns: `ts (relative + abs)`, `level (colored badge)`, `logger`, `file:line`, `msg (truncated 100 chars + tooltip on full text)`. |
| FR37 | Record detail (right panel slide-in on click) — JSON pretty-print, exception traceback if present, "Find similar" link (records with same `logger` + `level`), "Session" link (records within ±5 min of this one). |
| FR38 | Tutorial overlay — shown on first visit (no `localStorage.ulogTutorialDismissed`). 4 steps: filter, click, detail, sectors. Skip + Got-it buttons. |
| FR39 | Per-column tooltips — hover a column header reveals `<title>`-style tooltip (Tailwind hover state, no extra JS lib needed). |
| FR40 | `/docs` — markdown rendered in-app. v0.2 ships 5 pages (quickstart, storage, api, troubleshooting, sectors-and-files-explained). Footer link on every page. |

### 3.5 Tailwind styling

| FR | Description |
|---|---|
| FR41 | TailwindCSS via the standalone CLI binary (no `npm` required for end users). Compiled CSS shipped under `ulog/web/static/ulog/tailwind.css`. Re-build via `make web-tailwind` for contributors. |
| FR42 | Light + dark mode via `prefers-color-scheme`. Toggle button in header overrides + persists to localStorage. |
| FR43 | Mobile-responsive (≥ 320px width). Sidebar collapses into a drawer on narrow screens. |

### 3.6 Sectors

A "sector" is a hierarchical logger-name prefix that ULog auto-detects
from the loaded data. Example: a qlnes session has logger names like
`qlnes.audio.renderer`, `qlnes.audio.engine`, `qlnes.cli`. The UI
groups these into a tree:

```
qlnes (147 records)
├── audio (89)
│   ├── renderer (56)
│   ├── engine (24)
│   └── in_process (9)
├── cli (43)
└── io.errors (15)
```

| FR | Description |
|---|---|
| FR44 | Sector tree built from logger-name `.`-split prefixes. Each node shows record count for the current filter set; counts update as filters apply. |
| FR45 | Clicking a node restricts the view to that prefix (e.g. clicking `audio.renderer` filters `record.name LIKE 'qlnes.audio.renderer%'`). |
| FR46 | Multi-select via Ctrl-click — combine sectors with OR (e.g. show `audio.renderer` OR `cli`). |

### 3.7 File-based filtering

| FR | Description |
|---|---|
| FR47 | "Files" filter shows distinct `record.filename` values for the loaded dataset, with record counts. |
| FR48 | Click a file → restrict view to records originating from that source file. |
| FR49 | Multi-select. |
| FR50 | A "by directory" toggle re-groups files by their parent directory (`qlnes/audio/*.py` collapses into one entry showing the rollup count). |

---

## 4. Non-Functional Requirements

| NFR | Budget |
|---|---|
| NFR-PERF-10 | SQL handler INSERT throughput ≥ 5K records/sec on default SQLite (single core, batch=100). |
| NFR-PERF-11 | Django UI page load ≤ 500 ms for 100K-record DB filtered to one page (default level=ERROR or no filter). |
| NFR-PERF-12 | Filter sidebar update ≤ 200 ms after toggle (server-side; SPA-style is v0.3). |
| NFR-DEP-10 | Optional installs only: `pip install ulog[storage]` brings `sqlalchemy>=2.0`. `pip install ulog[web]` brings `django>=5.0` + the Tailwind CLI bundled. Core ULog stays zero-runtime-dep. |
| NFR-COMPAT-10 | SQL: SQLite (default), Postgres 13+, MySQL 8+. JSON: any UTF-8 file. CSV: RFC 4180. |
| NFR-DOC-10 | The `/docs` content is also published as markdown in `docs/` for offline reading; the Django app is just a renderer. |
| NFR-A11Y-10 | UI passes WCAG 2.1 AA (color contrast, keyboard nav, screen-reader labels on filter inputs). |
| NFR-SEC-10 | `ulog-web` binds to `127.0.0.1` only by default. `--host 0.0.0.0` requires explicit opt-in + a printed warning. SQL queries use SQLAlchemy core with parameterized statements (no string interpolation). |
| NFR-PORT-10 | `ulog-web` works on Linux + macOS + Windows. |
| NFR-REL-10 | Any storage handler must survive disk-full / file-locked errors without crashing the host process — best-effort, log to stderr fallback. |

---

## 5. API surface (sketch)

### 5.1 Storage configuration

```python
import ulog

# Stream + SQLite + JSON (multi-handler):
ulog.setup(
    format='qlnes',
    handlers=['stream', 'sql', 'json'],
    sql_url='sqlite:///./qlnes.sqlite',
    json_path='./qlnes.jsonl',
)

# CSV only:
ulog.setup(handlers=['csv'], csv_path='./qlnes.csv')

# Postgres production setup:
ulog.setup(
    handlers=['sql'],
    sql_url='postgresql://localhost/qlnes_logs',
    sql_batch_size=500,  # higher batch for remote DB
)

# Library use unchanged:
log = ulog.get_logger(__name__)
log.info("rendered", extra={'rom_sha': 'abc'})
```

### 5.2 CLI viewer

```bash
# Auto-detect file type, open browser:
ulog-web ./qlnes.sqlite

# Specific port, don't open browser:
ulog-web --port 8080 --no-open ./qlnes.sqlite

# JSON Line file:
ulog-web ./qlnes.jsonl

# CSV:
ulog-web ./qlnes.csv
```

### 5.3 Django integration (advanced)

For users who already run a Django project and want to embed the
viewer:

```python
# settings.py
INSTALLED_APPS = [..., 'ulog.web.viewer']

# urls.py
urlpatterns = [
    ..., path('logs/', include('ulog.web.urls')),
]
```

---

## 6. UI mockup (text)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ULog Viewer  ./qlnes.sqlite  ☼/☽           [docs] [help] [⌘k search]    │
├──────────────────────────────────────────────────────────────────────────┤
│ FILTERS                  │ TS         LEVEL    LOGGER         FILE:LINE  │
│ ──────                   │ 13:35:21   INFO     qlnes.cli      cli.py:280 │
│ □ DEBUG    (12)          │ 13:35:21   INFO     qlnes.audio.r  rend.py:80 │
│ □ INFO     (89)          │ 13:35:24   WARN     qlnes.audio.e  eng.py:165 │
│ ☑ WARNING  (4)           │ 13:35:25   ERROR    qlnes.io.err   err.py:91  │
│ ☑ ERROR    (1)           │ 13:35:26   ERROR    qlnes.audio.r  rend.py:155│
│ □ CRITICAL (0)           │                                               │
│                          │                                               │
│ SECTORS                  │ ▼ Selected: 13:35:25 ERROR                    │
│ ▼ qlnes (107)            │ ────────────────────────────────────────────  │
│   ▼ audio (89)           │ logger:  qlnes.io.errors                      │
│     • renderer (56)      │ msg:     ROM not found: /tmp/foo.nes          │
│     • engine (24)        │ file:    qlnes/io/errors.py:91                │
│     • in_process (9)     │ context: {"rom_path":"/tmp/foo.nes",          │
│   • cli (43)             │           "cwd":"/home/…"}                    │
│   • io.errors (15)       │ exc:     <none>                               │
│                          │ [find similar] [session ±5min] [open in code] │
│ FILES                    │                                               │
│ • cli.py (43)            │                                               │
│ • renderer.py (56)       │                                               │
│ • errors.py (15)         │                                               │
│ • [+12 more...]          │                                               │
│                          │                                               │
│ TIME RANGE               │                                               │
│ [last 1h ▾]  ⌚ ⌚         │                                               │
│                          │                                               │
│ BOUND FIELDS             │                                               │
│ rom_sha=abc123 ╳         │                                               │
│ engine=                  │                                               │
│                          │                                               │
│ Examples ▶               │                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Built-in doc structure

`/docs` is a single Django view rendering markdown files from
`ulog/web/docs/`. Pages:

1. **`/docs/quickstart`** — 5 steps:
   1. `pip install ulog[web]`
   2. In your code: `ulog.setup(handlers=['sql'], sql_url='sqlite:///./logs.sqlite')`
   3. Run your code; logs accumulate in the file.
   4. `ulog-web ./logs.sqlite`
   5. Browser opens; click "ERROR" filter to find issues.

2. **`/docs/storage`** — schema for each handler:
   - SQL: full SQL `CREATE TABLE`, index list, example query.
   - JSON: schema sample with all fields, jq one-liners.
   - CSV: column list, dialect notes, gotcha re commas in messages.

3. **`/docs/api`** — full API ref for v0.1 + v0.2 (auto-generated
   from docstrings via Sphinx-like extraction).

4. **`/docs/troubleshooting`** — 8 common gotchas:
   - "SQLite says database is locked" — use WAL mode or close other readers.
   - "JSON file too big to load" — use a smaller time range (`--from / --to`).
   - "Records missing" — check the host's log level, check handler list.
   - "CSV has weird quotes" — choose `dialect='unix'` for sane defaults.
   - "Browser won't open" — `--no-open` then visit `http://127.0.0.1:<port>` manually.
   - "Tailwind looks broken" — re-run `make web-tailwind`.
   - "Postgres connection refused" — `pg_hba.conf`, etc.
   - "Django app won't start" — check `pip install ulog[web]` ran fully.

5. **`/docs/sectors-and-files`** — the conceptual explanation of the
   left-sidebar tree, with a screenshot, 3 worked examples
   ("how to find all errors in the audio renderer in the last hour").

---

## 8. Roadmap continuation

- **v0.3** — real-time tail mode (WebSocket); multi-file merge view;
  filter export as CLI flags.
- **v0.4** — multi-user (auth, roles, team views).
- **v0.5** — graphs / dashboards (counts per minute, error rate
  per logger).
- **v1.0** — feature-frozen, PyPI Stable classifier.

---

## 9. Open questions

1. **Tailwind CLI bundling.** The standalone Tailwind CLI is a 25 MB
   binary. Ship it inside the wheel or download on first use? Lean
   toward "download on `make web-tailwind` first run, cache to
   `~/.cache/ulog/tailwind`."
2. **Sphinx vs handcrafted markdown.** v0.2 picks handcrafted markdown
   for the `/docs` pages — Sphinx adds a build dependency that's
   overkill for 5 pages. v0.4+ may move to it as the doc grows.
3. **Browser auto-open.** macOS `open`, Linux `xdg-open`, Windows
   `start`. Ship the cross-platform shim. (Python's `webbrowser`
   stdlib module covers all three; trust it.)
4. **SQL handler thread safety.** SQLAlchemy connections aren't
   thread-safe by default. Use a session-per-thread pattern? Or
   serialize emits via a queue? Lean toward a per-handler queue +
   single writer thread (the v0.3 async pattern naturally extends
   this).

---

## 10. Definition of Done — v0.2

- [ ] Three storage handlers shipped (`SQLHandler`, `JSONLineHandler`,
       `CSVHandler`) under `ulog/handlers/`.
- [ ] Django app under `ulog/web/` with full filter UI, list, detail,
       tutorial overlay, per-column tooltips.
- [ ] Tailwind CSS compiled + shipped under `ulog/web/static/ulog/`.
       Light + dark mode.
- [ ] Built-in `/docs` with 5 pages (quickstart, storage, api,
       troubleshooting, sectors-and-files).
- [ ] `ulog-web <path>` console script auto-detects file type.
- [ ] ≥ 60 unit tests covering storage handlers + Django views.
- [ ] mypy --strict green.
- [ ] WCAG 2.1 AA passes on the filter form + list view.
- [ ] README updated with screenshots + 5-line "Web UI" section.
- [ ] Tag `v0.2.0`.
