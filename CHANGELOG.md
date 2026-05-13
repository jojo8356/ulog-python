# CHANGELOG

All notable changes to ulog-python. Versions follow the PRD index at
[docs/prds/index.md](docs/prds/index.md). RELEASE_NOTES.md focuses on
the v0.5 breaking changes; this file is the full history.

## Unreleased

In progress: v0.14 scraper, v0.8.2 vendoring + more HTMX, v0.4.4
SQL JOIN author-filter refactor.

## v0.17.0 — Log import

- `ulog import <file>… --db <out>` ingests external log files
  (jsonl, csv, nginx-combined, apache-combined, syslog RFC3164,
  journald-json, raw, custom regex). Imported rows out-of-chain
  (`is_imported=1`); streaming reader; .gz/.bz2 stdlib decoding.

## v0.16.0 — Unified solution search

- `unified_search(db, msg, stack, consent_community)` fans out
  across local (v0.13) + known-bugs (v0.14) + community (v0.15).
- Detail-view "Search solutions" button with per-record consent
  dialog. Provenance badges on every result row.

## v0.15.0 — Community-solutions site (client + self-host recipe)

- `ulog solutions {keygen, publish, fetch}` client; ed25519 signing
  (opt-in `[solutions]` extra for `cryptography>=42`).
- `docker/ulog-solutions/docker-compose.yml` recipe (Postgres 16 +
  the site image placeholder).
- `ULOG_SOLUTIONS_ENDPOINT` env for self-hosted deploys.

## v0.14.0 — Known-bugs cache (phase 1)

- Local SQLite cache at `~/.cache/ulog/bug-cache.sqlite`.
- `ulog bug-cache {refresh,search,status,clear}` — `refresh
  --source-file <curated.json>` for hand-curated imports until the
  full SO/GH/docs scraper lands.

## v0.13.0 — Local fix database

- `ulog.resolve(hash, by, note)` / `ulog.reopen(hash, reason)`
  signatures + sidecar SQLite at `<db>.fixes.sqlite`.
- "Known fix" panel on detail view when current record's signature
  matches a previously-resolved entry.

## v0.12.0 — Per-record call-stack capture

- `setup(capture_stack=True, capture_stack_locals=False)` attaches
  `traceback.extract_stack()` (+ optional `repr()` locals, 10 KB
  cap) to every record under `context.stack`.
- Detail-view collapsible frame tree.
- Source-line links (`ULOG_AUTHOR_REPO=` or `ULOG_SOURCE_BASE_URL=`).

## v0.11.0 — HTTP request inspector

- Auto-detect records carrying `method+url` context; renders an
  HTTP panel with method pill, status code colour, headers (with
  sensitive masking), body, latency, and a "Copy as curl" button.

## v0.10.0 — Fleet probes

- `@probe(target=URL, parents=[...])` decorator wraps pytest
  functions. Emits records on `logger='ulog.fleet'` with
  target/parents/latency_ms/probe_status in context.
- Sidebar "Fleet" tree section aggregates by target.

## v0.9.0 — Resource validity

- `ulog validate-resources --path .` walks JSON/TOML/CSV/INI files,
  parses each via stdlib (PyYAML opt-in), exits with failure count.
- Sidebar Resources panel when `ULOG_RESOURCES_DIR=` is set.

## v0.8.1 — Docs syntax highlighting

- Prism.js 1.30 on `/docs/*` with python/bash/sql/json/yaml grammars
  + light + dark themes (linked via `class="dark"` toggle).

## v0.8.0 (phase 1) — Modern frontend stack

- Tailwind v4.3 standalone CLI build pipeline (already in v0.6.2).
- Alpine.js 3.14 + HTMX 2.0 loaded via CDN.
- HTMX-augmented: multi-track form, records-list Prev/Next pagination.

## v0.7.0 — Test execution stack (data + UI + CLI)

- `with ulog.span("name"):` context manager — span_id +
  parent_span_id (via contextvar) + span_ms + span_status.
- Detail-view Span panel.
- `ulog explain --db <db>` waterfall tree CLI.

## v0.6.4 — export-html perf gate

- `make bench-fixture` + `make bench-export`; CI step parses
  `benchmark.json` for the SC1 ≤ 30 s target (advisory, first 2
  v0.6.4 runs).

## v0.6.3 — Cross-browser Playwright matrix

- `tests/test_export_html_e2e.py` parametrized chromium / firefox /
  webkit via `pytest --browser …`. CI job with `actions/cache@v4`
  for the browser binaries.

## v0.6.2 — Tailwind build pipeline

- Standalone v4.3 binary auto-downloaded by `make tailwind-build`
  per host platform. base.html links the bundled CSS; CDN script
  gone. `make tailwind-check` CI gate.

## v0.6.1 — Multi-format snapshot

- `ulog snapshot --format {log,jsonl,csv,html,pdf} --since today`.
  PDF opt-in via Playwright (already in `[dev]`).

## v0.6.0 (Epic 8 part 1) — Static HTML export

- `ulog export-html <db> --output <dir>` produces a self-contained
  directory of pages with the v0.5 features (integrity badge,
  incident panels, multi-track navigation). `--filter` / `--include`
  / `--theme` / `--inline-data` / `--force-cap` / `--repo`.

## v0.5.0 — Forensic black box (Epics 3 → 7)

- Hash-chained SQLite (`integrity='hash-chain'`, `min_retention_days`).
- `ulog {verify, repair, purge, correlate, bisect, replay, trace,
  incidents}` CLI.
- Replay primitives + Filter DSL.
- Incident lifecycle (`resolve` / `reopen` / `compute_states`).
- OTel cross-service auto-bind (W3C `traceparent`, no SDK dep).
- Multi-track view, integrity badge, issue-template URL button.
- `ulog-web` → `ulog web` migration (RELEASE_NOTES.md).

## v0.4.x — Author attribution + viewer polish

- v0.4.5: theme swap sync (View Transitions API + universal CSS
  fallback).
- v0.4.3: `/team/` directory page with per-author cards + GitHub
  URL inference.
- v0.4.2: Markdown renderer extensions (tables, ordered lists,
  blockquotes, hr, italics).
- v0.4.1: AuthorsSummary memoization (page-load < 3s).
- v0.4.0: git-blame author indexer + "Authored by" detail panel +
  authors sidebar.
- v0.4.4: FTS5 opt-in full-text search + startup pre-warm.

## v0.3.0 — Test integration

- pytest plugin (`[project.entry-points.pytest11]`), `--ulog-db
  PATH` CLI flag, Tests sidebar in the viewer, "Test context"
  panel.

## v0.2.1 — UI bugfixes

- Ghost-count contract (per-axis counts ignore that axis's filter).
- Sidebar spacing + theme fade.

## v0.2.0 — Storage + Web UI

- SQLHandler / JSONLineHandler / CSVHandler.
- Django + Tailwind inspection UI (`ulog-web`).
- Filter sidebar, detail view, tutorial overlay, dark mode.

## v0.1.0 — Core

- Stdlib `logging` integration with sensible defaults.
- Four built-in formatters (qlnes / simple / verbose / json).
- ucolor integration (vendored as a submodule, optional).
- Context binding via contextvars.
- Idempotent `setup()`.
