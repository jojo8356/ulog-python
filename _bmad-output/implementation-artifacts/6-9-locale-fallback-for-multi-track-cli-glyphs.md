# Story 6.9: Locale fallback for multi-track CLI glyphs

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-9-locale-fallback-for-multi-track-cli-glyphs`
**Implements:** NFR-PORT-50.

## Story

On non-UTF-8 terminals (Windows cmd.exe, ancient SSH, no-locale CI), ULog's CLI glyphs (∞, ⚠, ✓, ✗) become mojibake. Fall back to ASCII equivalents when `locale.getpreferredencoding()` isn't UTF-8.

## Acceptance Criteria

1. New `ulog/_glyphs.py` exposes `g(name) -> str` that returns the appropriate glyph based on locale.
2. Names: `check` (✓ / `OK`), `cross` (✗ / `X`), `inf` (∞ / `inf`), `warn` (⚠ / `WARN`), `bullet` (• / `*`).
3. `cmd_correlate` uses `g("inf")` and `g("warn")` instead of literal glyphs.
4. `cmd_verify`, `cmd_repair` continue to use literal glyphs in v0.5 (their output is short — ASCII-fallback for v0.6 if Windows feedback demands).
5. `LC_ALL=C python -m ulog._cli correlate ...` outputs ASCII (no `∞`).
6. Default UTF-8 env continues to use unicode.

## Dev Notes

Stdlib `locale.getpreferredencoding(False)` returns the active encoding. Cache at module-import time.

## Dev Agent Record

### Completion Notes List

- `ulog/_glyphs.py` (NEW). Resolves locale at module import (`utf-8` /
  `utf8` accepted; ASCII/iso-8859 → fallback). `g(name)` returns
  appropriate glyph.
- `cmd_correlate` now uses `g("inf")` and `g("warn")` instead of
  literal ∞ / ⚠.
- 6 / 6 tests in `tests/test_glyphs.py` green (UTF-8 path, ASCII
  fallback, unknown name KeyError, recognises 4 utf-8 variant forms,
  rejects 4 non-utf-8 forms, end-to-end correlate output).
- mypy / ruff / format clean.

### File List

- `ulog/_glyphs.py` (NEW)
- `ulog/_cli/cmd_correlate.py` — uses `g(...)` helper.
- `tests/test_glyphs.py` (NEW)
