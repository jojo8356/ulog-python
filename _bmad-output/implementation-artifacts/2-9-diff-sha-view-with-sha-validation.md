# Story 2.9: `/diff/<sha>` view with sha validation

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-9-diff-sha-view-with-sha-validation`
**Implements:** FR81 (`/diff/<sha>` server-side handler), NFR-SEC-30 (regex + `git rev-parse --verify` before `git show`)
**Source:** PRD-v0.4 §3.3 FR81, §4 NFR-SEC-30; epics.md Story 2.9
**Built on:** Stories 2.2 (CLI repo flag → ULOG_AUTHOR_REPO env)

## Story
As a viewer user clicking "view diff", I want the server to validate the sha (hex regex + `git rev-parse --verify`) and render `git show <sha>` output safely, so no shell injection or arbitrary command is possible.

## Acceptance Criteria
- **AC1** — Sha format check: `^[0-9a-f]{4,40}$` (case-insensitive). Invalid → 400.
- **AC2** — Repo path resolved from `ULOG_AUTHOR_REPO` env (set by Story 2.2). Missing env → 503-equivalent friendly message.
- **AC3** — `git rev-parse --verify <sha>^{commit}` confirms commit reachability. Not reachable → 404.
- **AC4** — `git show <sha>` output rendered HTML-escaped in `<pre>` block.
- **AC5** — `subprocess.run(...)` with list-args, `shell=False`, `cwd=repo`, `timeout=30`.
- **AC6** — Tests cover: invalid sha 400, valid-but-unknown sha 404, valid sha render, no-repo 503.

## Dev Agent Record
### File List
- `ulog/web/viewer/views.py` — new `diff_view` + `_validate_sha` helper
- `ulog/web/urls.py` — route `path("diff/<str:sha>/", views.diff_view, name="ulog-diff")`
- `ulog/web/templates/ulog/diff.html` — NEW
- `tests/test_diff_view.py` — NEW

### Completion Notes
Suite at 249 + 7 = 256/256.
