# ULog

> Stdlib `logging`, with the batteries that should have been included.

ULog is a thin layer on Python's standard `logging` module. It ships
sensible defaults, four built-in formatters
(qlnes / simple / verbose / json), terminal colour via
[ucolor](https://github.com/jojo8356/ucolor-python), and `contextvars`
field binding for structured logging. It DOESN'T fork the logger
hierarchy — code that uses `logging.getLogger(__name__)` keeps working
unchanged, including third-party libraries like `requests`,
`urllib3`, `boto3`, etc.

```python
import ulog

ulog.setup(format='qlnes', color='auto')
log = ulog.get_logger(__name__)

log.info("hello")          # → hello
log.error("boom")          # → qlnes: error: boom    (red on a TTY)
```

See [`docs/prds/PRD-v0.1-core.md`](./docs/prds/PRD-v0.1-core.md) for the full design rationale and roadmap.

## Install

ULog vendors [`ucolor`](https://github.com/jojo8356/ucolor-python) as
a git submodule under `vendor/ucolor-python/` so you don't have to
reinstall it separately. Always clone with `--recursive` (or
initialize submodules after the fact):

```bash
# 1. Clone with submodules
git clone --recursive https://github.com/jojo8356/ulog-python.git
cd ulog-python
# (equivalent if cloned without --recursive:
#  git submodule update --init --recursive)

# 2. Install ucolor from the submodule, then ULog itself
pip install -e ./vendor/ucolor-python
pip install -e ".[dev]"
```

For the storage + web stack:

```bash
pip install -e ".[storage,web,dev]"
```

ULog itself has **zero PyPI runtime dependencies**. ucolor is
optional — if it's missing, ULog falls back to an 8-color ANSI
palette automatically. Optional groups:

- `[storage]` — `sqlalchemy>=2.0` (needed by `SQLHandler`)
- `[web]` — `django>=5.0` + sqlalchemy (needed by `ulog-web`)
- `[dev]` — pytest + mypy

Python 3.10+.

## Quick tour

### Four formatters

```python
ulog.setup(format='qlnes')      # qlnes: error: msg     (default)
ulog.setup(format='simple')     # [ERROR] msg
ulog.setup(format='verbose')    # 2026-05-04T15:20:00Z ERROR [logger] msg (file:line)
ulog.setup(format='json')       # {"ts":"...","level":"ERROR","logger":"...","msg":"..."}
```

### Context binding

```python
ulog.bind(request_id="abc-123")
log.info("step 1")              # request_id propagates to JSON output
log.info("step 2")

with ulog.context(rom="alter_ego"):
    log.info("rendering")       # rom is set within the block, removed after
```

### Library-friendly

ULog never installs handlers on user-named loggers unless you call
`setup(name="myapp")` explicitly. Code in libraries does:

```python
log = ulog.get_logger(__name__)
log.info("hello from a library")
```

…and works whether or not the host application called `setup()`.

### Idempotent setup

```python
ulog.setup()
ulog.setup()           # no double-print — replaces the previous handler
ulog.setup(level='DEBUG')  # tests can re-setup freely
```

### Color resolution

Auto-detects TTY, honors the `NO_COLOR` env var (per
[no-color.org](https://no-color.org)), supports `--color {auto,always,never}`
CLI flags via the `color=` argument. Falls back to an 8-color ANSI
palette if `ucolor` isn't installed; with ucolor installed, uses
24-bit truecolor.

### Custom formatters

```python
class UpperFormatter(logging.Formatter):
    def format(self, record):
        return record.getMessage().upper()

ulog.register_formatter('upper', UpperFormatter)
ulog.setup(format='upper')
```

## Submodules

ULog vendors one external package as a **git submodule** to avoid
duplicating its source while still embedding it transparently in the
clone:

| Submodule | Repo | Init |
|---|---|---|
| `vendor/ucolor-python/` | [github.com/jojo8356/ucolor-python](https://github.com/jojo8356/ucolor-python) | `git submodule update --init --recursive` |

Update the submodule pin to a newer ucolor commit:

```bash
cd vendor/ucolor-python && git pull origin main && cd ../..
git add vendor/ucolor-python && git commit -m "bump ucolor"
```

## Why ULog over alternatives

| Lib | ULog wins on | They win on |
|---|---|---|
| stdlib `logging` | sensible defaults, ucolor, JSON formatter, `bind()`, idempotent | familiarity (no new lib) |
| `loguru` | stdlib-compat (catches third-party libs' logs), no fork | even simpler API |
| `structlog` | drop-in for stdlib consumers, no processor chains | richer event-style API, async-aware |
| `rich.logging` | production-shaped output, JSON for pipelines | beautiful tracebacks, syntax highlighting |

## v0.2 — Storage + Web UI

Three persistent handlers + a Django + Tailwind inspection UI ship in
v0.2 (see [`docs/prds/PRD-v0.2-storage-and-ui.md`](./docs/prds/PRD-v0.2-storage-and-ui.md)).

```python
ulog.setup(
    handlers=['stream', 'sql', 'json'],
    sql_url='sqlite:///./logs.sqlite',
    json_path='./logs.jsonl',
)
log.info("hello")  # → stderr + sqlite + jsonl
```

Then inspect the result in a browser:

```bash
pip install ulog[web]
ulog web ./logs.sqlite       # auto-detects sqlite/jsonl/csv
```

Features of the v0.2 UI:
- Filter sidebar (level, hierarchical sector tree, files,
  time range, bound-context fields, full-text search)
- Click any record for detail (JSON pretty-print, exception
  traceback, context fields)
- Tutorial overlay on first visit
- Per-column tooltips
- Light/dark mode (toggle + `prefers-color-scheme`)
- Built-in `/docs` (5 pages: quickstart, storage, api,
  troubleshooting, sectors-and-files)

## v0.5+ — Forensic black box

The `ulog` CLI ships 15+ subcommands beyond `ulog web` (see
[RELEASE_NOTES.md](./RELEASE_NOTES.md) for the full migration from
`ulog-web` → `ulog web`):

```bash
ulog setup integrity=hash-chain      # via setup() — hash-chained SQLite
ulog verify ./logs.sqlite            # walk the chain, OK / BROKEN exit codes
ulog repair --confirm ./logs.sqlite  # archive orphans + truncate
ulog purge --before 2026-01-01       # purge respecting min_retention_days

ulog correlate "level=ERROR"         # over/under-represented dimensions
ulog bisect "stripe.*5\d\d"          # first chain row matching a regex
ulog replay "level=ERROR" --to-pytest /tmp/test_inc.py  # generate a regression test
ulog explain                         # waterfall span tree (PRD-v0.7)
ulog trace 4bf92f...                 # cross-service OTel trace_id

ulog incidents --status open         # CI gate: exit code = open incident count
ulog incidents --report --since 1m   # Markdown KPIs (MTTR / P95 / top closers)
ulog fix resolve --record-id 42 \    # signature-based fix DB (PRD-v0.13)
        --writeup "restarted pool" --by "Johan"

ulog import nginx-access.log --db prod.sqlite      # ingest external logs (PRD-v0.17)
ulog snapshot --format pdf --since today           # multi-format archive (PRD-v0.6.1)
ulog export-html ./logs.sqlite --output /tmp/audit # static HTML bundle (PRD-v0.6)
ulog enable-fts5 ./logs.sqlite                     # opt-in full-text search
ulog validate-resources --path .                   # JSON/TOML/CSV/INI parse gate
ulog bug-cache refresh --source-file curated.json  # local known-bugs cache
ulog solutions {keygen,publish,fetch}              # community solutions site client
```

### Python API additions (v0.5+)

```python
import ulog

# v0.5 — chain integrity + replay + incidents
ulog.setup(integrity="hash-chain", min_retention_days=30,
           handlers=["sql"], sql_url="sqlite:///./logs.sqlite",
           issue_template_url="https://linear.app/team/new?title={msg}",
           capture_stack=True)        # PRD-v0.12 — every record captures its stack
ulog.resolve("3f7c12a", by="Johan")  # incident lifecycle
ulog.reopen("3f7c12a", reason="recurrence")
ulog.compute_states(records)         # latest-wins state walk

# v0.5 — query API
ulog.replay("./logs.sqlite", where_dsl="level=ERROR", on=lambda r: ...)
ulog.correlate("level=ERROR", db="./logs.sqlite")
ulog.bisect("timeout", db="./logs.sqlite")

# v0.7 — span-based execution timeline
with ulog.span("setup_db"):
    with ulog.span("git_clone"):
        ...

# v0.10 — fleet probes
from ulog.fleet import probe
@probe(target="https://api.example.com/health", parents=["db.internal"])
def test_api_health():
    ...
```

### Viewer features added v0.5+

- **Integrity badge** in every page header (green ✓ / red ✗ BROKEN /
  gray "never verified").
- **Incidents sidebar** quick filters + detail-page "Resolves /
  Resolved by" cross-links.
- **Multi-track view** at `/multi-track/` — 4 SVG strips (level /
  service / author / file) over shared time axis.
- **HTTP request inspector** panel — auto-detects `method+url` in
  context, renders body / headers / status with "Copy as curl"
  (sensitive headers masked).
- **Known-fix panel** — when the record's signature matches the
  local fix DB, the writeup surfaces inline.
- **Search solutions** button — per-record consent dialog, fans
  out across local (v0.13), known-bugs cache (v0.14), community
  site (v0.15).
- **Call-stack panel** — collapsible frame tree with optional
  locals capture (PRD-v0.12).
- **Span panel** — span_name + duration + parent chain link
  (PRD-v0.7).
- **Fleet sidebar tree** — `@probe`-decorated probes grouped by
  parent/child (PRD-v0.10).
- **Resources sidebar** — JSON/TOML/CSV/INI parse status badges
  (PRD-v0.9; opt-in via `ULOG_RESOURCES_DIR=`).
- **/team/** directory — per-author cards with GitHub URL
  inference (PRD-v0.4.3).
- **View-source links** on file:line — `ULOG_SOURCE_BASE_URL=` or
  `ULOG_AUTHOR_REPO=` env config (PRD-v0.12 phase 3).
- **HTMX-augmented** multi-track form + records pagination (PRD-v0.8)
  — sidebar stays cached, only the affected region swaps.
- **Prism.js syntax highlighting** on `/docs/*` (PRD-v0.8.1).
- **Tailwind built locally** via `make tailwind-build` — no CDN
  runtime, offline-clean.

## Tests

```bash
make test         # 900+ tests across v0.1 → v0.17
make mypy         # mypy --strict
make check        # both

# Per-PRD slice:
.venv/bin/pytest tests/test_chain*.py        # Epic 3 — chain integrity
.venv/bin/pytest tests/test_replay*.py       # Epic 4 — queryability
.venv/bin/pytest tests/test_incidents*.py    # Epic 5 — incident lifecycle
.venv/bin/pytest tests/test_export_html.py   # Epic 8 — static export
```

## Release engineering

```bash
make tailwind-build       # rebuild ulog/web/static/ulog/tailwind.css
make tailwind-check       # CI gate: fail on committed CSS drift
make bench-fixture        # generate tests/fixtures/bench_100k.sqlite
make bench-export         # pytest-benchmark export-html SC1 gate
```

Self-host the community-solutions site:

```bash
cd docker/ulog-solutions && docker compose up -d
export ULOG_SOLUTIONS_ENDPOINT=http://localhost:8080/v1
ulog web ./logs.sqlite
```

## License

MIT.
