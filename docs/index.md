---
docType: docs-index
project_name: ulog-python
date: 2026-05-05
generator: bmad-document-project (exhaustive scan)
---

# ULog — Documentation Index

## Project Overview

- **Type:** monolith / library (Python)
- **Primary Language:** Python `>=3.10`
- **Architecture:** thin layer on stdlib `logging` + plugin handlers + storage adapters
- **Repository structure:** single `pyproject.toml` shipping one Python package (`ulog/`) with an embedded Django web viewer (`ulog/web/`); vendored `ucolor` git submodule under `vendor/ucolor-python/`

## Quick reference

- **Tech stack:** stdlib `logging` core (zero PyPI runtime deps); optional extras `[storage]` (sqlalchemy>=2.0), `[web]` (django>=5.0 + django-lucide), `[dev]` (pytest, mypy)
- **Entry points:** `import ulog` (library), `ulog-web` (console-script), `./run.sh` (local launcher)
- **Architecture pattern:** stdlib-compatible by construction (no parallel logger hierarchy); idempotent `setup()` via `_ulog_managed=True` handler tagging; lazy optional-dep imports

## Generated documentation (this DP run)

- [Project Overview](./project-overview.md) — what ULog is, public surfaces, status table
- [Architecture](./architecture.md) — patterns, invariants, ghost counts, freeze contract
- [Source Tree Analysis](./source-tree-analysis.md) — annotated directory map
- [Development Guide](./development-guide.md) — setup, day-to-day commands, contribution conventions
- [API Contracts](./api-contracts.md) — Python public API + Django HTTP routes + `ulog-web` CLI
- [Data Models](./data-models.md) — SQL `logs` table schema + JSONL/CSV shapes + reserved-keys frozenset
- [Component Inventory](./component-inventory.md) — formatters / handlers / adapters / views / templates catalog

## Standards

- [Django clean-code standard](./standards/django-clean-code-standard.md) — 7 architectural + 5 hygiene rules + i18n + 10 anti-patterns. Distilled from HackSoft Styleguide + Two Scoops. Applies to ulog and any future Django app (FastAPI mapping table for Cycloth included).

## Existing documentation (predates DP)

- [`README.md`](../README.md) — install + quick tour
- [`docs/prds/index.md`](./prds/index.md) — PRD roadmap (v0.1 → v0.5)
  - [PRD-v0.1-core](./prds/PRD-v0.1-core.md) — shipped
  - [PRD-v0.2-storage-and-ui](./prds/PRD-v0.2-storage-and-ui.md) — shipped
  - [PRD-v0.2.1-ui-bugfixes](./prds/PRD-v0.2.1-ui-bugfixes.md) — shipped
  - [PRD-v0.3-test-integration](./prds/PRD-v0.3-test-integration.md) — draft v1
  - [PRD-v0.4-commit-author-filter](./prds/PRD-v0.4-commit-author-filter.md) — draft v1
  - [PRD-v0.5-forensic-archive](./prds/PRD-v0.5-forensic-archive.md) — draft v1
- In-app runtime docs (served via `/docs/<slug>/` in the web viewer):
  [`ulog/web/docs/quickstart.md`](../ulog/web/docs/quickstart.md) ·
  [`storage.md`](../ulog/web/docs/storage.md) ·
  [`api.md`](../ulog/web/docs/api.md) ·
  [`troubleshooting.md`](../ulog/web/docs/troubleshooting.md) ·
  [`sectors-and-files.md`](../ulog/web/docs/sectors-and-files.md)

## Getting started

1. Read [`project-overview.md`](./project-overview.md) for the 30-second mental model.
2. Skim [`architecture.md`](./architecture.md) — pay attention to "Architectural patterns & invariants" and the **frozen contracts** at the bottom.
3. For new contributors: [`development-guide.md`](./development-guide.md).
4. For new feature work: pick the right PRD in [`docs/prds/index.md`](./prds/index.md). The `parent_prd` chain shows what each version depends on.

## Brownfield PRD entry point

When opening a new PRD with the BMad PRD workflow, point it at:

```
docs/index.md  (this file)
```

The PRD facilitator will pull `architecture.md`, `data-models.md`,
`api-contracts.md`, and the existing PRD chain as grounding context.

## DP run state

- Mode: `initial_scan`
- Scan level: `exhaustive`
- State file: [`project-scan-report.json`](./project-scan-report.json)
- Outputs: 8 files (this index + 7 generated docs)
- Verification: tests not run from this skill — see `make check` for the project's own validation
- Risks/follow-ups: none
- Recommended next checks before PR: `make check` (mypy + pytest)
