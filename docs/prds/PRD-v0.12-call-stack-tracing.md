---
docType: prd
project_name: ulog-python
version: 0.12.0
date: 2026-05-12
author: jojo8356
status: draft v1
parent_prd: PRD-v0.2-storage-and-ui.md
related_prd:
  - PRD-v0.7-test-execution-stack.md
---

# ULog v0.12 — Per-record call-stack tracing

> Every log record captures the **full Python call stack** at emit
> time (function name, file, line, locals snapshot — opt-in). **The
> web UI renders the stack ON EVERY record's detail page** as a
> collapsible tree, like `EXPLAIN ANALYZE` for the call path that
> produced the log. The "Call stack" panel is a MANDATORY surface
> on `/r/<id>/` whenever the record has a stack — not behind a
> setting, not opt-in to display. A bug becomes "click the record →
> see the 12 frames that led here" instead of "grep + git blame +
> cross-reference".

---

## 0. 30-second pitch

When a record says `log.error("payment failed")`, the existing
viewer shows: timestamp, level, msg, file:line, exception (if any).
**Missing: the call path.** Who called the function that logged
this? Their caller? The caller's caller? Today you reconstruct the
stack from a stack trace IF one was attached (exception path only);
on a plain `log.error(...)` it's grep-and-pray.

v0.12 adds a `stack` column populated at emit time via
`traceback.extract_stack()` — cheap, stdlib, no sampling. The
detail view renders the frames as a collapsible tree with each
frame: `module.function (file:line)`. Optional `--with-locals`
captures `repr()` of each frame's locals (10 KB cap per frame),
so you can answer "what was `order_id` at frame 3?" in one click.

Adjacent but distinct from v0.7 (test execution waterfall — spans
across multiple tests). v0.12 is per-record, in-process, applies
to EVERY log record regardless of test context.

---

## 1. Vision

### 1.1 Why this exists

Three observations:

1. **`log.exception(...)` gets you the trace; `log.error(...)` doesn't.** But most "error" log lines are NOT inside an `except` block — they're early-return cases, validation failures, business-rule rejections. No exception, no stack trace. v0.12 fixes the asymmetry.
2. **The call stack is the highest-signal-per-byte context** an emit can carry. Knowing "this log fired from `compute_tax → apply_vat_rules → eu_rate_lookup`" answers 80% of "where in the code does this happen?" questions instantly.
3. **`traceback.extract_stack()` is stdlib + fast.** ~5 µs per call on a 20-frame stack on a modern CPU. Affordable as a default; opt-out for the latency-paranoid 1%.

### 1.2 What v0.12 isn't

- **Not a profiler.** No `sys.setprofile` / `sys.settrace`. We capture the stack only on log emit, not on every function call.
- **Not a tracer in the OpenTelemetry sense.** No spans, no parent_id chain (that's v0.7), no service-mesh propagation. Per-record only.
- **Not a "step-through debugger".** No replay, no time-travel. v0.12 captures + renders; debugger replacement is out of scope forever.
- **Not a memory-dump tool.** Locals are captured as `repr(value)[:10240]` — strings only, no live object reference, no serialisation of arbitrary objects.
- **Not retroactive.** Records emitted before v0.12 won't have a stack. The new column is nullable.

### 1.3 Target users

- **Sara** (carried) — debugging a library that fails on a specific input. Today: add print statements, re-run, remove. v0.12: stack on the failing record reveals the input-routing path.
- **Maria** (carried from v0.10, SRE) — triaging cascading failures. Stack on `log.error("circuit breaker open")` reveals which upstream call triggered it, no instrumentation needed.
- **Marco** (carried, solo dev) — early-return cases in his Flask app. Stack at `log.warning("invalid coupon")` shows the route handler + middleware chain.
- **NEW: Tom**, who reviews other devs' code at code review time. v0.12 lets reviewers click a failing-test log and see the full call path without checking out the branch locally.

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | Default-on emit captures `stack` in ≤ 50 µs on a 20-frame Python stack | yes (NFR-PERF-130) |
| SC2 | Storage overhead per record ≤ 2 KB without `--with-locals`, ≤ 12 KB with `--with-locals` | yes |
| SC3 | EVERY record detail view (`/r/<id>/`) with a non-NULL stack renders the "Call stack" panel — no setting can hide it from the page. Collapsible tree, lazy-expand at frame 5+ | yes |
| SC3b | The records-list shows a small `stack: N frames` indicator inline next to the file:line for any record with a captured stack | yes |
| SC4 | Locals capture uses `repr()` with a 10 KB-per-frame cap | yes |
| SC5 | Zero new PyPI runtime deps (stdlib `traceback`, `inspect`) | yes |
| SC6 | `setup(capture_stack=False)` disables the feature with zero overhead (the column stays NULL) | yes |
| SC7 | Stack frames inside ULog's own code (`ulog/handlers/sql.py`, etc.) filtered out — the user sees their app's stack, not the logging pipeline's | yes |

---

## 2. Scope (v0.12)

### 2.1 In scope (7 features, ~ 400 LOC)

1. **DB schema extension** — new column `logs.stack` (LargeBinary, JSON-encoded list of frames). Nullable. Part of v0.5 chain hash when chain mode is active.
2. **Capture in `SQLHandler._record_to_row`** — when `setup(capture_stack=True)` (default), call `traceback.extract_stack()` minus the ULog-internal frames, store as a list of `{file, line, function, code, locals?}` dicts.
3. **ULog-frame filter** — automatic exclusion of frames inside `ulog/`, `logging/`, the pytest plugin. Configurable via `setup(stack_filter_patterns=[...])`.
4. **Locals capture (opt-in)** — `setup(capture_stack_locals=True)`: each frame includes `locals` (dict of `name → repr(value)[:10240]`). Off by default for perf + privacy. Sensitive-key masking reuses v0.11's header-masking conventions.
5. **Detail view "Call stack" panel — MANDATORY rendering** — between "Authored by" (v0.4) and "Exception" (v0.2). The panel SHALL be present on every `/r/<id>/` page where `record.stack` is non-NULL; it is NOT behind a setting, NOT collapsible-into-hidden, NOT behind a `?show_stack=1` URL param. Default state: closed if > 5 frames, open if ≤ 5. User expand/collapse toggle persists in `localStorage` under `ulog:stack_panel_open` (per-record-id). Frames render as `<ol>` numbered (1 = outermost, N = emit site).
6. **Frame click → source line** — when ULog's `--repo` is set (v0.4 author indexer's `--repo`), each frame's `file:line` becomes a link to `/source/<path>:<line>/` (a small new view rendering ±5 lines of source around the line, syntax-highlighted via Prism v0.8.1). 404 if file not in repo or v0.4 isn't enabled.
7. **CLI `ulog stack <record_id>`** — print the stack for a single record to stdout (text format) for shell-side triage. `--format json` for piping.

### 2.2 Explicit non-goals (deferred or never)

- **Full `sys.setprofile` tracing** — out forever. Sampling-based "ulog perf" is a different feature (v1.x).
- **Async stack frames (Tasks, Futures)** — out of v0.12. asyncio stacks need `asyncio.format_stack()`; v0.12.1 candidate.
- **C-extension frames (numpy, native libs)** — out. `traceback.extract_stack()` already excludes them; we won't go beyond.
- **Live "stack diff" between two records** — out. Compute with `difflib` if you want it; v0.12.x candidate.
- **Persist locals as live Python objects** (pickle) — out forever (security + size + serialisability nightmare).

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Stack is huge (> 200 frames — e.g. recursive bug) | Truncate to 100 inner-most frames + 5 outer-most + "… N frames elided …" marker. |
| A frame's locals contain a non-repr-able object (raising in `__repr__`) | Replace with `<repr failed: ExceptionType>`. Don't crash the emit path. |
| Locals contain a 500 MB list | `repr()` itself caps; we further hard-cap at 10 KB per frame. |
| Sensitive value in locals (e.g. `password = "abc"`) | Masking by name: keys matching `*password*`, `*secret*`, `*token*`, `*api_key*` (case-insensitive) → `<masked>`. Configurable via `setup(stack_sensitive_locals_patterns=[...])`. |
| Record is emitted from `<string>` / `<console>` (eval / REPL) | Frame's `file` literally is `<string>`; rendered as-is, no source link. |
| Record is emitted from a generator coroutine | Stack shows up to the generator's resumed point; documented limitation. |
| User calls `log.error(...)` from `__del__` during interpreter shutdown | Stack may be incomplete; ULog catches the error per existing `Handler.handleError` semantics. |
| Chain mode (v0.5) + stack column | Stack JSON is part of the canonical hash. Tampering with stack invalidates the chain. |

### 2.4 Protected invariants

- **I5 (carried):** Logging API unchanged. v0.12 is OPT-DEFAULT (on) but disable-able via `setup(capture_stack=False)`.
- **I13 (new):** Locals capture is OPT-IN (off by default) — privacy + perf.
- **I14 (new):** ULog's own frames NEVER appear in the captured stack. Tested in `tests/test_stack_capture.py::test_ulog_frames_excluded`.

---

## 3. Functional Requirements

- **FR181**: `setup(capture_stack: bool = True, capture_stack_locals: bool = False, stack_filter_patterns: list[str] = None, stack_sensitive_locals_patterns: list[str] = None)`.
- **FR182**: `_record_to_row` captures the stack via `traceback.extract_stack()` minus filtered frames.
- **FR183**: Frame schema: `{"file": str, "line": int, "function": str, "code": str, "locals": dict | None}`. `code` = the raw source line (from `linecache.getline`, no syntax processing).
- **FR184**: Detail view: MANDATORY "Call stack (N frames)" panel on `/r/<id>/` whenever `record.stack` is non-NULL. NO setting hides it from the page. Renders outermost frame first; tooltip on each frame shows the code snippet from `linecache`. Panel slot is reserved in the template even on records without a stack (renders empty "no stack captured for this record" notice instead of being absent) so the page layout is stable.
- **FR184b**: Records list (`/`) inline marker: when a record has a non-NULL stack, append a small ` · stack: N` text next to its `file:line` (clickable to the detail view's stack anchor `#stack`). Visible at all viewport widths; no hover-required.
- **FR184c**: Each frame in the panel renders 4 elements ALWAYS visible: position number (1-based), `module.function` (bolded), `file:line` (monospace, clickable if `--repo` set), and the source-line snippet (1 line, italic muted). Locals (when captured) render under each frame in a `<details>` element collapsed by default.
- **FR185**: Frame links: when `--repo` set, `file:line` → `<a href="/source/<rel>:<line>/">file:line</a>`.
- **FR186**: `/source/<path>:<line>/` view: 11 lines of source (target ±5), Prism-highlighted, the target line marker highlighted.
- **FR187**: CLI `ulog stack <record_id> [--format text|json] [--with-locals] [--db PATH]`.
- **FR188**: Stack column included in chain canonical JSON when chain mode is active.
- **FR189**: `ulog/_stack_capture.py` — capture + filter + locals-mask helpers. Single module, ≤ 200 LOC.
- **FR190**: Records-list sidebar: NO new filter axis (stack content is too high-cardinality to filter on). Documented decision.

---

## 4. Non-Functional Requirements

- **NFR-PERF-130**: Default capture ≤ 50 µs on a 20-frame Python stack. With locals: ≤ 200 µs.
- **NFR-PERF-131**: Detail-view render: collapsible tree ≤ 50 ms for a 50-frame stack.
- **NFR-DEP-120**: Stdlib only (`traceback`, `inspect`, `linecache`).
- **NFR-SEC-120**: Locals masking (when `capture_stack_locals=True`) is unconditional for default patterns; user can add but not remove the defaults (mirrors v0.11 D3).
- **NFR-DOC-120**: `/docs/call-stack/` doc page with: perf footprint table, locals-capture trade-offs, filter pattern syntax, source-link prerequisites (v0.4 `--repo`).

---

## 5. API surface (sketch)

```python
ulog.setup(
    integrity='hash-chain',
    capture_stack=True,                                  # default
    capture_stack_locals=False,                          # default
    stack_filter_patterns=['mylib/decorators.py'],       # ADD
    stack_sensitive_locals_patterns=['*tenant_token*'],  # ADD to defaults
)

log = ulog.get_logger("svc.checkout")
log.error("payment failed")  # ← stack captured automatically
```

```bash
ulog stack 142071 --with-locals
# Outputs the 12 frames + locals for record id 142071.

ulog stack 142071 --format json | jq '.frames[-1]'
# Just the innermost frame.
```

---

## 6. Implementation sketch

| Story | Scope | LOC |
|---|---|---|
| 12.1 | `_stack_capture.py` — capture, filter, locals-mask | 150 |
| 12.2 | DB schema extension + chain-hash integration | 50 |
| 12.3 | `setup()` new kwargs | 40 |
| 12.4 | Detail-view "Call stack" panel + collapsible tree | 80 |
| 12.5 | `/source/<path>:<line>/` view + Prism wiring | 70 |
| 12.6 | `ulog stack <id>` CLI subcommand | 50 |
| 12.7 | Doc page `/docs/call-stack/` | n/a |
| 12.8 | Edge case tests (truncation, repr-fail, sensitive locals) | ~ tests |

Total ~ 440 LOC.

---

## 7. Decisions log

| ID | Decision | Trade-off |
|---|---|---|
| D1 | Stack captured at EMIT time, not at function entry | ~50 µs / emit overhead vs trivial implementation. `setProfile` route was rejected (~10× overhead). |
| D2 | Default ON, with `setup(capture_stack=False)` opt-out | Pay the perf cost only if it bites. Most users won't notice. |
| D3 | Locals OPT-IN | Privacy + serialisation pain. Worth it for deep debug; not worth it for default. |
| D4 | ULog's own frames filtered automatically | The pipeline is implementation detail; the user wants THEIR stack. |
| D5 | Locals are `repr()` strings, NOT live objects | Stdlib serialisable + safe. Lossy for complex objects, but `repr()` is the universal "tell me about this" lens. |
| D6 | Stack column part of chain hash | Forensic integrity: tampering with stack invalidates the chain. |
| D7 | NO records-list filter on stack content | High cardinality (~unique per record); filter UI would be useless. Search exists for "msg contains X"; stack search would be a v1.x candidate. |
| D7b | Stack panel is MANDATORY on detail view — no setting can hide it from the page | The whole point of v0.12 is that the stack is visible. A "hide stack panel" toggle would undermine the value prop. Users who want to disable capture use `setup(capture_stack=False)`; the panel then renders the "no stack captured" notice instead of being absent. |
| D8 | Frame source links require v0.4 `--repo` | Reuses the author indexer's repo-root discovery. No new mechanism. |
| D9 | Truncate giant stacks at 100 inner + 5 outer | Common heuristic for recursive bugs. Marker `… N elided …`. |

---

## 8. Open questions

| ID | Question | Tentative |
|---|---|---|
| Q1 | Should the stack hash (sha256 of canonical stack JSON) be stored as a separate column for grouping "records emitted from the same code path"? | Yes — `stack_hash` column, v0.12.1 candidate. Foundation for "find all records from this code path". |
| Q2 | Locals masking: should it also mask values that LOOK like secrets (regex on the repr)? | No — name-based only. Value-based masking has too many false positives. |
| Q3 | Should `/source/<path>:<line>/` allow editing the source from the viewer? | NO. Read-only, forever. |
| Q4 | Stack capture during pytest fixture teardown — captures fixture's stack or test's stack? | The frame at emit time (fixture teardown). Documented. |

---

## 9. References

- [Source: docs/prds/PRD-v0.2-storage-and-ui.md] — detail-view panel pattern
- [Source: docs/prds/PRD-v0.4-commit-author-filter.md] — `--repo` source-line resolution reused
- [Source: docs/prds/PRD-v0.5-forensic-archive.md] — chain hash includes the new column
- [Source: docs/prds/PRD-v0.7-test-execution-stack.md] — span/waterfall is sibling, not duplicate
- [Source: docs/prds/PRD-v0.8.1-docs-syntax-highlight.md] — Prism for `/source/<path>:<line>/`
- [stdlib `traceback.extract_stack`, `linecache`] — chosen primitives
