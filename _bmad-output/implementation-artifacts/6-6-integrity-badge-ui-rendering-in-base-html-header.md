# Story 6.6: Integrity badge UI rendering in `base.html` header

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-6-integrity-badge-ui-rendering-in-base-html-header`
**Implements:** FR113.
**Built on:** Story 3.10 (`<db>.verify_state.json` sidecar — data already plumbed).

## Story

As any viewer user,
I want an integrity badge in the page header showing `Integrity ✓ verified up to #N (last check: T)` or `Integrity ✗ broken at #N`,
so that I always know whether the archive is currently trustworthy.

## Acceptance Criteria

1. Header has an integrity badge between the DB-path span and the nav.
2. Badge content:
   - `status: OK` → green pill `✓ Integrity verified` + tooltip `verified up to #N · last check: <relative>`.
   - `status: BROKEN` → red pill `✗ BROKEN at #N` + tooltip `last check: <relative>`.
   - No sidecar → gray pill `Integrity: never verified`.
3. Badge auto-renders on every page (`base.html` extension).
4. Template tag `{% integrity_badge %}` resolves data from `<settings.ULOG_LOGS_PATH>.verify_state.json` at request time.
5. Tests:
   - `test_badge_ok_renders_when_sidecar_is_ok`
   - `test_badge_broken_renders_when_sidecar_is_broken`
   - `test_badge_never_verified_when_sidecar_absent`
   - `test_badge_appears_on_every_page` (records list + detail view).

## Dev Agent Record

### Completion Notes List

- New template tag `{% integrity_badge %}` (`ulog/web/viewer/templatetags/integrity.py`).
- New partial `ulog/_integrity_badge.html` with 3 states (OK / BROKEN / missing).
- Inserted in `base.html` header (between DB path and Records link).
- Relative-timestamp helper `_relative_ts` (Ns/Nm/Nh/Nd ago).
- 3 / 3 tests green: missing sidecar → "never verified", OK after verify
  → "Integrity ✓", BROKEN after corruption → "BROKEN" rendered.

### File List

- `ulog/web/viewer/templatetags/integrity.py` (NEW)
- `ulog/web/templates/ulog/_integrity_badge.html` (NEW)
- `ulog/web/templates/ulog/base.html` — `{% load integrity %}` + `{% integrity_badge %}`
- `tests/test_integrity_badge.py` (NEW)
