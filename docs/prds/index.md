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
| v0.5.0 | [PRD-v0.5-forensic-archive.md](./PRD-v0.5-forensic-archive.md) | Forensic black box — immutable chain, replay, correlate, incidents ledger | draft v1 | 706 |
| v0.6.0 | [PRD-v0.6-static-export.md](./PRD-v0.6-static-export.md) | Static HTML export — `ulog export-html` for archival/distribution (compliance, GitHub Releases, Pages) | draft v1 | 600 |

## Filiation

```
PRD-v0.1-core.md
└── PRD-v0.2-storage-and-ui.md
    ├── PRD-v0.2.1-ui-bugfixes.md   (patch)
    ├── PRD-v0.3-test-integration.md
    ├── PRD-v0.4-commit-author-filter.md
    └── PRD-v0.5-forensic-archive.md   (draft v1 — emerged from brainstorming session 2026-05-04)
        └── PRD-v0.6-static-export.md  (draft v1 — `ulog export-html` for archival/distribution)
```

## Conventions

- **Frontmatter** : `docType: prd`, `version`, `status`, `parent_prd` (sauf v0.1).
- **Statut** : `draft v1` → `shipped vX.Y.Z` une fois la release taguée.
- **Naming** : `PRD-v<MAJOR>.<MINOR>[.<PATCH>]-<topic-kebab>.md`.
