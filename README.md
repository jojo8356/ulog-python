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

See `PRD.md` for the full design rationale and roadmap.

## Install

```bash
# Editable from a clone
git clone https://github.com/jojo8356/ulog-python.git
cd ulog-python
pip install -e ".[dev]"

# Or pin via requirements.txt with -e or git+ syntax
```

Requires Python 3.10+. One required dep: `ucolor`. Optional `[json]`
extra brings `orjson` for faster JSON serialization (planned v0.2).

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

## Why ULog over alternatives

| Lib | ULog wins on | They win on |
|---|---|---|
| stdlib `logging` | sensible defaults, ucolor, JSON formatter, `bind()`, idempotent | familiarity (no new lib) |
| `loguru` | stdlib-compat (catches third-party libs' logs), no fork | even simpler API |
| `structlog` | drop-in for stdlib consumers, no processor chains | richer event-style API, async-aware |
| `rich.logging` | production-shaped output, JSON for pipelines | beautiful tracebacks, syntax highlighting |

## v0.2 — Storage + Web UI

Three persistent handlers + a Django + Tailwind inspection UI ship in
v0.2 (see [`PRD-v0.2-storage-and-ui.md`](./PRD-v0.2-storage-and-ui.md)).

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
ulog-web ./logs.sqlite       # auto-detects sqlite/jsonl/csv
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

## Tests

```bash
make test         # 69 unit + integration tests across v0.1 + v0.2
make mypy         # mypy --strict
make check        # both
```

## License

MIT.
