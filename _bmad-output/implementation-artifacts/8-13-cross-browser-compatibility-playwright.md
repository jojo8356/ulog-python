# Story 8.13: Cross-browser compatibility (Playwright)

Status: done

**Epic:** 8 — v0.6 static HTML export
**PRD:** v0.6.3 (operating manual)

## Completion Notes

- `tests/test_export_html_e2e.py` — 6 tests, parametrized over
  chromium / firefox / webkit via the pytest-playwright `--browser`
  CLI flag.
- Tests cover: index load + record count, zero console errors,
  integrity badge visible, click-row → detail navigation, XSS
  escape (NFR-SEC-60 re-asserted in real browser), file:// fetch
  for --inline-data.
- `pytest-playwright>=0.5` added to `[dev]` extras; deptry
  module map updated.
- `.github/workflows/ci.yml` gains `playwright-cross-browser` job
  with browser-cache via `actions/cache@v4` keyed by pyproject hash.
- Local validation: 6 / 6 green on chromium.

## File List

- `tests/test_export_html_e2e.py` (NEW — 6 tests × 3 browsers in CI)
- `pyproject.toml` — pytest-playwright in [dev]
- `.github/workflows/ci.yml` — playwright-cross-browser job
