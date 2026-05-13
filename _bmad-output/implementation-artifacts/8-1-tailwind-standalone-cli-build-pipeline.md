# Story 8.1: Tailwind standalone CLI build pipeline (PRD-v0.6.2)

Status: done

**Epic:** 8 — v0.6 static HTML export
**Implements:** Decision D3 acceleration / Story 8.1
**PRD:** v0.6.2 (operating manual)

## Completion Notes

- Tailwind v4.3.0 standalone binary (28 MB) auto-downloaded by
  `make tailwind-build` per host platform (Linux x64, Linux arm64,
  macOS arm64, macOS x64).
- Input: `ulog/web/static/ulog/_tailwind-input.css` (uses @source
  + @variant for v4 CSS-first config).
- Output: `ulog/web/static/ulog/{tailwind,ulog-light,ulog-dark}.css`
  — 31 KB minified, ~7 KB gzipped.
- `base.html` no longer loads `cdn.tailwindcss.com`; instead links
  `{% static 'ulog/tailwind.css' %}`. CDN dev-mode warning gone.
- `make tailwind-check` re-builds into /tmp and diff's; CI step
  fails on drift.
- 23 / 23 freshness tests green (`test_tailwind_freshness.py`)
  asserting key utility classes + minified + size cap.

## File List

- `Makefile` (NEW — release-eng targets)
- `ulog/web/static/ulog/_tailwind-input.css` (NEW)
- `ulog/web/static/ulog/{tailwind,ulog-light,ulog-dark}.css` (NEW — built artifacts)
- `ulog/web/templates/ulog/base.html` — CDN script swapped for {% static %} link
- `.gitignore` — `.tailwind/`, `.benchmarks/`, `benchmark.json`, fixtures
- `tests/test_tailwind_freshness.py` (NEW — 23 tests)
- `docs/prds/PRD-v0.6.2-tailwind-build-pipeline.md` (NEW)
