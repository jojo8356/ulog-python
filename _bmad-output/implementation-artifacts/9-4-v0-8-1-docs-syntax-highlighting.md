# Story 9.4: v0.8.1 docs syntax highlighting

Status: done

**Epic:** 9 — BMAD catch-up ledger (v0.7 → v0.9)
**PRD:** `docs/prds/PRD-v0.8.1-docs-syntax-highlight.md`
**Shipped as:** v0.8.1

## Scope Recorded

- Prism.js syntax highlighting on `/docs/*`.
- Light and dark Prism themes.
- Language classes emitted by the markdown/doc renderer.
- Supported grammars include Python, Bash, SQL, JSON, and YAML.

## Implementation Evidence

- Commit: `52bc377` — `feat(v0.8.1): Prism.js syntax highlighting on /docs/*`
- Files:
  - `ulog/web/templates/ulog/docs_page.html`
  - Prism static assets under `ulog/web/static/ulog/`
  - markdown rendering/highlight integration

## Regression Tests

- `tests/test_docs_syntax_highlight.py`

## Notes

This artifact regularizes already-shipped work. No production code was changed while creating this BMAD record.
