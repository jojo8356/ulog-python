# Story 9.3: v0.8 modern frontend stack

Status: done

**Epic:** 9 — BMAD catch-up ledger (v0.7 → v0.9)
**PRD:** `docs/prds/PRD-v0.8-modern-frontend-stack.md`
**Shipped as:** v0.8.0 / v0.8.2 follow-up

## Scope Recorded

- Tailwind standalone CLI pipeline already delivered through Epic 8 follow-up Story 8.1.
- Alpine.js integration for lightweight client-side behavior.
- HTMX integration for partial updates.
- HTMX multi-track form.
- HTMX records-list pagination.
- HTMX filter form.
- Cheatsheet inline search.
- Vendored Alpine/HTMX assets in v0.8.2 follow-up.

## Implementation Evidence

- Commit: `400d3b4` — `feat(v0.8): Alpine.js + HTMX (phase 1) — CDN + first HTMX form`
- Commit: `4d4950f` — `feat(v0.8): HTMX pagination on records list`
- Commit: `615e833` — `feat(v0.8): Alpine.js-powered inline search on /docs/cheatsheet/`
- Commit: `2e4cedb` — `feat(v0.8): HTMX on records-list filter form`
- Commit: `864fdef` — `feat(v0.8.2): vendor Alpine.js + HTMX (offline-clean)`
- Commit: `b2de2ad` — `chore(test): stabilize uv and browser e2e workflow`

## Regression Tests

- `tests/test_v08_frontend.py`
- `tests/test_filter_form_htmx.py`
- `tests/test_pagination_htmx.py`
- `tests/test_cheatsheet_search.py`
- `tests/test_js_vendor.py`
- `tests/test_tailwind_freshness.py`

## Notes

This artifact regularizes already-shipped work. No production code was changed while creating this BMAD record.
