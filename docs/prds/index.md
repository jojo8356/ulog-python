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
| v0.4.2 | [PRD-v0.4.2-docs-quality.md](./PRD-v0.4.2-docs-quality.md) | Docs refresh post-Epic 2 + per-page collapsible TOC accordion | draft v1 | 250 |
| v0.5.0 | [PRD-v0.5-forensic-archive.md](./PRD-v0.5-forensic-archive.md) | Forensic black box — immutable chain, replay, correlate, incidents ledger | draft v1 | 706 |
| v0.6.0 | [PRD-v0.6-static-export.md](./PRD-v0.6-static-export.md) | Static HTML export — `ulog export-html` for archival/distribution (compliance, GitHub Releases, Pages) | draft v1 | 600 |
| v0.7.0 | [PRD-v0.7-test-execution-stack.md](./PRD-v0.7-test-execution-stack.md) | "EXPLAIN ANALYZE for tests" — span-based execution timeline + waterfall in viewer + `ulog explain` CLI | draft v1 | 380 |
| v0.8.0 | [PRD-v0.8-modern-frontend-stack.md](./PRD-v0.8-modern-frontend-stack.md) | Modern frontend stack — Tailwind CLI standalone (CSS <10KB) + Alpine.js (declarative JS) + HTMX (partial swaps). Replaces CDN runtime + ad-hoc inline JS. Supersedes Story 8-1. | draft v1 | 460 |
| v0.8.1 | [PRD-v0.8.1-docs-syntax-highlight.md](./PRD-v0.8.1-docs-syntax-highlight.md) | Patch — code syntax highlighting in `/docs/*` via Prism.js (CSS-variable theme, dark-mode aware). Backed by [benchmarks/syntax-highlighter-2026.md](./benchmarks/syntax-highlighter-2026.md). | draft v1 | 302 |

## Filiation

```
PRD-v0.1-core.md
└── PRD-v0.2-storage-and-ui.md
    ├── PRD-v0.2.1-ui-bugfixes.md   (patch)
    ├── PRD-v0.3-test-integration.md
    ├── PRD-v0.4-commit-author-filter.md
    │   ├── PRD-v0.4.1-viewer-perf-hotpath.md  (patch — authors-summary memoization)
    │   └── PRD-v0.4.2-docs-quality.md         (patch — docs refresh + TOC accordion)
    └── PRD-v0.5-forensic-archive.md   (draft v1 — emerged from brainstorming session 2026-05-04)
        └── PRD-v0.6-static-export.md  (draft v1 — `ulog export-html` for archival/distribution)
            └── PRD-v0.7-test-execution-stack.md  (draft v1 — span timeline / waterfall / `ulog explain`)
                └── PRD-v0.8-modern-frontend-stack.md  (draft v1 — Tailwind CLI + Alpine.js + HTMX, supersedes Story 8-1)
                    └── PRD-v0.8.1-docs-syntax-highlight.md  (draft v1 — Prism.js code highlighting, backed by benchmarks/syntax-highlighter-2026.md)
```

## Conventions

- **Frontmatter** : `docType: prd`, `version`, `status`, `parent_prd` (sauf v0.1).
- **Statut** : `draft v1` → `shipped vX.Y.Z` une fois la release taguée.
- **Naming** : `PRD-v<MAJOR>.<MINOR>[.<PATCH>]-<topic-kebab>.md`.
