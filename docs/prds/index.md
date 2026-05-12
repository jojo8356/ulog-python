# PRD Index

Roadmap des Product Requirements Documents pour `ulog-python`.
Chaque ligne pointe vers le PRD complet.

## Versions

| Version | PRD | Sujet | Statut | Lignes |
|---|---|---|---|---|
| v0.1.0 | [PRD-v0.1-core.md](./PRD-v0.1-core.md) | Core API + 4 formatters + ucolor + contextvars | shipped | 334 |
| v0.2.0 | [PRD-v0.2-storage-and-ui.md](./PRD-v0.2-storage-and-ui.md) | Storage handlers (SQL/JSONL/CSV) + Django inspection UI | shipped | 471 |
| v0.2.1 | [PRD-v0.2.1-ui-bugfixes.md](./PRD-v0.2.1-ui-bugfixes.md) | Patch — ghost counts + sidebar spacing + theme fade | shipped | 192 |
| v0.3.0 | [PRD-v0.3-test-integration.md](./PRD-v0.3-test-integration.md) | pytest plugin + UI section "tests vs logs" | draft v1 | 397 |
| v0.4.0 | [PRD-v0.4-commit-author-filter.md](./PRD-v0.4-commit-author-filter.md) | git-blame author enrichment + sidebar "By author" | draft v1 | 335 |
| v0.4.1 | [PRD-v0.4.1-viewer-perf-hotpath.md](./PRD-v0.4.1-viewer-perf-hotpath.md) | Patch — authors-summary memoization + SQL GROUP BY (page-load < 3s) | implementing | — |
| v0.4.2 | [PRD-v0.4.2-docs-quality.md](./PRD-v0.4.2-docs-quality.md) | Docs refresh post-Epic 2 + per-page TOC accordion + markdown renderer extension (tables/ol/em/blockquote/hr) + per-Epic QA master checkbox | draft v1 | 489 |
| v0.4.3 | [PRD-v0.4.3-team-page.md](./PRD-v0.4.3-team-page.md) | `/team/` directory page — per-author cards with GitHub link inference, tests/records/files-owned counts, drill-down at `/team/<email>/`. Builds on v0.4 AuthorIndex; zero new runtime dep. | draft v1 | 429 |
| v0.4.4 | [PRD-v0.4.4-perf-sub-second.md](./PRD-v0.4.4-perf-sub-second.md) | Patch — every page-load path under 1s (search + filters + cold cache). SQL JOIN author filter, opt-in SQLite FTS5 search, startup pre-warm. Tightens v0.4.1 budgets. | draft v1 | 411 |
| v0.4.5 | [PRD-v0.4.5-theme-swap-sync.md](./PRD-v0.4.5-theme-swap-sync.md) | Patch — dark/light toggle: every element transitions in lockstep. View Transitions API primary + universal-selector fallback. Kills the per-tag-list desync. | draft v1 | 408 |
| v0.5.0 | [PRD-v0.5-forensic-archive.md](./PRD-v0.5-forensic-archive.md) | Forensic black box — immutable chain, replay, correlate, incidents ledger | draft v1 | 706 |
| v0.6.0 | [PRD-v0.6-static-export.md](./PRD-v0.6-static-export.md) | Static HTML export — `ulog export-html` for archival/distribution (compliance, GitHub Releases, Pages) | draft v1 | 600 |
| v0.6.1 | [PRD-v0.6.1-snapshot-exports.md](./PRD-v0.6.1-snapshot-exports.md) | Multi-format snapshot exports — `ulog snapshot --format html\|log\|json\|csv\|pdf` with `--since today` for daily archives. PDF opt-in via `[snapshot-pdf]` (Playwright). | draft v1 | 202 |
| v0.7.0 | [PRD-v0.7-test-execution-stack.md](./PRD-v0.7-test-execution-stack.md) | "EXPLAIN ANALYZE for tests" — span-based execution timeline + waterfall in viewer + `ulog explain` CLI | draft v1 | 380 |
| v0.8.0 | [PRD-v0.8-modern-frontend-stack.md](./PRD-v0.8-modern-frontend-stack.md) | Modern frontend stack — Tailwind CLI standalone (CSS <10KB) + Alpine.js (declarative JS) + HTMX (partial swaps). Replaces CDN runtime + ad-hoc inline JS. Supersedes Story 8-1. | draft v1 | 460 |
| v0.8.1 | [PRD-v0.8.1-docs-syntax-highlight.md](./PRD-v0.8.1-docs-syntax-highlight.md) | Patch — code syntax highlighting in `/docs/*` via Prism.js (CSS-variable theme, dark-mode aware). Backed by [benchmarks/syntax-highlighter-2026.md](./benchmarks/syntax-highlighter-2026.md). | draft v1 | 302 |
| v0.9.0 | [PRD-v0.9-resource-validity.md](./PRD-v0.9-resource-validity.md) | Resource validity panel — viewer scans the project for JSON/TOML/CSV/INI files (YAML opt-in), reports parse status in a sidebar + `ulog validate-resources` CLI for CI. Stdlib parsers only. | draft v1 | 337 |
| v0.10.0 | [PRD-v0.10-fleet-dashboard.md](./PRD-v0.10-fleet-dashboard.md) | Fleet dashboard for remote endpoint tests — `@probe(target=URL, parents=[...])` decorator + hierarchical fleet tree + per-target drill-down + cross-panel links to Tests / Authors panels. HTTP/HTTPS/TCP/Unix-socket probes via stdlib. | draft v1 | 276 |
| v0.11.0 | [PRD-v0.11-http-request-inspector.md](./PRD-v0.11-http-request-inspector.md) | HTTP request inspector — auto-detect records with `method+url` context, render src/dest URL + JSON body (Prism) + status badge + latency + sensitive-header masking + "Copy as curl". Records-list filter by method + status range. | draft v1 | 266 |
| v0.12.0 | [PRD-v0.12-call-stack-tracing.md](./PRD-v0.12-call-stack-tracing.md) | Per-record call-stack tracing — every emit captures the Python stack via `traceback.extract_stack()` (≤ 50 µs, opt-out). Detail view renders frames as collapsible tree, optional locals capture (10 KB cap, sensitive-key masking). Frame links → `/source/<path>:<line>/` when `--repo` set. | draft v1 | 227 |
| v0.13.0 | [PRD-v0.13-local-fix-database.md](./PRD-v0.13-local-fix-database.md) | Local fix database — devs resolve errors with a write-up; signature = `sha256(canonical_msg + stack_hash)`; next time the same error fires, the viewer auto-links to the prior fix. Sidecar `<db>.fixes.sqlite`. CLI `ulog fix {resolve,list,show,unresolve}`. Read-only mode for compliance-shipped DBs. | draft v1 | 235 |
| v0.14.0 | [PRD-v0.14-known-bugs-auto-lookup.md](./PRD-v0.14-known-bugs-auto-lookup.md) | LONG-TERM — known-bugs auto-lookup. Detects language + framework from the stack, queries a local cache of scraped SO Data Dump + GitHub issues + official docs. "Known matches" panel shows top-3 results with accepted-answer badge. Zero LLM. `ulog bug-cache refresh` daily. | draft v1 | 248 |
| v0.15.0 | [PRD-v0.15-community-solutions-site.md](./PRD-v0.15-community-solutions-site.md) | LONG-TERM — `ulog.solutions` hosted community site. Devs push their v0.13 fixes signed via ed25519 keypair bound to GH OAuth identity; same signatures across orgs surface each other's solutions. CC BY-SA 4.0. Self-host Docker Compose ships from day 1. | draft v1 | 281 |
| v0.16.0 | [PRD-v0.16-unified-solution-search.md](./PRD-v0.16-unified-solution-search.md) | Unified solution search — ONE "Search solutions" button on every detail view (when signature present). Per-record consent dialog → parallel fan-out: community (v0.15) + local DB (v0.13) + known-bugs (v0.14 when shipped) → merged + reranked + deduped. Payload = signature only. Modes: `off` / `opt-in` (default) / `auto-consent` (banner-warned). | draft v1 | 320 |
| v0.17.0 | [PRD-v0.17-log-import.md](./PRD-v0.17-log-import.md) | Log import — `ulog import <file>… --db <out>.sqlite` ingests external log files (.log, .txt, JSONL, CSV, nginx/apache combined, syslog 3164/5424, journald JSON, raw, custom regex) into ulog's storage. Imported rows marked `is_imported=1`, out-of-chain (chain integrity preserved). Streaming reader; .gz/.bz2 stdlib, .zst opt-in. 6 built-in parsers + regex escape hatch. | draft v1 | — |

## Filiation

```
PRD-v0.1-core.md
└── PRD-v0.2-storage-and-ui.md
    ├── PRD-v0.2.1-ui-bugfixes.md   (patch)
    ├── PRD-v0.3-test-integration.md
    ├── PRD-v0.4-commit-author-filter.md
    │   ├── PRD-v0.4.1-viewer-perf-hotpath.md  (patch — authors-summary memoization)
    │   ├── PRD-v0.4.2-docs-quality.md         (patch — docs refresh + TOC accordion + markdown extension + Epic QA toggle)
    │   ├── PRD-v0.4.3-team-page.md            (feature — /team/ directory with cards + drill-down + GitHub link)
    │   ├── PRD-v0.4.4-perf-sub-second.md      (patch — every page-load path < 1s: SQL JOIN authors + FTS5 search + startup pre-warm)
    │   └── PRD-v0.4.5-theme-swap-sync.md      (patch — UI polish: every element flips theme in lockstep via View Transitions API + universal-selector fallback)
    └── PRD-v0.5-forensic-archive.md   (draft v1 — emerged from brainstorming session 2026-05-04)
        └── PRD-v0.6-static-export.md  (draft v1 — `ulog export-html` for archival/distribution)
            ├── PRD-v0.6.1-snapshot-exports.md  (patch — `ulog snapshot --format {html,log,json,csv,pdf}` + `--since today` for daily archives; PDF opt-in via [snapshot-pdf])
            └── PRD-v0.7-test-execution-stack.md  (draft v1 — span timeline / waterfall / `ulog explain`)
                └── PRD-v0.8-modern-frontend-stack.md  (draft v1 — Tailwind CLI + Alpine.js + HTMX, supersedes Story 8-1)
                    └── PRD-v0.8.1-docs-syntax-highlight.md  (draft v1 — Prism.js code highlighting, backed by benchmarks/syntax-highlighter-2026.md)
                        └── PRD-v0.9-resource-validity.md  (draft v1 — Resource validity panel + `ulog validate-resources` CLI; stdlib parsers only, YAML opt-in)
                            ├── PRD-v0.10-fleet-dashboard.md  (draft v1 — synthetic monitoring built on v0.3 pytest plugin: `@probe(target=URL)` decorator + hierarchical fleet tree + cross-panel links; HTTP/HTTPS/TCP/Unix probes via stdlib)
                            └── PRD-v0.11-http-request-inspector.md  (draft v1 — auto-detect HTTP-shaped context records, render src/dest URL + JSON body + status + latency + "Copy as curl"; sensitive-header masking)
                                └── PRD-v0.12-call-stack-tracing.md  (draft v1 — per-record stack capture via `traceback.extract_stack()`; detail-view collapsible tree + optional locals + frame links to /source/)
                                    └── PRD-v0.13-local-fix-database.md  (draft v1 — per-project fixes ledger keyed by `sha256(canonical_msg + stack_hash)`; sidecar SQLite; CLI `ulog fix …`)
                                        ├── PRD-v0.14-known-bugs-auto-lookup.md  (LONG-TERM — scrape SO Data Dump + GH issues + docs, viewer panel "Known matches" cache-only)
                                        └── PRD-v0.15-community-solutions-site.md  (LONG-TERM — hosted `ulog.solutions` site, ed25519-signed submissions, GH OAuth, CC BY-SA 4.0, self-host Docker recipe shipped)
                                            └── PRD-v0.16-unified-solution-search.md  (draft v1 — merges v0.13 + v0.14 + v0.15 into ONE consent-gated "Search solutions" button + merged ranked panel)

PRD-v0.5-forensic-archive.md
└── PRD-v0.17-log-import.md  (draft v1 — `ulog import` ingests arbitrary log files into a ulog SQLite DB; out-of-chain via is_imported=1; 6 built-in parsers + regex escape hatch)
```

## Conventions

- **Frontmatter** : `docType: prd`, `version`, `status`, `parent_prd` (sauf v0.1).
- **Statut** : `draft v1` → `shipped vX.Y.Z` une fois la release taguée.
- **Naming** : `PRD-v<MAJOR>.<MINOR>[.<PATCH>]-<topic-kebab>.md`.
