---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-05-05'
scope: 'drafts v0.3 → v0.5 (v0.1/v0.2/v0.2.1 architecture is substrate, see docs/architecture.md)'
inputDocuments:
  - docs/prds/index.md
  - docs/prds/PRD-v0.1-core.md
  - docs/prds/PRD-v0.2-storage-and-ui.md
  - docs/prds/PRD-v0.2.1-ui-bugfixes.md
  - docs/prds/PRD-v0.3-test-integration.md
  - docs/prds/PRD-v0.4-commit-author-filter.md
  - docs/prds/PRD-v0.5-forensic-archive.md
  - docs/architecture.md
  - docs/project-overview.md
  - docs/component-inventory.md
  - docs/data-models.md
  - docs/api-contracts.md
  - docs/development-guide.md
  - docs/source-tree-analysis.md
  - docs/index.md
  - _bmad-output/project-context.md
workflowType: 'architecture'
project_name: 'ulog-python'
user_name: 'Jojokes'
date: '2026-05-05'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

_Scope of this architecture: drafts v0.3 → v0.5. Shipped versions
(v0.1 / v0.2 / v0.2.1) are out-of-scope for new decisions — their
architecture is captured in `docs/architecture.md` and is treated as
substrate. The seven invariants I1–I7 of PRD-v0.5 §2.4 are
non-negotiable inputs; any decision below that violates one is
invalid by construction._

### Requirements Overview

**Functional Requirements (drafts only):**

- **v0.3 — Test integration (FR51–FR69).** A `ulog.testing.pytest_plugin`
  auto-discovered via `[project.entry-points.pytest11]`, instrumenting
  `pytest_runtest_*` hooks. Pushes `test_id` via `ulog.bind` so
  application records during a test inherit it. UI grows a "Tests"
  sidebar above "Sectors", a detail-view "Test context" panel, and
  three new pytest CLI flags (`--ulog-db`, `--ulog-disable`,
  `--ulog-summary`). Architecturally novel: pytest plugin packaging,
  xdist concurrency on the SQL handler, programmatic `test_event(...)`
  context manager for non-pytest runners.
- **v0.4 — Commit author filter (FR70–FR83).** A startup-time
  `AuthorIndex(repo_root)` walks unique `(file, line)` pairs from
  loaded records, runs `git blame --porcelain` per file (batched via
  `-L`), caches results in a sidecar `authors` table (or
  `<logs>.authors.sqlite` for JSONL/CSV). UI grows an "Authors"
  sidebar section honoring the v0.2.1 ghost-count contract, a
  detail-view "Authored by" panel, and a `/diff/<sha>` endpoint
  (sha-validated, no shell injection). Three new CLI flags (`--repo`,
  `--no-author-index`, `--rebuild-author-index`).
- **v0.5 — Forensic archive (FR90–FR117).** Six architecturally
  novel sub-systems layered on top of v0.4:
  1. **Two-tier storage** — `logs_immutable` + `logs_rotable` with
     SQL trigger blocking UPDATE/DELETE on the immutable side, shared
     `chain_pos` sequence (open question §8.1: column-flag chosen for
     v0.5).
  2. **Hash chain** — `record_hash = sha256(canonical_json + prev_hash)`
     under per-DB `BEGIN IMMEDIATE` lock; `ulog verify`, `ulog repair`,
     UI integrity badge.
  3. **Replay** — `ulog.replay(filter, on=callback)` with
     `is_replaying()` flag; primary driver `ulog.replay_to_pytest()`
     generates a regression test from a real incident.
  4. **Query** — `ulog correlate <filter>` (lift over tag dimensions,
     single `GROUP BY`) and `ulog bisect <pattern>` (binary search
     over chain order).
  5. **Incidents ledger** — `ulog.resolve()` / `ulog.reopen()` emit
     immutable INFO records; `ulog incidents --status` / `--report`
     CLI; UI cross-links + "Incidents" sidebar section.
  6. **Cross-service** — OTel `trace_id` auto-bind from contextvars
     (zero new dep), `ulog trace <id>` CLI, tracker-agnostic
     `issue_template_url` button.
  7. **Multi-track UI minimal** — 4 fixed SVG tracks (level/service/
     author/file) with mute toggle and `(no data)` fallback.

**Non-Functional Requirements driving decisions:**

| NFR | Architectural implication |
|---|---|
| NFR-DEP-50 (= SC4) | `pyproject.toml dependencies = []` regression CI gate. New runtime PyPI deps forbidden — pytest, sqlalchemy, django stay extras; OTel detection via stdlib `contextvars` only; canonical JSON via stdlib `json`. |
| NFR-PERF-50 / 51 | `setup()` ≤ 1 ms; per-log overhead ≤ 1.3× v0.4 baseline. Hash-chain compute (≈5 µs) must NOT happen on the hot record path beyond constant cost. |
| NFR-PERF-52 (= SC1) | `ulog verify` ≤ 5 s / 100 K records → chain walk must be SQL-driven, single pass, indexed `chain_pos`. |
| NFR-PERF-53 (= SC2) | `correlate` ≤ 500 ms / 10 K-filter / 1 M-baseline → single `GROUP BY tag, value` with `COUNT(*) FILTER`; index on `(tag_name, tag_value)` mandatory. |
| NFR-PERF-55 (= SC7) | Multi-track UI ≤ 200 ms TTI / 100 K records / 4 axes / 4 h → SVG (no canvas in v0.5), server-side aggregation per track, payload ≤ a few KB. |
| NFR-PERF-30 / 31 | v0.4 indexer ≤ 5 s / 100 K records / 30-file repo; page-load ≤ 500 ms with author filter active → indexed `authors(file,line)` PK and SQL JOIN, not Python-side merge. |
| NFR-PERF-20 | v0.3 plugin overhead ≤ 5 ms per test → bind + 2-3 batched SQL inserts; no synchronous flushes per test. |
| NFR-REL-50 | Chain integrity under 8-writer × 10 K-record concurrency → `BEGIN IMMEDIATE` per write transaction, validated by `tests/test_chain_concurrency.py`. |
| NFR-REL-51 / 52 | Replay is read-only on chain; `is_replay=True` flag prevents loops. `repair` is idempotent. |
| NFR-COMPAT-10 / 50 | pytest 7.0+ with xdist; mypy --strict green; stdlib logging compat preserved (I5/SC5 byte-stable test stays green). |
| NFR-PORT-10 / 30 / 50 | Linux + macOS + Windows. v0.4: `git` binary on PATH; v0.5 multi-track CLI: locale fallback ASCII (▲▼⚡⊕⚠ → `>>` `<<` `!` `+` `WARN`). |
| NFR-SEC-30 / 50 / 51 | All CLI inputs validated: sha must match `[0-9a-f]{4,64}`; range syntax parsed not eval'd; bisect pattern compiled as Python regex (no shell expansion); issue-template URL placeholders URL-encoded server-side. |
| NFR-DOC-10 / 30 / 50 | Three new in-app doc pages: `/docs/test-integration.md` (v0.3), `/docs/author-filter.md` (v0.4), `/docs/v0.5-forensic-archive.md` (v0.5). |

**Scale & Complexity:**

- Primary technical domain: **Python library + embedded Django web
  viewer + CLI tools.** Single PyPI distribution, multiple optional
  extras gated lazily.
- Complexity level: **medium → high.** v0.3 + v0.4 are extensions of
  the v0.2 foundation (medium). v0.5 is high — four architecturally
  novel sub-systems (hash chain, replay, correlate/bisect, incidents
  ledger) layered on top, plus storage schema evolution.
- Estimated new architectural components (drafts only): **~10–12
  modules / sub-modules.** v0.3 adds `ulog/testing/`; v0.4 adds
  `ulog/web/viewer/blame.py` + `/diff/<sha>` view + sidecar `authors`
  table; v0.5 adds `ulog/_chain.py`, `ulog/replay.py`,
  `ulog/correlate.py`, `ulog/bisect.py`, `ulog/incidents.py`,
  `ulog/_otel.py`, plus `ulog/web/templates/ulog/multi_track.html`
  and integrity-badge / incidents-sidebar template extensions, plus
  the `ulog` CLI multi-subcommand entry point (verify / bisect /
  correlate / incidents / trace / repair / purge).

### Technical Constraints & Dependencies

**Hard freeze (PRD-v0.5 §2.4 invariants):**

- **I1** — no auto-classification; tagging is the app's act.
- **I2 / I3 / I7** — local-first; no network without explicit opt-in;
  no telemetry, no SaaS, no phone-home.
- **I4** — immutable records uncuttable through any path (API, CLI,
  admin, SDK).
- **I5 / I6** — `logging.getLogger(__name__).info(...)` and untagged
  `log.error("oops")` continue to work, forever.

**Inherited substrate (v0.1 / v0.2):**

- Zero PyPI runtime deps in core (`dependencies = []`); every
  optional-dep import (`sqlalchemy`, `django`, `ucolor`) is lazy,
  performed inside the function/handler that needs it.
- Idempotent `setup()` via `_ulog_managed=True` handler tagging.
- `_RESERVED` frozenset triplicated verbatim in `formatters.py`,
  `handlers/sql.py`, `handlers/csv_file.py`. Any new
  extra-merging code path requires a 4th copy.
- Adapter shape: `Record` + `Filters` + `QueryResult` dataclasses
  must remain uniform across SQLite/JSONL/CSV — new fields (test_id,
  author, record_hash, prev_hash, resolves, trace_id) propagate to
  all three adapters or none.
- Ghost-count contract (PRD-v0.2.1): every new sidebar axis (Tests
  v0.3, Authors v0.4, Incidents v0.5) must compute its own counts
  with a where-clause that excludes its own filter.
- No migrations: `SchemaError` is the upgrade-path mechanism. v0.5
  schema additions (chain_pos, record_hash, prev_hash, immutable
  column, authors table) must surface via `SchemaError` with
  actionable messages on drift. Postgres backend deferred to v0.7
  behind a `ChainWriter` abstraction.

**Toolchain:**

- Python `>=3.10`; `from __future__ import annotations` mandatory.
- `mypy --strict` green is a release gate.
- pytest with `testpaths = ["tests"]`; ≥30 new tests in v0.5
  (FR105–FR108 + 8 edge cases of §2.3 each covered); ≥25 in v0.3;
  ≥15 in v0.4.
- `git` binary on PATH required when v0.4's `--repo` is set or
  auto-detected (no GitPython dep — subprocess + porcelain parse).

### Cross-Cutting Concerns Identified

1. **Stdlib `logging` compatibility (I5/I6).** Every new feature must
   cohabit with `logging.getLogger(__name__).info(...)`. Architectural
   touch points: hash chain hook (must be a Handler `emit()` or
   pre-emit interceptor that doesn't break the standard pipeline);
   `bind(test_id=...)` and `_OTEL_TRACE_CONTEXT` propagation must NOT
   require ulog-specific logger calls.

2. **Lazy optional-dep discipline.** Pytest (v0.3), git (v0.4),
   OTel SDK (v0.5) are all detected at runtime via stdlib
   primitives — no top-level imports added to `ulog/__init__.py`.
   Pytest plugin lives in `ulog/testing/` (separate sub-package),
   git is `subprocess` only, OTel reads contextvars without
   importing `opentelemetry.*`.

3. **Bound-context propagation pipeline.** Three features push fields
   onto the same `ulog.context` ContextVar: v0.3 `test_id`, v0.5
   `trace_id`/`span_id`, v0.4 author lookup is read-side only. The
   propagation contract (fresh-dict copy on mutate, unbind on scope
   exit) must hold across pytest's lifecycle, ASGI requests, and
   manual `with ulog.context(...)` blocks.

4. **Storage schema evolution without migrations.** v0.4 adds the
   `authors` sidecar table; v0.5 adds 4 columns + 1 trigger
   (`logs_immutable`/`logs_rotable` decision per §8.1: column-flag
   for v0.5). The `SchemaError` mechanism becomes the user-facing
   upgrade contract for both versions.

5. **Adapter uniformity.** New record fields (`test_id`, `author_*`,
   `record_hash`, `prev_hash`, `resolves`, `trace_id`, `span_id`)
   must extend the `Record` dataclass and be supported by all three
   adapters (SQLite via columns/joins, JSONL/CSV via per-line
   payload). Filters extend likewise.

6. **CLI surface unification.** v0.4 adds `--repo`,
   `--no-author-index`, `--rebuild-author-index` to `ulog-web`. v0.5
   introduces a NEW top-level `ulog` CLI with subcommands (`verify`,
   `bisect`, `correlate`, `incidents`, `trace`, `repair`, `purge`).
   Decision pending: keep two binaries (`ulog-web` + `ulog`) or
   consolidate to `ulog web` / `ulog verify` / etc.

7. **Concurrency model.** Three concurrency surfaces:
   (a) v0.3 xdist parallel pytest workers writing to shared SQLite
   (NFR-PORT-10 fallback to JSONL on NFS); (b) v0.5 multiprocess
   chain writers (NFR-REL-50: 8 writers × 10 K records under
   `BEGIN IMMEDIATE`); (c) Django viewer module-level adapter
   singleton reset between tests. Decision: SQLite WAL mode + per-DB
   write lock for both, JSONL path-of-last-resort for xdist+NFS.

8. **Security boundary on CLI/HTTP inputs.** v0.4 `/diff/<sha>` and
   v0.5 `bisect <pattern>`, `verify --range`, `incidents`, `trace`,
   `purge --before`, `issue_template_url` placeholders all accept
   user input. Hex regex for hashes (`[0-9a-f]{4,64}`), Python regex
   compilation (not shell), URL-encoding of placeholders, no `git`
   args from user data — all enforced at the boundary.

9. **Locale and encoding.** Multi-track CLI output uses UTF-8 glyphs
   (▲▼⚡⊕⚠) with ASCII fallback detected via
   `locale.getpreferredencoding()`. Windows `cmd.exe` and no-locale
   CI runners are first-class targets.

10. **Test → architecture feedback loop.** v0.3 plugin enables
    "every architectural feature gets a `test_event`-shaped
    integration test"; v0.5 `replay_to_pytest` enables "every
    resolved incident becomes a permanent regression test". The
    architecture must NOT make either of these slow or awkward.

## Starter Template Evaluation

**Brownfield project — no starter template applies.** ulog-python is
a hand-rolled stdlib-`logging` extension shipping under setuptools.
Below are the toolchain decisions already locked in by the v0.5
freeze (PRD-v0.5 §2.4) + the regression gate
`grep '^dependencies' pyproject.toml | grep -q '\[\]'`. AI agents
implementing v0.3 → v0.5 MUST respect them.

### Locked-out libraries (forbidden) and their stdlib alternatives

| Concern | Forbidden | Use instead | Reason |
|---|---|---|---|
| CLI parsing | click, typer, fire | `argparse` (stdlib) | NFR-DEP-50 |
| Git interrogation | GitPython, pygit2 | `subprocess.run(['git', 'blame', '--porcelain', ...])` + parse | NFR-DEP-50, FR70 |
| Schema migrations | alembic, yoyo, django-south | `SchemaError` on column drift (v0.2 mechanism) | v0.2 inheritance |
| Markdown rendering | markdown-it-py, mistune, commonmark | `_markdown_to_html` in-house (~60 LOC, `ulog/web/viewer/views.py`) | v0.2 inheritance |
| Canonical JSON / hashing input | msgpack, orjson, ujson, cbor2 | `json.dumps(record, sort_keys=True, separators=(',',':'))` (stdlib) | NFR-DEP-50, FR94 |
| Cryptographic hash | cryptography, hashlib alternatives | `hashlib.sha256` (stdlib) | NFR-DEP-50 |
| OTel SDK | opentelemetry-sdk, opentelemetry-api | Read contextvar `_OTEL_TRACE_CONTEXT` or env `traceparent` directly | NFR-DEP-50, FR109 |
| Django test runner | pytest-django, django-pytest | `django.test.Client` + `django.setup()` (existing v0.2 pattern) | v0.2 inheritance |
| Multi-track visualization | d3.js, plotly, chart.js | Inline SVG in Django template, server-side aggregation | NFR-PERF-55, NFR-DEP-50 |
| Tailwind (production path) | npm + @tailwindcss/cli (Node toolchain) | Tailwind standalone CLI binary → `ulog/web/static/ulog/tailwind.css` (PRD-v0.2 §3.5; current state: CDN script, migration deferred) | offline use, no Node user-side |
| Truecolor in terminal | colorama, blessed, rich | Vendored `ucolor` git submodule + 8-color ANSI fallback | v0.1 freeze |
| Date / time utils | arrow, pendulum | `datetime` + `zoneinfo` (stdlib) | NFR-DEP-50 |
| Concurrency primitives | trio, anyio | `threading` + stdlib lock; `BEGIN IMMEDIATE` at SQL layer for chain | NFR-DEP-50, FR94 |
| Issue-tracker SDKs | linear-sdk, github3.py, jira-python | URL template with placeholders, opened in browser | NFR-DEP-50, FR111 |
| HTTP client (none currently needed) | requests, httpx | `urllib.request` (stdlib) if ever required | NFR-DEP-50, I2 |
| Test parametrization helpers | hypothesis, factory_boy | Plain pytest parametrize + fixtures | NFR-DEP-50 |

### Locked-in toolchain (substrate)

- **Build:** `setuptools >=68.0`, `pyproject.toml` only — no `setup.py` shim. Package discovery: `tool.setuptools.packages.find` with `include = ["ulog*"]` and `exclude` covering `tests*` + `vendor*`.
- **Type-check:** `mypy --strict` (release gate, `tool.mypy.strict = true`).
- **Tests:** `pytest`, `testpaths = ["tests"]`, hermetic per-test SQLite via `tmp_path`. `_isolate_logging` autouse fixture strips `_ulog_managed` handlers post-test.
- **Format / lint:** none enforced — code review only. (No `black` / `ruff` / `flake8` config in repo.)
- **Python version matrix:** 3.10 / 3.11 / 3.12 / 3.13. `from __future__ import annotations` mandatory in every module.
- **Console scripts:** `ulog-web = ulog.web.cli:main` (v0.2). v0.5 adds a second top-level binary `ulog` (verify / bisect / correlate / incidents / trace / repair / purge) — **CLI consolidation decision deferred to step-04** (Cross-Cutting Concern #6).
- **Local launcher:** `run.sh` (subcommands: `setup` / `prod` / `test` / `dev` / `demo` / `clean`) + `Makefile` (`install-dev` / `test` / `mypy` / `check` / `build` / `clean`).
- **Cache layout:** `~/.cache/ulog/<profile>.sqlite`, XDG-aware via `XDG_CACHE_HOME`. Profiles: `prod`, `test`. `auto` → `test` if pytest in charge, else `prod`.
- **Submodule discipline:** `vendor/ucolor-python/` cloned via `git submodule update --init`; library falls back to 8-color ANSI without it. `pip install -e ./vendor/ucolor-python` after recursive clone enables truecolor.
- **Optional extras:** `[dev]` (pytest, mypy), `[storage]` (sqlalchemy>=2.0), `[web]` (django>=5.0, sqlalchemy>=2.0, django-lucide>=1.3).

**Note:** No project-init story is needed (brownfield). v0.3 / v0.4 / v0.5 work continues from the current `main` branch. The first story of each version is the version's primary FR cluster, not bootstrapping.

## Core Architectural Decisions

_Categories recast for the ulog domain (library + embedded viewer + CLI). The default workflow template ("Auth", "Hosting", "Frontend Architecture") is web-app-centric — below it is mapped to: Storage / Concurrency-integrity-validation / Public-API-and-CLI / Viewer-UI / Build-CI-packaging._

### Decision Priority Analysis

**Critical Decisions (block implementation of v0.3 / v0.4 / v0.5):**

- A1 — Storage shape (column-flag vs two-tables)
- A2 — Schema upgrade path v0.4 → v0.5
- A3 — Authors cache shape (v0.4) for JSONL/CSV inputs
- B1 — Hash chain hook mechanism
- B3 — `ChainWriter` abstraction (Postgres v0.7 prep)
- C1 — CLI consolidation (`ulog-web` + `ulog` vs `ulog` unified)
- C2 — Pytest plugin packaging
- D1 — Multi-track UI aggregation strategy
- E2 — CI gate enforcement for `dependencies = []`

**Important Decisions (shape architecture, deferred to step-05 patterns):**

- B2 (concurrency: WAL + `BEGIN IMMEDIATE` vs `BEGIN IMMEDIATE` alone)
- B4 (CLI input validators: centralised vs in-line vs argparse `type=`)
- B5 (`immutable_when()` raise behavior implementation point)
- C3 (`replay()` callback signature shape)
- C4 (`_RESERVED` frozenset 4th copy strategy)
- C5 (`correlate` filter syntax: DSL vs argparse-flat)
- D2 (integrity badge data flow / cache strategy)
- D3 (Tailwind CDN → standalone CLI migration timing)
- D4 (`/diff/<sha>` rendering: raw vs syntax-highlighted vs ANSI→HTML)
- E1 (Python version matrix evolution)
- E3 (benchmark gating: `pytest-benchmark` vs custom timer)
- A4 (`chain_pos` strategy: rowid vs sequence vs reuse `id`)

**Deferred Decisions (out of scope for v0.5, on the post-v0.5 roadmap):**

- Postgres `ChainWriter` impl (v0.7 — interface defined now per B3, impl deferred).
- `--anonymize-authors` flag for blame privacy (v0.5+, see PRD-v0.4 §8.1).
- Mailmap normalization (v0.5+, see PRD-v0.4 §2.2).
- Streaming Merkle-tree verify (v0.7, see PRD-v0.5 §7).
- Multi-DB federation `ulog trace --across` (v0.7).

---

### Storage Architecture

**Decision A1 — Storage shape: column-flag, single table.**

Single `logs` table with new `immutable BOOLEAN NOT NULL DEFAULT 0` column added to the v0.4 schema. SQL trigger blocks `UPDATE`/`DELETE` `WHERE immutable = 1`. Chain walk = single `SELECT ... ORDER BY chain_pos`.

- **Rationale:** Schema diff minimal (1 ALTER TABLE). Chain walk has no UNION. Single trigger logic, easier to test. PRD-v0.5 §8.1 explicitly recommends this for v0.5; two-table physical split deferred to v0.6 if benchmarks demand it. Postgres v0.7 will use partial indexes (`CREATE INDEX ... WHERE immutable = TRUE`) instead of table split.
- **Affects:** v0.5 storage core, all chain operations, trigger DDL.
- **Rejected:** two physical tables `logs_immutable` + `logs_rotable` (YAGNI; UNION cost on every chain walk).

**Decision A2 — Schema upgrade v0.4 → v0.5: `SchemaError` with explicit ALTER TABLE in message.**

Existing v0.2 `SchemaError` mechanism extended for v0.5. Behavior:
- New DBs → `metadata.create_all()` lazy-creates with v0.5 schema.
- Existing v0.4 DBs → `SchemaError` raised on first `emit()`, error message contains the literal `ALTER TABLE logs ADD COLUMN ...` SQL needed (deterministic, copy-paste).
- Existing v0.5 DBs → proceed.

- **Rationale:** Stays consistent with the v0.2 contract ("no auto-migrations"). For a forensic archive, forcing user awareness at the upgrade point is a feature, not a bug. Zero new abstraction.
- **Affects:** `ulog/handlers/sql.py:_verify_or_create_schema`, error message catalog.
- **Rejected:** auto-add-columns at startup (breaks "no migrations" v0.2 contract, torn-state risk on partial failure); `ulog migrate` CLI subcommand (over-engineered for a single ALTER).

**Decision A3 — Authors cache (v0.4) for JSONL/CSV inputs: sidecar `<logs>.authors.sqlite`.**

For `ulog-web` (or v0.5: `ulog web`) on a JSONL/CSV log file, the v0.4 `AuthorIndex` writes to a sidecar SQLite file alongside the source. Schema: `authors(file TEXT, line INTEGER, author_name TEXT, author_email TEXT, commit_sha TEXT, commit_ts INTEGER, PRIMARY KEY (file, line))`.

- **Rationale:** Indexed `(file, line)` PK → matches NFR-PERF-31 (≤500 ms page-load with author filter). SQLAlchemy stack already required when v0.4 author filter is enabled. Embedded-in-record (alternative b) would bloat each record by ~50 bytes × N. JSON sidecar (alternative c) requires loading the entire mapping in memory at startup — fails NFR-PERF-30 on large repos.
- **Affects:** `ulog/web/viewer/blame.py`, JSONL/CSV adapter side, `--rebuild-author-index` flag.

**Decision A4 — `chain_pos` strategy: deferred to step-05 patterns.**

(Marked Important, not Critical: the choice between SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` rowid, dedicated sequence column, or reusing existing `id` is an implementation detail visible at code-write time.)

---

### Concurrency, Integrity & Input Validation

**Decision B1 — Hash chain hook: encapsulated inside the SQL handler, delegated to a `ChainWriter`.**

The chain is a property of the SQL storage path. Hash computation happens at INSERT time, under `BEGIN IMMEDIATE`, inside the `SQLHandler` (or a dedicated `ChainSQLHandler` mode). The handler holds a reference to a `ChainWriter` instance (per B3) which encapsulates `get_last_hash()` + `append(record, ...)`.

JSONL and CSV handlers do **not** participate in the chain; they remain observation surfaces. Records written through them omit `record_hash`/`prev_hash`. The chain walk and `ulog verify` operate exclusively on the SQL backend.

- **Rationale:** `prev_hash` depends on what is *persisted*, not on what is *emitted*. Multi-process concurrency requires a serialization point at the SQL layer; pre-emit hooks (Filter, LogRecordFactory) cannot guarantee this without their own lock. The handler-internal approach makes the lock acquisition (`BEGIN IMMEDIATE`) coextensive with the hash computation. Composes cleanly with stdlib `logging.getLogger(__name__).info(...)` (I5 invariant preserved): records flow through the standard pipeline; the chain is invisible at the user-facing API.
- **Affects:** `ulog/_chain.py` (new), `ulog/handlers/sql.py` (extended), `ulog/setup.py` (new `integrity='hash-chain'` parameter).
- **Rejected:** `logging.Filter` on root logger (cannot serialise multi-process writes); `setLogRecordFactory` global patch (non-disable-able per logger); per-handler hash duplication (divergent post-formatter, multiple handlers compute different hashes for the "same" record).

**Decision B3 — `ChainWriter` abstraction: defined now, SQLite impl in v0.5, Postgres impl in v0.7.**

Tiny interface in `ulog/_chain.py`:

```python
class ChainWriter(Protocol):
    def get_last_hash(self) -> bytes: ...
    def append(self, record: dict, record_hash: bytes, prev_hash: bytes) -> int: ...  # returns chain_pos
```

v0.5 ships `SQLiteChainWriter` (the only impl). v0.7 will add `PostgresChainWriter` using `SELECT ... FOR UPDATE` on a chain-marker row instead of `BEGIN IMMEDIATE`.

- **Rationale:** A rare exception to the "no premature abstraction" rule — interface is minuscule, second impl is on the published roadmap (PRD-v0.5 §7), tests gain immediately (mock `ChainWriter` for unit tests, no SQLite needed). PRD-v0.5 §8.4 explicitly recommends this shape. Couples cleanly with B1.
- **Affects:** `ulog/_chain.py` (interface + SQLite impl), all chain-related tests, future v0.7 backend.
- **Rejected:** skip until v0.7 (chain logic baked into `SQLHandler` would require painful extraction at v0.7 time).

**Decisions B2, B4, B5 — deferred to step-05 patterns.**

(WAL mode toggle, CLI input validator architecture, `immutable_when()` raise handler — implementation patterns rather than core architectural choices.)

---

### Public API & CLI Surface

**Decision C1 — CLI consolidation: single `ulog` binary with subcommands. `ulog-web` removed in v0.5.**

v0.5 ships exactly one console-script entry point: `ulog`. Subcommands:

```
ulog web <path>            (replaces ulog-web)
ulog verify [--range A-B]
ulog repair --confirm
ulog bisect <pattern>
ulog correlate <filter>
ulog incidents [--status …] [--report --since …]
ulog trace <id>
ulog purge --before <date>
```

Migration: `ulog-web` is removed cleanly in v0.5. Release notes call out the rename. Pre-v1.0 = breaking changes are expected.

- **Rationale:** v0.5 is the natural restructure moment per PRD-v0.5 §0 ("the v1.0 freeze contract crystallizes here"). Not consolidating now means freezing two binaries forever at v1.0. Public adopter footprint is small (qlnes per SC6a + ≥1 per SC6b best-effort) — break impact is minimal. Aligned with the "pas de surcouches procédurales" preference (no compat shim, no dual entry-point).
- **Affects:** `pyproject.toml` `[project.scripts]`, `ulog/_cli/__init__.py` (new — argparse subparser dispatcher), all CLI documentation, release notes.
- **Rejected:** keep `ulog-web` + add `ulog` as second binary (permanent legacy gravé in v1.0); dual entry-point with `ulog web` alias (maintenance tax for zero user value).

**Decision C2 — Pytest plugin packaging: sub-package `ulog/testing/`.**

Layout:
```
ulog/testing/
    __init__.py          # exposes test_event(...), TestSession dataclass
    pytest_plugin.py     # pytest_runtest_* hooks, registered via entry-point
```

`pyproject.toml` declares:
```toml
[project.entry-points.pytest11]
ulog = "ulog.testing.pytest_plugin"

[project.optional-dependencies]
testing = ["pytest>=7.0"]
```

- **Rationale:** PRD-v0.3 §5.2 anchors `from ulog.testing import test_event` for the programmatic non-pytest-runner API — namespace required. Pytest auto-discovery via entry-point. Lazy-import-friendly (pytest dep gated to `[testing]` extra; the plugin module imports pytest at top, but it's only loaded by pytest itself). Aligned with the `ulog/handlers/` precedent (sub-package per concern).
- **Affects:** `ulog/testing/` new sub-package, `pyproject.toml` `[project.entry-points.pytest11]` section + `[testing]` extra.
- **Rejected:** top-level `ulog/pytest_plugin.py` (no namespace for `test_event`); separate `ulog-pytest` distribution (heavier ops for a single project).

**Decisions C3, C4, C5 — deferred to step-05 patterns.**

(Replay callback signature, `_RESERVED` frozenset 4th-copy strategy, correlate filter syntax — these are pattern-level choices that are best fixed once with the surrounding code.)

---

### Viewer / UI

**Decision D1 — Multi-track UI: server-side bucket aggregation per track, light JSON payload, client-side SVG.**

Adapters expose a new method `multi_track(filters, tracks: list[str], window_start, window_end, bucket_size_s) -> MultiTrackResult` returning a uniform dataclass:

```python
@dataclass(frozen=True)
class MultiTrackResult:
    tracks: dict[str, list[BucketCount]]  # track name → list of (bucket_start_ts, count_per_value)
    window: tuple[datetime, datetime]
    bucket_size_s: int
```

SQLite impl uses `GROUP BY strftime('%Y-%m-%dT%H:%M', ts), <track>`. JSONL/CSV impls use `collections.Counter` per bucket. Payload size: 4 tracks × 240 buckets × small int = well under 5 KB. Client-side SVG renders from JSON (Django template + ~30 lines of vanilla JS).

- **Rationale:** Hits NFR-PERF-55 (≤200 ms TTI on 100 K records). Preserves the adapter-uniform contract (cross-cutting concern #5). SQL `GROUP BY` is fast; Python `Counter` is acceptable for JSONL/CSV (consistent with their existing in-memory filter strategy). Empty-track fallback returns `[]` for that track key — UI renders the `(no data)` placeholder per PRD-v0.5 §2.1.6.
- **Affects:** `ulog/web/viewer/adapters.py` (new method on each adapter), `ulog/web/viewer/views.py` (new `multi_track_view`), `ulog/web/templates/ulog/multi_track.html` (new), small JS in `ulog/web/static/ulog/multi_track.js`.
- **Rejected:** raw record stream + client-side bucketing (100 K records × JSON × network = bottleneck); SQL-only `strftime` (works for SQLite but breaks the JSONL/CSV adapters).

**Decisions D2, D3, D4 — deferred to step-05 patterns.**

(Integrity badge cache strategy, Tailwind CDN→standalone migration timing, `/diff/<sha>` rendering format — all Important but downstream of D1's adapter work.)

---

### Build, CI & Packaging

**Decision E2 — CI gate `dependencies = []`: shell `grep` in GitHub Actions workflow.**

Add to `.github/workflows/ci.yml`:

```yaml
- name: regression-gate-zero-deps
  run: grep '^dependencies' pyproject.toml | grep -q '\[\]'
```

- **Rationale:** PRD-v0.5 SC4 mentions this exact command verbatim. Zero new dep. Cross-OS (Windows GH Actions runners use bash). Binary check (passes/fails); the `dependencies = []` line is the only place where the regression matters.
- **Affects:** `.github/workflows/ci.yml` (single new step).
- **Rejected:** pre-commit hook (requires the pre-commit framework as a new dev dep); pytest test parsing `pyproject.toml` (requires `tomli` for 3.10 — adds dep for marginal gain over a 1-line grep).

**Decisions E1, E3 — deferred to step-05 patterns.**

(Python version matrix evolution policy, benchmark gating tool selection — both shape CI but not blocking implementation start.)

---

### Decision Impact Analysis

**Implementation Sequence (recommended order across v0.3–v0.5):**

1. **v0.3 first** — `ulog/testing/` sub-package (C2). Lowest blast radius, validates the pytest plugin packaging pattern before v0.4/v0.5 land.
2. **v0.4 next** — `AuthorIndex` + sidecar SQLite (A3) + `/diff/<sha>` view. Composes with v0.3 `test_id` enrichment cleanly.
3. **v0.5 storage core** — A1 (column-flag) + A2 (`SchemaError` upgrade path) + B3 (`ChainWriter` interface + `SQLiteChainWriter` impl). Before any chain-using feature.
4. **v0.5 chain integration** — B1 (`SQLHandler` extended with `ChainWriter` injection + `BEGIN IMMEDIATE` lock).
5. **v0.5 query + ledger** — `correlate`, `bisect`, `incidents` CLI subcommands. All depend on the chain being live.
6. **v0.5 UI** — D1 multi-track adapter method + view + template + tiny JS. Independent of the CLI work; can run in parallel after #4.
7. **v0.5 CLI consolidation** — C1: introduce `ulog` binary with subparsers, port `ulog-web` to `ulog web`, drop `ulog-web` console script. Last because every subcommand from #4-6 lands here.
8. **CI gate** — E2 `grep` step. Anytime; cheap to add early.

**Cross-Component Dependencies:**

- **B3 ⊂ B1** — `SQLHandler` constructs the `ChainWriter` instance. Cannot land B1 without B3.
- **A1 → A2** — column-flag schema choice determines the `ALTER TABLE` SQL emitted by the upgrade `SchemaError`.
- **A3 → C1** — sidecar `<logs>.authors.sqlite` path resolution lives in the `ulog web` subcommand argparse; plumbing depends on the new CLI shape.
- **D1 → adapter contract** — `MultiTrackResult` dataclass extends the uniform adapter contract; touches SQLite/JSONL/CSV impls together (cross-cutting concern #5).
- **C1 → docs + release notes** — every CLI doc page (`/docs/quickstart.md`, `/docs/api.md`, README) needs the `ulog-web` → `ulog web` rename.
- **B1 ↔ I5/I6 invariants** — chain hook sits *below* the user-facing logger API. `logging.getLogger(__name__).info(...)` and untagged `log.error("oops")` keep working unchanged. Verified by SC5 byte-stable test staying green.

**Deferred-decision boomerang risk:** the 12 Important decisions deferred to step-05 patterns can each surface a constraint on these 9 critical choices when implementation starts. If that happens, this document section is amended in place; the cascade above is the canonical reference for re-evaluation order.

## Implementation Patterns & Consistency Rules

_Recast for ulog: Python stdlib-`logging` extension + embedded
Django viewer + CLI. Categories adapted from the workflow template's
web-app default. The 12 "Important" decisions deferred from step-04
are resolved inline below, marked with their decision ID (B2, B4,
B5, C3, C4, C5, D2, D3, D4, E1, E3, A4)._

### Naming patterns

**Python modules:** snake_case. Private helpers prefixed `_` (e.g.
`_color.py`, `_chain.py`, `_filter_dsl.py`, `_cli/`). Sub-packages
get a directory + `__init__.py` (e.g. `ulog/handlers/`,
`ulog/testing/`, `ulog/_cli/`).

**Functions / classes / constants:**
- Functions: `snake_case`. Private with `_` prefix.
- Classes: `PascalCase`. Frozen dataclasses for value types
  (`Record`, `Filters`, `QueryResult`, `MultiTrackResult`,
  `Author`, `BucketCount`).
- Module-level constants: `SCREAMING_SNAKE_CASE` (`LOG_LEVELS`,
  `PROFILES`).

**SQL identifiers:** lowercase snake_case. Tables: `logs`, `authors`.
Indexes: `ix_<table>_<col>` (matches v0.2 — `ix_logs_ts`,
`ix_logs_level`, `ix_logs_logger`, `ix_logs_file`). New v0.5
indexes follow the same: `ix_logs_chain_pos`, `ix_logs_immutable`,
`ix_logs_tag_value`. JSON-extract paths: lowercase keys throughout
(`extras_json -> '$.service'`).

**ContextVar keys:** snake_case, descriptive, never colliding with
stdlib `LogRecord` reserved attrs (see Format patterns below).
Existing: `request_id`, `rom_sha`. v0.3: `test_id`. v0.5:
`trace_id`, `span_id`. App-level keys are caller-defined; ulog
reserves only those it sets itself.

**CLI surface (post-C1 consolidation):**
- Binary: `ulog`. Subcommands: bare verbs (`web`, `verify`, `bisect`,
  `correlate`, `incidents`, `trace`, `purge`, `repair`).
- Long flags: kebab-case (`--ulog-db`, `--no-author-index`,
  `--rebuild-author-index`, `--anonymize-authors` future).
- argparse `dest=`: snake_case (`ulog_db`, `no_author_index`).
- Short flags: only for very common ones (`-q` quiet, `-v` verbose).

**Public API additions:** every new public symbol added in v0.3–v0.5
is **listed in `ulog/__init__.py:__all__`** AND re-exported from
the package root. Internal helpers prefixed `_` and NOT in `__all__`.
The `__all__` list is the contract surface.

### Structure patterns

**Module placement (decision tree for AI agents adding a new file):**
- Optional-dep handler? → `ulog/handlers/<name>.py` (precedent:
  `sql.py`, `json_line.py`, `csv_file.py`).
- New ulog public sub-system with multi-file growth? →
  sub-package `ulog/<name>/` with `__init__.py` (precedent:
  `ulog/handlers/`, future `ulog/testing/`, future `ulog/_cli/`).
- Internal helper, single file? → `ulog/_<name>.py` at the package
  root (precedent: `_color.py`, future `_chain.py`,
  `_filter_dsl.py`, `_reserved.py`).
- Django viewer extension? → under `ulog/web/viewer/` (adapter, view,
  blame index) or `ulog/web/templates/ulog/` (template). NEVER add
  a top-level `ulog/web/foo.py` for viewer code.

**Test placement:** one module per concern under `tests/`. Shape:
`tests/test_<feature>.py`. Each test that touches the SQL handler
uses `tmp_path`. The `_isolate_logging` autouse fixture is
**extended** for v0.3–v0.5 (not duplicated): if a new module needs
extra teardown (e.g. unbind v0.3 `test_id`), add it to the existing
fixture rather than spawning a parallel fixture.

**Lazy-import discipline (locked toolchain → enforcement):**
- Top-level imports in `ulog/__init__.py`, `ulog/setup.py`,
  `ulog/formatters.py`, `ulog/context.py`, `ulog/_color.py` are
  stdlib-only. Period.
- Optional deps (`sqlalchemy`, `django`, `django_lucide`, `ucolor`,
  any v0.5 OTel detection) are imported **inside** the function or
  handler `__init__` that needs them.
- `pytest` may be imported at top level **only** in
  `ulog/testing/pytest_plugin.py` (loaded by pytest itself when
  the `[testing]` extra is installed).
- `git` (subprocess) is invoked from `ulog/web/viewer/blame.py`
  only — never from the core library.

### Format patterns

**Canonical JSON for hashing (B1 / FR94):**
```python
import json
canonical = json.dumps(
    record_dict,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8")
record_hash = hashlib.sha256(canonical + prev_hash).digest()
```
Stable across Python versions. The hash input dict
**EXCLUDES** `chain_pos`, `record_hash`, `prev_hash` (would create
self-reference). Includes: `ts` (ISO-8601 UTC string),
`level`, `logger`, `msg`, `file`, `line`, `exc`, `context`.

**Error messages:** complete English sentences. Include the
actionable item verbatim. Example:
`SchemaError("Existing logs table is missing column 'chain_pos'. Run: ALTER TABLE logs ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0; CREATE INDEX ix_logs_chain_pos ON logs(chain_pos);")`.

**LogRecord reserved attributes — `_RESERVED` frozenset (Decision C4):**
**Centralized in `ulog/_reserved.py`** as part of v0.5. The current
triplication in `formatters.py` / `handlers/sql.py` /
`handlers/csv_file.py` is replaced by `from ulog._reserved import RESERVED`
in each module. Rationale: stdlib adds new attrs over time
(`taskName` 3.12, future ones); single source of truth eliminates
the lockstep-update tax. This is a small, safe refactor that
lands as part of v0.5 storage work — not a separate change.

**Datetime:** UTC, naive (tz-stripped before SQL insert via
`_ts_aware()`). ISO-8601 string in JSONL/CSV (`"2026-05-05T12:34:56Z"`).
Never store local time, never store tz-aware datetimes in the SQL
`ts` column (regression-protected by existing v0.2 tests).

**Boolean in SQL:** `INTEGER DEFAULT 0`, NOT `BOOLEAN`. SQLite has
no native boolean; SQLAlchemy maps `Boolean` → `INTEGER` anyway.
Explicit INTEGER avoids ambiguity in raw SQL DDL strings the
upgrade-path messages emit.

**ANSI / colour:** truecolor via vendored `ucolor` when available
(`_color.color_level`); 8-color ANSI fallback otherwise. Multi-track
CLI glyphs (▲▼⚡⊕⚠) → ASCII fallback (`>>` `<<` `!` `+` `WARN`)
when `locale.getpreferredencoding()` is not UTF-8.

### Process patterns

**Handlers MUST NOT raise (stdlib `logging` contract):** every
`emit()` body wraps work in try/except, calls `self.handleError(record)`
on failure, suppresses with `# noqa: BLE001`. Five existing
swallow points in v0.2 (`setup.py:169`, `handlers/sql.py:129/144/214`,
`handlers/csv_file.py:107`) — v0.5 chain insert and v0.3 plugin emit
add new ones following the same pattern.

**Idempotent `setup()`:** every handler installed gets
`_ulog_managed = True`. Re-`setup()` removes managed handlers
(via `getattr(h, "_ulog_managed", False)`), preserves user-installed
ones. v0.5 chain handler follows the same tag.

**ContextVar mutation pattern:** copy-on-write.
```python
# CORRECT
current = _ctx_var.get()
_ctx_var.set({**current, **new_fields})

# WRONG — mutates shared state, breaks contextvars semantics
current.update(new_fields)
```

**Concurrency (Decision B2):** SQLite WAL mode + `BEGIN IMMEDIATE`
per chain insert. WAL is set once at handler init via
`engine.connect().exec_driver_sql("PRAGMA journal_mode=WAL")`. WAL
lets readers (the `ulog` CLI subcommands, Django viewer)
not block writers. `BEGIN IMMEDIATE` serializes the writers
themselves. Verified by `tests/test_chain_concurrency.py`
(NFR-REL-50: 8 writers × 10 K records).

**CLI input validators (Decision B4):** argparse `type=` callables
for simple inputs (path → `pathlib.Path`, regex → `re.compile`,
hex sha → custom `_hex_sha40`). Multi-step validators
(filter DSL parser, range syntax) live in
`ulog/_cli/_validators.py` and are imported by each subcommand.
**Never** validate in-line in the subcommand body — keeps the
test surface concentrated.

**`immutable_when()` exception handling (Decision B5):** try/except
wraps the predicate call **inside `SQLiteChainWriter.append()`**.
On exception: write to stderr via `print(f"...", file=sys.stderr)`
(NOT via the ulog logger — would recurse). Treat the record as
immutable (fail-safe). Implementation point is the chain writer,
not the user-facing API.

**Replay callback signature (Decision C3):** frozen-dict view via
`types.MappingProxyType`. The callback receives:
```python
def callback(record: Mapping[str, Any]) -> None: ...
```
where `record` is `MappingProxyType` over the record's dict.
Callers cannot mutate (TypeError on `record["foo"] = ...`).
JSON-roundtrip safe. Records flagged `is_replay=True` automatically
during the replay context (per FR99/NFR-REL-51).

**Correlate filter DSL (Decision C5):** small custom grammar,
parsed (NOT `eval`'d), compiled to SQL WHERE clauses. Grammar:

```
filter   := atom (("AND" | "OR") atom)*
atom     := IDENT op (LITERAL | TIME_REL)
op       := "=" | "!=" | ">" | "<" | ">=" | "<=" | "~"  (regex match)
TIME_REL := "-" NUMBER ("min" | "h" | "d" | "w" | "m")
LITERAL  := QUOTED_STRING | NUMBER | "true" | "false"
```

Implementation in `ulog/_filter_dsl.py`. Tokenizer + recursive-descent
parser, < 200 LOC. Compiled to a SQLAlchemy Core expression for the
SQLite adapter; in-Python predicate for JSONL/CSV adapters. **Never
`eval()`** (NFR-SEC-50).

**Integrity badge cache (Decision D2):** sidecar file
`<db>.verify_state.json` next to the SQLite DB:
```json
{
  "verified_up_to_chain_pos": 487234,
  "last_check_ts": "2026-05-05T22:51:00Z",
  "status": "OK",
  "broken_at": null,
  "walk_time_s": 4.3
}
```
UI reads on every page-load (cheap, single file stat + tiny JSON).
"Re-verify" button kicks `ulog verify` in a subprocess (Django view
returns immediately with HTTP 202; the JSON is updated when
done; the next page-load sees the fresh state). No long-poll
needed in v0.5 — user manually refreshes.

**Tailwind production migration (Decision D3):** stay on CDN
through v0.5. Standalone-CLI migration **deferred to v0.6**
(PRD-v0.2 §3.5 already targets v0.6). v0.5 work focuses on the
forensic archive surfaces; touching the CSS toolchain is
unrelated. A `<!-- TODO v0.6: tailwind standalone build -->` comment
in `ulog/web/templates/ulog/base.html` makes this discoverable.

**`/diff/<sha>` rendering (Decision D4):** raw `git show <sha>` output,
HTML-escaped, wrapped in `<pre class="font-mono whitespace-pre
overflow-x-auto">`. **No syntax highlighting** (would require
Pygments — forbidden by NFR-DEP-50). Users with diff-heavy
workflows pipe the URL to their own viewer. The endpoint validates
the sha against `[0-9a-f]{4,40}` before invoking subprocess
(NFR-SEC-30).

**`chain_pos` column strategy (Decision A4):** dedicated `INTEGER NOT NULL`
column with `ix_logs_chain_pos` index. **Not** reusing the existing
`id` (`INTEGER PRIMARY KEY AUTOINCREMENT`) — the chain order must be
distinguishable from the row insertion order in case of future
backfill scenarios. Filled via `chain_pos = (SELECT COALESCE(MAX(chain_pos), 0) FROM logs) + 1`
inside the `BEGIN IMMEDIATE` transaction. Existing v0.4 rows on
upgrade get `chain_pos = id` (deterministic backfill in the upgrade
SQL hint emitted by `SchemaError`).

**Python version matrix (Decision E1):** stay
**3.10 / 3.11 / 3.12 / 3.13** through v0.5. Drop 3.10 only if a
specific feature requires it (none in v0.3–v0.5). Add 3.14
once stable release lands. v1.0 is the natural moment to
re-evaluate the floor.

**Benchmark gating (Decision E3):** `pytest-benchmark` added to
`[dev]` extras. Tests in `tests/bench_*.py` (matches PRD-v0.5
references). CI runs benchmarks **as advisory** (warn on regression,
don't fail) for the first two runs to establish a baseline; gate
hardens once baseline stable. The `[dev]` extra grows by one
package — acceptable since it's not in the runtime contract.

### Enforcement

**All AI agents implementing v0.3–v0.5 MUST:**

1. Add new public symbols to `ulog/__init__.py:__all__` (the
   `__all__` list is the contract surface).
2. Use lazy imports for `sqlalchemy`, `django`, `ucolor`, `git` (subprocess),
   `pytest` (except inside `ulog/testing/pytest_plugin.py`), and
   anything OTel-related.
3. Import `RESERVED` from `ulog/_reserved.py` (single source) when
   merging `record.__dict__` into output payload.
4. Wrap `Handler.emit()` work in try/except, call
   `self.handleError(record)` on failure, suppress with
   `# noqa: BLE001`.
5. Tag handlers installed via `setup()` with `_ulog_managed = True`
   for idempotent re-installation.
6. Use `BEGIN IMMEDIATE` for any chain-related SQL transaction.
   WAL mode set once at engine init.
7. Validate CLI inputs at the argparse `type=` boundary; centralize
   multi-step validators in `ulog/_cli/_validators.py`.
8. Mirror new `Record` / `QueryResult` fields across all three
   adapters (SQLite/JSONL/CSV) — never break adapter uniformity.

**Pattern enforcement mechanisms:**

- `mypy --strict` green (release gate). Catches signature drift,
  missing annotations, optional-`None` mistakes.
- `pytest` (full suite + new `tests/test_<feature>.py` per PRD).
- CI shell-grep `dependencies = []` regression gate (E2).
- Code review checks the lazy-import + `_ulog_managed` discipline
  on diffs that touch `ulog/setup.py` or `ulog/handlers/`.

### Pattern examples

**Good — lazy import inside handler:**
```python
# ulog/handlers/sql.py
class SQLHandler(logging.Handler):
    def __init__(self, url: str | None = None, ...) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._buffer: list[dict[str, Any]] = []
        from sqlalchemy import create_engine, MetaData  # lazy
        self._engine = create_engine(url or _default_url())
```

**Anti-pattern — top-level import breaks zero-deps invariant:**
```python
# ulog/handlers/sql.py — DO NOT DO THIS
from sqlalchemy import create_engine  # breaks `import ulog` for
                                      # users without the [storage] extra
```

**Good — frozen-dict callback signature for replay:**
```python
import types
def _make_view(record_dict: dict[str, Any]) -> Mapping[str, Any]:
    return types.MappingProxyType(record_dict)

for record_dict in chain_walk():
    callback(_make_view(record_dict))  # callback can read, can't mutate
```

**Anti-pattern — passing a mutable dict:**
```python
# DO NOT — callback could mutate and break replay determinism
for record_dict in chain_walk():
    callback(record_dict)
```

**Good — validator at argparse boundary:**
```python
# ulog/_cli/_validators.py
def hex_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{4,40}", value):
        raise argparse.ArgumentTypeError(f"not a valid sha: {value!r}")
    return value

# subcommand
parser.add_argument("sha", type=hex_sha)
```

**Anti-pattern — in-line validation inside subcommand body:**
```python
# DO NOT — pushes validation past argparse, harder to test
def cmd_diff(args):
    if not re.fullmatch(r"[0-9a-f]{4,40}", args.sha):
        print("invalid sha"); sys.exit(2)
```

**Good — `_ulog_managed` cleanup in `setup()`:**
```python
for h in list(logger.handlers):
    if getattr(h, "_ulog_managed", False):
        h.close()
        logger.removeHandler(h)
# ... build new handler ...
new_handler._ulog_managed = True
logger.addHandler(new_handler)
```

**Anti-pattern — wholesale `handlers.clear()`:**
```python
logger.handlers.clear()  # destroys user-installed handlers — breaks FR2
```

## Project Structure & Boundaries

_Concrete tree post-v0.5 release. NEW files marked `[+v0.3]` /
`[+v0.4]` / `[+v0.5]`; extended files marked `[ext vN.N]`. Absent
markers = unchanged from v0.2._

### Complete project directory structure (post-v0.5)

```
ulog-python/
├── pyproject.toml                          [ext v0.3/v0.4/v0.5]
│                                             - new [testing] extra (pytest>=7.0)
│                                             - [project.entry-points.pytest11]
│                                             - [project.scripts] = { ulog = "ulog._cli:main" }
│                                             - removed: ulog-web entry (folded into `ulog web`)
│                                             - [dev] adds pytest-benchmark
├── Makefile
├── run.sh                                   [ext v0.5] — new `ulog` subcommand alias
├── README.md                                [ext v0.5] — CLI rename + chain quick-tour
├── LICENSE
├── uv.lock
├── BENCHMARK.md                             [+v0.5] — NFR-PERF-* baselines
├── STABILITY.md                             [+v0.5] — the 7 invariants doc (DOD)
├── OUTREACH.md                              [+v0.5] — SC6b adopter tracking
│
├── .github/workflows/ci.yml                 [ext v0.5] — `dependencies = []` grep gate (E2)
│
├── ulog/                                    # zero PyPI runtime deps — INVIOLATE
│   ├── __init__.py                          [ext v0.3/v0.4/v0.5]
│   │                                          __all__ extended:
│   │                                          v0.5: verify, replay, replay_to_pytest,
│   │                                                correlate, bisect, resolve, reopen,
│   │                                                trace, purge, default_chain_path
│   ├── setup.py                             [ext v0.5]
│   │                                          new params: integrity, immutable_when,
│   │                                                      min_retention_days,
│   │                                                      issue_template_url
│   ├── formatters.py                        [ext v0.5] — imports RESERVED from _reserved.py
│   ├── context.py                           # unchanged
│   ├── _color.py                            # unchanged
│   ├── _reserved.py                         [+v0.5] — single source of RESERVED frozenset (C4)
│   ├── _chain.py                            [+v0.5] — ChainWriter Protocol + SQLiteChainWriter (B1, B3)
│   ├── replay.py                            [+v0.5] — replay() + replay_to_pytest() (FR98-100, C3)
│   ├── correlate.py                         [+v0.5] — correlate() (FR101-102, FR104)
│   ├── bisect.py                            [+v0.5] — bisect() (FR103-104)
│   ├── incidents.py                         [+v0.5] — resolve() / reopen() / list (FR105-108)
│   ├── _filter_dsl.py                       [+v0.5] — DSL parser (C5, NFR-SEC-50)
│   │
│   ├── handlers/
│   │   ├── __init__.py                      [ext v0.5] — re-exports chain-aware SQLHandler
│   │   ├── sql.py                           [ext v0.5]
│   │   │                                      injects ChainWriter when integrity='hash-chain'
│   │   │                                      adds immutable column + chain_pos to schema
│   │   │                                      BEGIN IMMEDIATE on chain inserts (B1, B2)
│   │   ├── json_line.py                     # unchanged (no chain participation)
│   │   └── csv_file.py                      [ext v0.5] — imports RESERVED from _reserved.py
│   │
│   ├── testing/                             [+v0.3 sub-package]
│   │   ├── __init__.py                      — exposes test_event(), TestSession, replay_records (FR100)
│   │   └── pytest_plugin.py                 — pytest_runtest_* hooks (FR51-69)
│   │
│   ├── _cli/                                [+v0.5 sub-package]
│   │   ├── __init__.py                      — main(): argparse subparser dispatcher (C1)
│   │   ├── _validators.py                   — hex_sha, range_spec, since_relative, filter_compile (B4)
│   │   ├── cmd_web.py                       — `ulog web <path>` (replaces ulog-web)
│   │   ├── cmd_verify.py                    — `ulog verify [--range A-B]` (FR95)
│   │   ├── cmd_repair.py                    — `ulog repair --confirm` (FR97)
│   │   ├── cmd_bisect.py                    — `ulog bisect <pattern>` (FR103)
│   │   ├── cmd_correlate.py                 — `ulog correlate <filter>` (FR101)
│   │   ├── cmd_incidents.py                 — `ulog incidents [--status …] [--report]` (FR107-108)
│   │   ├── cmd_trace.py                     — `ulog trace <id>` (FR110)
│   │   └── cmd_purge.py                     — `ulog purge --before <date>` (FR93)
│   │
│   └── web/
│       ├── __init__.py
│       ├── cli.py                           # KEPT as WSGI runner (called from _cli/cmd_web.py)
│       │                                      console_script entry REMOVED in v0.5 (C1)
│       ├── settings.py
│       ├── urls.py                          [ext v0.4/v0.5]
│       │                                      new routes: /diff/<sha>, /multi-track,
│       │                                                  /api/integrity, /api/incidents/
│       ├── docs/
│       │   ├── quickstart.md                [ext v0.5] — FR117 mention new APIs
│       │   ├── storage.md                   [ext v0.5]
│       │   ├── api.md                       [ext v0.5]
│       │   ├── troubleshooting.md           [ext v0.5]
│       │   ├── sectors-and-files.md         # unchanged
│       │   ├── test-integration.md          [+v0.3] (NFR-DOC-10)
│       │   ├── author-filter.md             [+v0.4] (NFR-DOC-30)
│       │   └── v0.5-forensic-archive.md     [+v0.5] (FR116, NFR-DOC-50)
│       ├── templates/ulog/
│       │   ├── base.html                    [ext v0.5] — integrity badge in header (FR113)
│       │   ├── list.html                    [ext v0.3/v0.4/v0.5]
│       │   │                                  Tests sidebar (FR62), Authors (FR76),
│       │   │                                  Incidents (FR115), multi-track strip (FR112)
│       │   ├── detail.html                  [ext v0.3/v0.4/v0.5]
│       │   │                                  Test context (FR66), Authored by (FR80),
│       │   │                                  Resolves cross-link (FR114), Issue button (FR111)
│       │   ├── docs_index.html
│       │   ├── docs_page.html
│       │   ├── multi_track.html             [+v0.5] — SVG strip template (FR112)
│       │   └── diff.html                    [+v0.4] — escaped pre-block (FR81, D4)
│       ├── static/ulog/
│       │   ├── multi_track.js               [+v0.5] — ~30 LOC vanilla JS for SVG render
│       │   └── (tailwind.css)               # TODO v0.6 — D3 standalone CLI build
│       └── viewer/
│           ├── __init__.py
│           ├── apps.py
│           ├── views.py                     [ext v0.3/v0.4/v0.5]
│           │                                  multi_track_view, integrity_view,
│           │                                  diff_view, incidents_view, all chain queries
│           ├── adapters.py                  [ext v0.3/v0.4/v0.5]
│           │                                  Record extended (test_id, author_*, record_hash,
│           │                                                   prev_hash, resolves, trace_id),
│           │                                  multi_track() method (D1),
│           │                                  ghost counts on Tests/Authors/Incidents axes
│           └── blame.py                     [+v0.4] — AuthorIndex (FR70-75, A3)
│
├── tests/
│   ├── __init__.py
│   ├── test_setup.py                        [ext v0.5] — integrity, min_retention_days
│   ├── test_formatters.py
│   ├── test_context.py
│   ├── test_handlers.py
│   ├── test_web.py                          [ext v0.5]
│   ├── test_qlnes_compat.py                 [+v0.5] — SC5/I5 byte-stable regression gate
│   ├── test_chain.py                        [+v0.5] — ChainWriter unit + integration
│   ├── test_chain_concurrency.py            [+v0.5] — NFR-REL-50 (8 writers × 10K)
│   ├── test_verify.py                       [+v0.5] — verify CLI + repair (FR95-97)
│   ├── test_replay.py                       [+v0.5] — FR98-100, NFR-REL-51
│   ├── test_correlate.py                    [+v0.5] — FR101-102 + sample-size warnings
│   ├── test_bisect.py                       [+v0.5] — FR103
│   ├── test_incidents.py                    [+v0.5] — FR105-108 + 8 edge cases of §2.3
│   ├── test_otel.py                         [+v0.5] — auto-bind from contextvars (FR109)
│   ├── test_filter_dsl.py                   [+v0.5] — DSL parser + injection refusal
│   ├── test_pytest_plugin.py                [+v0.3] — uses pytester fixture (FR54-69)
│   ├── test_test_event.py                   [+v0.3] — programmatic API (PRD-v0.3 §5.2)
│   ├── test_author_index.py                 [+v0.4] — AuthorIndex + 4 edge cases (PRD-v0.4 §2.3)
│   ├── test_diff_view.py                    [+v0.4] — /diff/<sha> validation
│   ├── bench_log.py                         [+v0.5] — NFR-PERF-51
│   ├── bench_verify.py                      [+v0.5] — NFR-PERF-52 / SC1
│   ├── bench_correlate.py                   [+v0.5] — NFR-PERF-53 / SC2
│   ├── bench_multitrack.py                  [+v0.5] — NFR-PERF-55 / SC7
│   └── coverage_matrix.md                   [+v0.5] — FR ↔ test mapping (SC3)
│
├── docs/                                    # brownfield documentation (DP-generated)
│   ├── index.md
│   ├── project-overview.md
│   ├── architecture.md                      # original brownfield arch — kept as substrate
│   ├── source-tree-analysis.md
│   ├── development-guide.md
│   ├── data-models.md
│   ├── api-contracts.md
│   ├── component-inventory.md
│   ├── project-scan-report.json
│   └── prds/
│       ├── index.md
│       ├── PRD-v0.1-core.md
│       ├── PRD-v0.2-storage-and-ui.md
│       ├── PRD-v0.2.1-ui-bugfixes.md
│       ├── PRD-v0.3-test-integration.md
│       ├── PRD-v0.4-commit-author-filter.md
│       ├── PRD-v0.5-forensic-archive.md
│       └── validation/
│
├── vendor/
│   └── ucolor-python/                       # git submodule
│
├── _bmad/
└── _bmad-output/
    ├── brainstorming/
    ├── planning-artifacts/
    │   └── architecture.md                  # THIS document
    ├── implementation-artifacts/
    └── project-context.md
```

### Architectural boundaries

**Public Python API (frozen contract per I5/I6 + PRD-v0.5 §2.4):**
- Exposed via `ulog/__init__.py:__all__`. Adding a name = adding to the contract surface.
- v0.5 additions: `verify`, `replay`, `replay_to_pytest`, `correlate`, `bisect`, `resolve`, `reopen`, `trace`, `purge`, `is_replaying`, `default_chain_path`.
- v0.4 additions: none at the package root (the `AuthorIndex` lives at `ulog.web.viewer.blame.AuthorIndex` — viewer-internal, not core).
- v0.3 additions: `ulog.testing.test_event`, `ulog.testing.replay_records`, `ulog.testing.TestSession`. Pytest plugin is loaded by pytest, not imported manually.

**HTTP API (Django viewer):**
- Existing v0.2 routes: `/`, `/r/<id>/`, `/api/records/`, `/docs/`, `/docs/<slug>/`, `/favicon.ico`.
- v0.4 additions: `GET /diff/<sha>`.
- v0.5 additions: `GET /multi-track` (page), `GET /api/integrity`, `GET /api/multi-track-buckets`, `POST /api/verify-trigger` (returns 202), `GET /api/incidents/`.

**CLI surface (post-C1 consolidation):**
- One binary: `ulog`. Subcommand resolution in `ulog/_cli/__init__.py:main()`.
- Each subcommand is a self-contained module under `ulog/_cli/cmd_*.py` with one `register(subparsers)` and one `run(args)` function. Pattern enforced by `ulog/_cli/__init__.py` discovery loop.

**Storage boundary:**
- SQL (SQLite via SQLAlchemy) is the canonical chain-bearing store. `logs` table extended with `chain_pos`, `record_hash`, `prev_hash`, `immutable`. Sidecar `<db>.verify_state.json` for the integrity badge cache (D2). Sidecar `<logs>.authors.sqlite` for v0.4 author index when source is JSONL/CSV (A3).
- JSONL / CSV are observation surfaces only — they emit records without `record_hash`/`prev_hash`. Adapters read them but cannot verify chain integrity.

### Requirements → structure mapping

| Requirement / Epic | Files / Directories |
|---|---|
| **PRD-v0.3 §3.1 — Plugin auto-discovery (FR51-53)** | `pyproject.toml [project.entry-points.pytest11]`, `ulog/testing/pytest_plugin.py` |
| **PRD-v0.3 §3.2 — Test event recording (FR54-58)** | `ulog/testing/pytest_plugin.py` (hooks), `ulog/testing/__init__.py:test_event()` |
| **PRD-v0.3 §3.3 — Bound-context propagation (FR59-61)** | `ulog/testing/pytest_plugin.py` (uses `ulog.context.bind/unbind`), `ulog/context.py` (existing) |
| **PRD-v0.3 §3.4 — UI rendering (FR62-66)** | `ulog/web/templates/ulog/list.html` (Tests sidebar), `detail.html` (Test context), `ulog/web/viewer/views.py`, `adapters.py` |
| **PRD-v0.3 §3.5 — CLI flags (FR67-69)** | `ulog/testing/pytest_plugin.py` (pytest hooks `pytest_addoption`) |
| **PRD-v0.4 §3.1 — Indexer (FR70-75)** | `ulog/web/viewer/blame.py:AuthorIndex`, sidecar `<logs>.authors.sqlite` (A3) |
| **PRD-v0.4 §3.2 — Sidebar UI (FR76-79)** | `ulog/web/templates/ulog/list.html` (Authors section), `ulog/web/viewer/views.py`, `adapters.py` (ghost counts) |
| **PRD-v0.4 §3.3 — Detail panel + /diff (FR80-81)** | `ulog/web/templates/ulog/detail.html`, `diff.html`, `ulog/web/viewer/views.py:diff_view`, `ulog/web/urls.py` |
| **PRD-v0.5 §3.1 — Storage & immutability (FR90-93)** | `ulog/handlers/sql.py` (extended schema + trigger), `ulog/setup.py` (immutable_when, min_retention_days), `ulog/_cli/cmd_purge.py` |
| **PRD-v0.5 §3.2 — Hash chain (FR94-97)** | `ulog/_chain.py` (ChainWriter), `ulog/handlers/sql.py` (integration), `ulog/_cli/cmd_verify.py`, `cmd_repair.py`, `ulog/web/viewer/views.py:integrity_view` |
| **PRD-v0.5 §3.3 — Replay (FR98-100)** | `ulog/replay.py`, `ulog/testing/__init__.py:replay_records` |
| **PRD-v0.5 §3.4 — Query (FR101-104)** | `ulog/correlate.py`, `ulog/bisect.py`, `ulog/_filter_dsl.py`, `ulog/_cli/cmd_correlate.py`, `cmd_bisect.py` |
| **PRD-v0.5 §3.5 — Incidents ledger (FR105-108)** | `ulog/incidents.py`, `ulog/_cli/cmd_incidents.py`, `ulog/web/templates/ulog/list.html` (Incidents sidebar), `detail.html` (Resolves panel) |
| **PRD-v0.5 §3.6 — Cross-service (FR109-111)** | `ulog/setup.py` (OTel context detection — stdlib contextvars only), `ulog/_cli/cmd_trace.py`, issue-template-URL plumbing in `ulog/web/templates/ulog/detail.html` |
| **PRD-v0.5 §3.7 — UI extensions (FR112-115)** | `ulog/web/templates/ulog/multi_track.html`, `static/ulog/multi_track.js`, integrity badge in `base.html`, Resolves cross-links in `detail.html`, Incidents section in `list.html` |
| **PRD-v0.5 §3.8 — Documentation (FR116-117)** | `ulog/web/docs/v0.5-forensic-archive.md` (new), `quickstart.md` / `storage.md` / `api.md` / `troubleshooting.md` (touched), `STABILITY.md`, `BENCHMARK.md` |

### Cross-cutting concerns → locations

| Concern | Location |
|---|---|
| Lazy-import discipline | enforced in `ulog/__init__.py`, `setup.py`, `formatters.py`, `context.py`, `_color.py` (stdlib-only at top); deferred imports inside handlers and CLI subcommands |
| `_RESERVED` frozenset (single source) | `ulog/_reserved.py` (C4) — imported by `formatters.py`, `handlers/sql.py`, `handlers/csv_file.py` |
| `_ulog_managed` flag discipline | enforced in `ulog/setup.py:_install_handlers` and on every new handler installation in v0.5 |
| ContextVar copy-on-write | enforced in `ulog/context.py` (existing); new keys (test_id, trace_id, span_id) follow the same pattern |
| BEGIN IMMEDIATE concurrency (B2) | `ulog/_chain.py:SQLiteChainWriter.append`, `ulog/handlers/sql.py:SQLHandler.flush` (chain mode) |
| CLI input validation (B4) | `ulog/_cli/_validators.py` (centralized helpers); each `cmd_*.py` uses argparse `type=` callables |
| Adapter uniformity | `ulog/web/viewer/adapters.py` — Record/Filters/QueryResult/MultiTrackResult dataclasses extended atomically across SQLite/JSONL/CSV impls |
| Ghost-counts contract (PRD-v0.2.1) | adapters compute new axis counts (Tests/Authors/Incidents) with all-filters-EXCEPT-this-axis |
| Locale fallback | `ulog/_cli/cmd_correlate.py` glyph table; `ulog/_cli/__init__.py` checks `locale.getpreferredencoding()` once at boot |

### Integration points & data flow

**Write path (chain integration):**
```
user code: log.error("boom", extra={...})
    ↓ stdlib logging
logging.Logger (root, _ulog_managed handlers attached)
    ↓ emit
SQLHandler (chain mode)
    ↓ batches
SQLiteChainWriter.append(record_dict, hash, prev_hash)
    ↓ BEGIN IMMEDIATE
SQLite logs table (chain_pos, record_hash, prev_hash columns)
```

**Read path (viewer):**
```
HTTP GET / or /api/records/
    ↓ Django view
Adapter.query(filters, page) → QueryResult (with ghost counts)
    ↓ template render
list.html (sidebar sections + records table + multi-track strip)
```

**Read path (CLI):**
```
$ ulog verify
    ↓ ulog/_cli/cmd_verify.py
SQLiteChainWriter walk → reports OK / BROKEN at #N
    ↓ writes
<db>.verify_state.json (consumed by web integrity badge)
```

**Cross-service (OTel):**
```
external trace context (env traceparent OR contextvar _OTEL_TRACE_CONTEXT)
    ↓ ulog/setup.py:_otel_bind() (stdlib contextvars read only)
record's context dict gets trace_id, span_id
    ↓ all handlers see the enriched record
SQL chain stores trace_id; `ulog trace <id>` walks records by trace_id
```

### Development workflow integration

- **Build:** `make build` → `python -m build` (setuptools); produces `dist/ulog-X.Y.Z-py3-none-any.whl` and sdist.
- **Test:** `make test` → `pytest` (testpaths = ["tests"]). Bench files (`tests/bench_*.py`) need explicit invocation: `pytest tests/bench_*.py --benchmark-only`.
- **Type-check:** `make mypy` → `mypy --strict ulog`.
- **Local viewer dev:** `./run.sh dev <path>` (existing) or `ulog web <path> --reload` (post-v0.5).
- **CLI quick-test (post-v0.5):** `ulog --help` lists all subcommands. Each subcommand is independently testable (`tests/test_<cmd>.py`).

**Deployment:** ulog is a library — "deployment" = PyPI publish (`twine upload dist/*`). The Django viewer ships *with* the lib, runs locally on user demand. Not a SaaS (I2/I3/I7).

## Architecture Validation Results

### Coherence Validation ✅

**Decision compatibility:** the 9 critical decisions of step-04 form
an internally consistent set. The cascade map (B3 ⊂ B1, A1 → A2,
A3 → C1, D1 → adapter contract, B1 ↔ I5/I6) was traced explicitly
and no contradictions surfaced. The 7 frozen invariants (I1–I7) of
PRD-v0.5 §2.4 are honored by every decision: I1 (no auto-class)
preserved by `tag = app's act`; I2/I3/I7 (local-first) preserved by
zero-network OTel detection (read contextvars only) and offline
`ulog verify`; I4 (immutable hard) enforced by SQL trigger + chain
hash; I5/I6 (stdlib-`logging` compat) preserved by handler-internal
chain hook (B1) which keeps `logging.getLogger(__name__).info(...)`
unchanged.

**Pattern consistency:** the step-05 patterns (canonical JSON,
`_RESERVED` centralization, lazy imports, `_ulog_managed` discipline,
copy-on-write contextvars, `BEGIN IMMEDIATE` concurrency) all align
with the v0.2 substrate. No pattern requires breaking an existing
v0.1/v0.2 contract. The new `_RESERVED` centralization (C4) is a
strict improvement (eliminates the lockstep-update tax) without
behavior change.

**Structure alignment:** the post-v0.5 tree (step-06) preserves the
existing `ulog/handlers/` and `ulog/web/viewer/` layout. New
sub-packages (`ulog/testing/`, `ulog/_cli/`) follow the same shape.
No top-level monolithic modules. Test layout extends `tests/test_*.py`
without restructuring.

### Requirements Coverage Validation ✅

**Functional requirements (FR51 → FR117) — full coverage:**

| FR cluster | PRD | Architectural support |
|---|---|---|
| FR51-53 plugin discovery | v0.3 §3.1 | `pyproject.toml` entry-point + `ulog/testing/pytest_plugin.py` |
| FR54-58 test event recording | v0.3 §3.2 | `pytest_plugin.py` hooks + `ulog.context.bind(test_id=...)` |
| FR59-61 bound-context propagation | v0.3 §3.3 | reuse of existing v0.1 `ulog/context.py` (no change needed) |
| FR62-66 UI Tests sidebar + detail panel | v0.3 §3.4 | `list.html` / `detail.html` extensions + `adapters.py` ghost counts |
| FR67-69 pytest CLI flags | v0.3 §3.5 | `pytest_addoption` in `pytest_plugin.py` |
| FR70-75 author indexer | v0.4 §3.1 | `ulog/web/viewer/blame.py:AuthorIndex` + sidecar SQLite (A3) |
| FR76-79 author sidebar UI | v0.4 §3.2 | `list.html` Authors section + ghost-count contract extended |
| FR80-81 detail panel + /diff | v0.4 §3.3 | `detail.html` Authored-by panel + `diff_view` + `diff.html` (D4 escaped pre-block) |
| FR82-83 indexer perf | v0.4 §3.4 | `(file, line)` PK index + per-file batched `git blame -L` |
| FR90-93 storage & retention | v0.5 §3.1 | A1 column-flag + A2 SchemaError upgrade + `ulog purge` (FR93) |
| FR94-97 hash chain & verify | v0.5 §3.2 | `_chain.py:SQLiteChainWriter` (B1+B3) + `cmd_verify.py` + `cmd_repair.py` + integrity badge cache (D2) |
| FR98-100 replay | v0.5 §3.3 | `replay.py` + `MappingProxyType` callback (C3) + `replay_records` in `ulog/testing/` |
| FR101-104 query | v0.5 §3.4 | `correlate.py` + `bisect.py` + `_filter_dsl.py` (C5) + CLI subcommands |
| FR105-108 incidents ledger | v0.5 §3.5 | `incidents.py` + `cmd_incidents.py` + UI Incidents section |
| FR109-110 OTel cross-service | v0.5 §3.6 | contextvar read in `setup.py` (zero new dep) + `cmd_trace.py` |
| FR111 issue button | v0.5 §3.6 | URL template plumbing in `detail.html` + URL-encode pass server-side (NFR-SEC-51) |
| FR112-115 UI extensions | v0.5 §3.7 | multi_track template + JS + integrity badge in base.html + Resolves cross-links |
| FR116-117 documentation | v0.5 §3.8 | new doc pages in `ulog/web/docs/` + STABILITY.md + BENCHMARK.md |

**Non-functional requirements — full coverage with measurement
points:**

- NFR-DEP-50 `dependencies = []` → E2 grep gate in `.github/workflows/ci.yml`
- NFR-PERF-50/51 setup + per-log overhead → `bench_log.py`
- NFR-PERF-52/SC1 verify ≤5s/100K → `bench_verify.py`
- NFR-PERF-53/SC2 correlate ≤500ms → `bench_correlate.py`
- NFR-PERF-55/SC7 multi-track ≤200ms → `bench_multitrack.py`
- NFR-PERF-30/31 v0.4 indexer + page-load → indexed `(file, line)` PK + SQL JOIN
- NFR-PERF-20 v0.3 plugin overhead → batched SQL inserts via existing buffer
- NFR-REL-50 chain concurrency → `test_chain_concurrency.py` (8 writers × 10K)
- NFR-REL-51/52 replay read-only + repair idempotent → `test_replay.py`, `test_verify.py`
- NFR-COMPAT-10/50 pytest 7.0+ + mypy --strict + I5/SC5 byte-stable → existing CI gates
- NFR-PORT-* Linux/macOS/Windows → `git` PATH check + locale fallback
- NFR-SEC-30/50/51 input validation → `_cli/_validators.py` + DSL parser (no eval) + URL-encode
- NFR-DOC-* three new doc pages → `ulog/web/docs/{test-integration,author-filter,v0.5-forensic-archive}.md`

**Frozen invariants (I1–I7) — preservation verified:**

- I1 (no auto-class): no decision introduces auto-classification logic.
- I2/I3/I7 (local-first / no SaaS / no telemetry): all `ulog verify`, `ulog correlate`, etc. run against local SQLite. OTel auto-bind reads existing contextvars, opens no socket.
- I4 (immutable hard): SQL trigger blocks UPDATE/DELETE on `WHERE immutable=1`; `ulog repair` archives orphans, never deletes.
- I5/I6 (stdlib compat): handler-internal chain hook (B1(d)) + zero changes to `ulog.get_logger` API.

### Implementation Readiness Validation ✅

- **Decision completeness:** all 9 critical (step-04) + all 12 important (step-05 patterns) documented with rationale and affects-list.
- **Structure completeness:** 100% of new files mapped to a directory with file-level annotation in step-06.
- **Pattern completeness:** naming/structure/format/process patterns + 5 good/anti-pattern code examples + 8 enforcement rules.

### Gap Analysis

**Critical gaps:** none.

**Important gaps (must be resolved during the first v0.5 sprint, before chain code freezes):**

| Gap | Description | Proposed resolution |
|---|---|---|
| **G1** | Pre-chain records on v0.4→v0.5 upgrade have no `record_hash`/`prev_hash`. The first NEW chain record's `prev_hash` is ambiguous: zero (`b"\x00"*32`) or `sha256(last_pre_chain_record)`? | **Resolution:** backfilled records get `chain_pos = id` (per A4) with NULL `record_hash`/`prev_hash`. The first NEW chain record uses `prev_hash = b"\x00"*32`, **starting a fresh chain**. `ulog verify` only walks records with non-NULL hash. The upgrade-path `SchemaError` message documents this discontinuity explicitly. Add `tests/test_v04_to_v05_upgrade.py`. |
| **G2** | `is_replay=True` flag storage point not specified | **Resolution:** new contextvar `_REPLAY_ACTIVE: ContextVar[bool]` in `ulog/replay.py`. Set inside `replay()` context manager. `ulog.is_replaying()` reads it. Records emitted with this var True are stamped `is_replay=True` by the SQL handler at insert time. |
| **G3** | `issue_template_url` `{body}` semantics: which 5 surrounding records (before / after / symmetric)? | **Resolution:** symmetric window — 2 before + 2 after the target record by `chain_pos`. JSON list of MappingProxyType views. Documented in `ulog/web/docs/v0.5-forensic-archive.md` worked example for FR111. |
| **G4** | OTel detection covers OTel SDK only; users with native Jaeger/Zipkin clients get no auto-bind | **Resolution:** documented as non-goal (FR109 explicitly targets OTel `_OTEL_TRACE_CONTEXT` contextvar + `traceparent` env). Other tracers can still bind manually via `ulog.bind(trace_id=...)`. Note added to `troubleshooting.md`. |
| **G5** | `replay_to_pytest` generated test fixture: import path + fixture API not locked | **Resolution:** generated test imports `from ulog.testing import replay_records` (a context manager). Stable signature: `replay_records(records: Sequence[Mapping]) -> ReplaySession`. Locked in v0.5 release notes; touches I5 stability. |
| **G6** | `ulog-web` removal in v0.5 needs a clear user-facing transition message | **Resolution:** remove the `ulog-web` console_script entry; ship a `ulog-web` shell stub via `pyproject.toml` post-install hint OR rely on `command not found` + RELEASE_NOTES.md prominent entry. **Pick:** RELEASE_NOTES.md prominent entry (post-install hint adds complexity for marginal UX gain). |
| **G7** | `ulog correlate` filter DSL: precedence of AND vs OR | **Resolution:** AND binds tighter than OR (standard precedence). Parentheses supported for explicit grouping. Documented in `_filter_dsl.py` docstring + `correlate.md` doc page. |
| **G8** | Chain integrity behavior on `min_retention_days` purge of pre-chain records | **Resolution:** `ulog purge --before <date>` only operates on `logs_rotable`-equivalent records (immutable=0). Pre-chain backfilled records (NULL record_hash) are treated as rotable by default. Behavior locked in `ulog/_cli/cmd_purge.py` test cases. |

**Nice-to-have (post-v0.5):**

- Streaming Merkle-tree verify (PRD-v0.5 §7, v0.7).
- Replay subprocess isolation (run callback in fresh interpreter for fuzz scenarios).
- `--anonymize-authors` flag (PRD-v0.4 §8.1).
- Mailmap normalization (PRD-v0.4 §2.2).

### Architecture Completeness Checklist

**Requirements Analysis**

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**

- [x] Critical decisions documented with versions
- [x] Technology stack fully specified (locked-out + locked-in)
- [x] Integration patterns defined (handler chain, contextvars, adapters)
- [x] Performance considerations addressed (NFR-PERF-* bench harness)

**Implementation Patterns**

- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**

- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** **READY WITH MINOR GAPS**

Reason: the 16 checklist items are all `[x]`, but 8 Important gaps (G1–G8) are flagged with proposed resolutions that must be applied during the first v0.5 implementation sprint, before chain code freezes. None of them block starting the work; all of them block tagging v0.5.0.

**Confidence Level:** medium-high.

- *High* on coherence (cascade traced explicitly), invariant preservation (I1–I7 verified per decision), and structure (100% file-level mapping).
- *Medium* on G1 (chain discontinuity on upgrade) — the proposed resolution is pragmatic but introduces a documented pre-chain blind spot. If forensic completeness is required for pre-chain records, the user runs `ulog repair --backfill-chain` (deferred to v0.6+ tooling).

**Key strengths:**

- Brownfield discipline preserved: zero PyPI runtime deps, lazy imports, idempotent setup, `_ulog_managed` flag, adapter uniformity all carried forward into v0.3-v0.5 additions.
- Clear separation between substrate (`docs/architecture.md` v0.2 reality) and forward decisions (this document — v0.3 to v0.5 deltas only).
- Negative-space documentation (Locked-out libraries table) closes the most likely AI-agent misstep — adding `click`/`GitPython`/`alembic`/`msgpack`.
- 7 frozen invariants (I1–I7) elevated to enforcement-level constraints throughout the doc.

**Areas for future enhancement:**

- v0.6 Tailwind standalone build (D3) — defer is documented but not scheduled.
- v0.7 `PostgresChainWriter` impl — interface defined (B3), impl deferred.
- Streaming verify (Merkle tree) for archives larger than 1M records.
- Co-author + mailmap support (deferred from v0.4 §2.2).

### Implementation Handoff

**AI Agent Guidelines:**

1. Treat this document as the source of truth for v0.3 → v0.5 work. PRDs supply WHAT; this doc supplies HOW.
2. Honor the 7 frozen invariants (I1–I7) without exception — any deviation is a release blocker.
3. Use the Locked-out libraries table (Starter Template Evaluation section) as a hard veto list.
4. Resolve gap items G1–G8 inline during the v0.5 first sprint, ahead of code-freeze.
5. Reference the cascade map (Decision Impact Analysis) when amending any of the 9 critical decisions — relitigation requires re-tracing dependents.
6. Adapter changes are atomic across SQLite/JSONL/CSV — never land a `Record` field that exists in only one impl.
7. New CLI subcommands follow the `ulog/_cli/cmd_<name>.py` pattern with `register(subparsers)` + `run(args)`.

**First implementation priorities (per step-04 sequence, with G-gaps interleaved):**

1. v0.3 first → `ulog/testing/` sub-package (lowest blast radius, validates the pytest-plugin packaging convention).
2. v0.4 next → `AuthorIndex` + sidecar SQLite + `/diff/<sha>`.
3. v0.5 storage core → A1 column-flag + A2 `SchemaError` (with G1 resolution baked in) + B3 `ChainWriter` interface + `SQLiteChainWriter`.
4. v0.5 chain integration → B1 SQLHandler chain mode + G2 `_REPLAY_ACTIVE` contextvar.
5. v0.5 query + ledger → `correlate` (with G7 precedence locked) + `bisect` + `incidents` (with G3 surrounding-record window locked).
6. v0.5 UI → multi-track + integrity badge + Issue button (with G3 body shape).
7. v0.5 CLI consolidation → `ulog` binary + remove `ulog-web` (with G6 RELEASE_NOTES entry).
8. CI gate (E2) — anytime; cheap to land first.
