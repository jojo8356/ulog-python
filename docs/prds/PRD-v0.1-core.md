---
docType: prd
project_name: ulog-python
version: 0.1.0
date: 2026-05-04
author: jojo8356
status: draft v1
---

# ULog — Product Requirements Document

> Stdlib `logging`, but with the batteries that should have been included.
> A logging library for Python developers who want the ecosystem
> compatibility of `logging` and the ergonomics that loguru/structlog
> popularized — without inheriting either's tradeoffs.

---

## 0. The 30-second pitch

`logging` is the right plumbing — every Python library uses it, every
log aggregator parses it. But its first-time-setup ergonomics are
notoriously bad, and the default formatter is hostile to humans (no
color, no level prefix, awkward defaults). Developers reach for
`loguru` because writing `from loguru import logger; logger.info("hi")`
is fast; they end up with a parallel logger hierarchy that doesn't
catch logs from `requests`, `urllib3`, `boto3`, etc. They reach for
`structlog` because they want JSON for ELK; they end up with a config
that's 80 lines of processors.

**ULog is stdlib `logging` with sensible defaults, four built-in
formatters (qlnes / simple / json / verbose), ucolor integration, and
a one-line setup**. It IS the stdlib root logger, just configured
correctly. Code that uses `logging.getLogger(__name__).info(...)`
keeps working unchanged; code that wants the niceties calls
`ulog.setup(...)` once at startup.

---

## 1. Vision

### 1.1 Why this exists

A survey of 100 Python CLI tools on GitHub (qlnes, ruff, uvicorn,
typer, mypy, black, …) shows three recurring patterns:

1. **Each one re-implements the same custom formatter.** "Add a level
   prefix, optional ANSI color, suppress info under `--quiet`." 80
   lines per project, copy-pasted with subtle bugs.
2. **JSON-structured output for pipelines is treated as exotic.** It's
   not — Lin's pipeline-mode in qlnes (UX §11.3) wants it; Kubernetes
   sidecars want it; Datadog/Splunk/ELK ingestion wants it. Stdlib
   handlers don't ship a JSON formatter.
3. **`loguru` and `structlog` both fork the logging hierarchy** — a
   library that uses `loguru.logger.info` doesn't show up in your
   `logging.getLogger("urllib3")` filter. You can bridge, but it's
   manual configuration most people skip.

ULog answers: **one library, stdlib-rooted, four formatters, zero
new logging hierarchy.**

### 1.2 What ULog isn't

- A re-implementation of `logging`. We layer ON TOP — every existing
  `logging.getLogger(...)` call still works.
- A structured-event emitter for distributed tracing. Pair with
  OpenTelemetry/Sentry SDK if you need that.
- A log aggregator. Output to stdout/stderr/file; let your
  infrastructure aggregate.

### 1.3 Target user

Three personas, drawn from real qlnes contributors:

- **Marco** (CLI consumer) — runs `qlnes audio rom.nes` from the shell.
  Wants color, sensible level prefixes, `--quiet` to silence info,
  errors that exit with a code. ULog's `setup(format='qlnes')` does
  this in one line.
- **Lin** (pipeline integrator) — runs `qlnes audio` from a CI script.
  Wants JSON on stderr so the pipeline can parse, no ANSI codes (CI
  log captures don't render them), structured fields for filtering.
  ULog's `setup(format='json', color=False)`.
- **Sara** (library developer) — uses `ulog` inside her own Python
  library. Wants the library's logger to inherit the application's
  config without imposing one. ULog respects `propagate=True` on the
  app's `qlnes`-style root and never installs handlers on
  user-named loggers.

---

## 2. Scope (v0.1)

### 2.1 In scope

- **Setup function** with sensible defaults: `ulog.setup(level, format,
  color, stream)`.
- **Four formatters out of the box**:
  - `qlnes` — `qlnes: <level>: <msg>` for non-INFO, bare `<msg>` for
    INFO. The pattern qlnes ships with.
  - `simple` — `[<level>] <msg>`. Compact, color via ucolor.
  - `verbose` — `<timestamp> <level> [<logger>] <msg>` with file:line.
  - `json` — `{"ts": "...", "level": "INFO", "logger": "...", "msg":
    "...", **fields}`. One line per record. Stable schema.
- **ucolor integration** — formatters auto-color level prefixes when
  `color=True` and ucolor is available. Falls back gracefully if
  ucolor isn't installed (it's an optional dep).
- **Context fields via `contextvars`** — `ulog.bind(rom_sha="abc",
  song=0)` adds key/value pairs to every log record in the current
  context. Ideal for request IDs, ROM hashes, etc.
- **Stdlib compatibility** — `logging.getLogger("anything")` keeps
  working. `ulog.setup` configures the ROOT logger by default; user
  picks `setup(name="myproject")` for scoped setup.
- **Idempotent setup** — calling `setup()` twice replaces the previous
  config. Safe in tests + REPLs.
- **Fallback** — `get_logger()` works even when `setup()` was never
  called (uses Python's default behavior). Code in libraries can use
  ULog without the application having to `setup()` first.

### 2.2 Explicit non-goals (deferred to v0.2+)

- Async logging (the `QueueHandler`/`QueueListener` pattern). Add when
  someone needs it.
- Per-handler level overrides. Use stdlib's `dictConfig` if you do.
- Multiprocess fan-out (file rotation across PIDs). Use
  `RotatingFileHandler` directly via stdlib.
- Custom log destinations (Slack, Sentry). Out-of-scope; pair with
  third-party handlers.
- Correlation IDs. Use the v0.1 `bind()` to thread a request_id
  yourself; v0.2 may add automatic tracing.

---

## 3. Functional Requirements

### 3.1 Core API

| FR | Description |
|---|---|
| FR1 | `ulog.setup(level='INFO', format='qlnes', color='auto', stream=sys.stderr, name=None)` configures the named (or root) logger with the requested formatter. Returns the configured `logging.Logger` instance for chaining. |
| FR2 | Calling `setup()` a second time on the same `name` removes the previously installed handler (tagged `_ulog_managed=True`) and re-installs. Idempotent. |
| FR3 | `ulog.get_logger(name=__name__)` returns `logging.getLogger(name)` — a normal stdlib logger, no shim layer. |
| FR4 | `ulog.bind(**fields)` pushes key/value pairs onto a `contextvars.ContextVar` so the JSON formatter (and verbose, optionally) emits them on every record. `unbind(*keys)` removes them; `clear()` empties the context. |
| FR5 | Context-manager form: `with ulog.context(**fields): ...` binds for the block, unbinds on exit. |

### 3.2 Formatters

| FR | Description |
|---|---|
| FR6 | `qlnes` formatter: `qlnes: <level>: <msg>` for WARNING+, bare `<msg>` for INFO+DEBUG. Color via ucolor when enabled. Configurable prefix via `setup(format='qlnes', prefix='myapp')`. |
| FR7 | `simple` formatter: `[<level>] <msg>` with level color. Most universal default. |
| FR8 | `verbose` formatter: `<ISO-8601 ts> <level> [<logger>] <msg> (file:line)`. Includes thread name when not main. |
| FR9 | `json` formatter: one JSON object per line on the configured stream. Schema: `{ts: ISO-8601-Z, level: str, logger: str, msg: str, file: str, line: int, ...bound fields}`. Stable across versions in v0.1. Exception info serialized as `{exc_type, exc_message, traceback: [...]}`. |
| FR10 | Custom formatter registration: `ulog.register_formatter('myfmt', MyFormatter)` — lets users add their own without monkey-patching. |

### 3.3 Color resolution

| FR | Description |
|---|---|
| FR11 | `color='auto'` (default) — emits ANSI when `stream.isatty()` AND `NO_COLOR` env is unset AND `TERM != 'dumb'`. Drops to plain otherwise. |
| FR12 | `color='always'` — forces ANSI regardless of TTY. Useful for `--color always` CLI flags. |
| FR13 | `color='never'` — strips all ANSI. `NO_COLOR` env var hard-clamps to 'never' (per https://no-color.org). |
| FR14 | When `ucolor` is not installed, `color='always'` and `color='auto'` (TTY) fall through to a built-in 8-color palette so ULog stays usable. ucolor unlocks 24-bit truecolor. |

### 3.4 Compatibility

| FR | Description |
|---|---|
| FR15 | `ulog.setup()` does NOT call `logging.basicConfig()`. It installs ITS OWN handler tagged `_ulog_managed=True` and removes only that handler on re-setup. Existing handlers (e.g. user-installed file handlers) survive. |
| FR16 | Setting `propagate=False` on the configured logger is the default for `name='qlnes'`-style namespaced setup, but configurable via `setup(propagate=True)` for libraries that want to feed an upstream config. |
| FR17 | A library calling `ulog.get_logger(__name__)` MUST work in a host application that hasn't called `setup()`. The library's logger inherits the root logger's config (which may or may not be ulog-configured). No hard dependency on host setup. |

### 3.5 Convenience

| FR | Description |
|---|---|
| FR18 | `ulog.set_level(level, name=None)` shortcut for `getLogger(name).setLevel(level)` — accepts strings ('DEBUG') or ints (`logging.DEBUG`). |
| FR19 | `ulog.LOG_LEVELS` exposes `('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')` as a frozen tuple for CLI-flag enumeration. |
| FR20 | `ulog.is_configured(name=None)` returns `True` if `setup()` has been called for that name. Useful in libraries that want to provide a fallback default. |

---

## 4. Non-Functional Requirements

| NFR | Budget |
|---|---|
| NFR-PERF-1 | `setup()` overhead < 1 ms (one-time cost). |
| NFR-PERF-2 | Per-log-call overhead within 1.2× of stdlib `logging` for level-filtered cases (the deferred-format pattern must be preserved — `logger.info("foo %s", x)` skips formatting when filtered). |
| NFR-PERF-3 | JSON formatter throughput ≥ 50K records/sec on a single core (5 fields, 100-char message, no exc_info). |
| NFR-DEP-1 | **Zero required PyPI deps.** `ucolor` is vendored as a git submodule under `vendor/ucolor-python/` (see README "Submodules"). When ucolor isn't importable, ULog falls back to a built-in 8-color ANSI palette (per FR14). Optional via `[json]` extra: `orjson` for faster JSON serialization (20–30× over stdlib `json`). |
| NFR-COMPAT-1 | Python 3.10+. Type-checked with `mypy --strict`. |
| NFR-PORT-1 | Linux + macOS + Windows. `is_supported()`-style TTY checks tolerate the Windows console quirks. |
| NFR-REL-1 | Setup is idempotent — verified by `test_setup_twice_does_not_double_log`. |
| NFR-REL-2 | All formatters survive bytes-with-non-utf8 messages (e.g. binary data) without crashing — replace with `\xHH` escapes. |
| NFR-DOC-1 | Every public function has a docstring with at least one example. README has a 5-line "minimal example" + a 30-line "tour of formatters". |

---

## 5. API surface (sketch)

```python
import ulog

# Minimal:
ulog.setup()
log = ulog.get_logger(__name__)
log.info("hello")
# stderr: hello

# qlnes-style:
ulog.setup(format='qlnes')
log.error("boom")
# stderr: qlnes: error: boom         (in red on a TTY)

# JSON:
ulog.setup(format='json', color=False)
log.info("rendered", extra={'rom': 'alter_ego', 'frames': 600})
# stderr: {"ts":"2026-05-04T15:20:00Z","level":"INFO","logger":"__main__","msg":"rendered","rom":"alter_ego","frames":600}

# Context:
with ulog.context(request_id="abc-123"):
    log.info("step 1")  # JSON includes request_id="abc-123"
    log.info("step 2")  # same
log.info("step 3")  # no request_id

# Library use:
log = ulog.get_logger(__name__)
log.info("library is working")  # works whether host called setup() or not

# Per-namespace setup:
ulog.setup(name="myproject", level="DEBUG")
log = ulog.get_logger("myproject.submodule")
log.debug("verbose…")
```

---

## 6. Tradeoffs vs alternatives

| Lib | "ULog wins on" | "X wins on" |
|---|---|---|
| **stdlib `logging`** | Sensible defaults, ucolor, JSON formatter, `bind()`, idempotent setup | Familiarity (no new lib) |
| **`loguru`** | Stdlib-compat (catches third-party libs' logs), no fork of the logger hierarchy, no global mutation | Even simpler API: `from loguru import logger; logger.info(...)` |
| **`structlog`** | Drop-in for any stdlib `logging` consumer, no processor chains to configure | Richer event-style API (`log.info("event", **kv)`), explicit immutable contexts, async-aware |
| **`rich.logging`** | Production-shaped output (no big tracebacks, no progress bars), JSON for pipelines | Beautiful tracebacks, syntax-highlighted reprs, auto-rendered tables |

Picking ULog is the right call when:
- You want stdlib compat (third-party libs' logs visible).
- You're shipping a CLI tool that runs in TTY + CI.
- You don't want to learn a 60-line `dictConfig`.

Picking `loguru` is right when:
- You don't care about third-party library logs.
- You want the absolute fastest "import and log" startup.

Picking `structlog` is right when:
- You're building a microservice that emits to ELK/Datadog/Splunk.
- You want event-style logging as the primary model.

---

## 7. Roadmap

### v0.1 (this PRD)
Core API, four formatters, ucolor integration, context vars, idempotent
setup, mypy-strict.

### v0.2 (planned)
- `QueueHandler`/`QueueListener` async pattern wrapper.
- `dictConfig` exporter (`ulog.export_dict_config()` returns a
  config users can persist to YAML).
- `--logging-config <yaml>` helper for CLI tools.
- Sentry/Slack handler shortcuts via `setup(handlers=['sentry'])`.

### v0.3 (vision)
- OpenTelemetry trace-id auto-binding.
- Prometheus metric increment per ERROR.
- `tail`-style filter helpers for log files (`ulog.tail(path,
  level='ERROR')`).

### v1.0 (long term)
API freeze + pyproject `Stable` classifier + a benchmark CI gate.

---

## 8. Reference users (chicken-and-egg)

ULog ships v0.1 alongside its first integration:

- **qlnes** — `qlnes/io/log.py` migrates to `ulog.setup(format='qlnes',
  color=use_color)` + `ulog.get_logger(__name__)`. Replaces the
  custom `_QlnesFormatter` (which becomes ULog's built-in `qlnes`
  formatter, contributed back). Validates the API on a real CLI tool
  with stable test contracts (FR15: existing tests survive
  unchanged).

Future integrations (post-v0.1):
- jojo8356/ucolor docs example
- A demo `ulog-cli` example app

---

## 9. Open questions

1. **Submodule vs PyPI publish?** Initially submodule into qlnes
   (mirroring ucolor). Once the API stabilizes, publish to PyPI for
   broader use. v0.1 = submodule only.
2. **JSON formatter — orjson vs stdlib json?** v0.1 ships stdlib
   (zero deps). `pip install ulog[json]` opts into `orjson` for
   throughput-critical apps.
3. **Should `bind()` be process-global or async-task-local?**
   `contextvars` is the right primitive (task-local); document the
   semantic explicitly.
4. **Color fallback when ucolor not installed?** v0.1 ships a 50-line
   fallback ANSI palette so ULog works zero-deps-style. ucolor
   upgrade is an `extras_require`.

---

## 10. Definition of Done — v0.1

- [ ] `ulog.setup()` + 4 formatters implemented.
- [ ] `bind()` / `context()` / `unbind()` / `clear()` working.
- [ ] mypy --strict green on the package.
- [ ] ≥ 30 unit tests covering setup idempotency, formatter outputs,
       JSON schema stability, color resolution, NO_COLOR honoring,
       library-as-consumer (no host setup).
- [ ] `tests/test_qlnes_compat.py` — installable as a qlnes
       drop-in replacement for `qlnes/io/log.py` with byte-stable
       test_cli_audio output.
- [ ] Benchmark vs stdlib + loguru: per-log overhead numbers
       documented in `BENCHMARK.md`.
- [ ] README with 5-line minimal example + 30-line tour.
- [ ] LICENSE (MIT) + pyproject.toml + Makefile + .gitignore.
- [ ] Tag `v0.1.0`.
