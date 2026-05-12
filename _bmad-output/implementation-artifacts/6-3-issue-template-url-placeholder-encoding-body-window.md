# Story 6.3: Issue-template URL with placeholder URL-encoding + body window

Status: done

**Epic:** 6 — v0.5 Cross-service & UI extensions
**Story key:** `6-3-issue-template-url-placeholder-encoding-body-window`
**Implements:** FR111, NFR-SEC-51, Gap G3.

## Story

As a viewer user clicking "Open issue" on a record,
I want the URL template's placeholders (`{msg}`, `{level}`, `{body}`, etc.)
to be URL-encoded server-side, with `{body}` = JSON of 2 records before +
record + 2 records after by `chain_pos`,
so that the URL is safe to share and the issue tracker gets actionable
context.

## Acceptance Criteria

1. `ulog.setup(issue_template_url="...")` stores the template URL in a
   process-global. Accepts `None` to disable.
2. Recognized placeholders: `{msg}`, `{level}`, `{service}`, `{author}`,
   `{author_handle}`, `{commit_sha}`, `{record_hash}`, `{labels}`,
   `{body}`. Unknown placeholders are left intact.
3. All resolved placeholder values are URL-encoded via
   `urllib.parse.quote(..., safe="")` — NFR-SEC-51.
4. `{body}` = JSON list of 5 records (2 before + target + 2 after) by
   `chain_pos`. At edges, the window shrinks (Gap G3).
5. Detail view renders an "Open issue" button (target `_blank`,
   `rel="noopener"`) when the template is configured.
6. Tests:
   - URL encoding of special chars (` `, `"`, `&`, `?`, `<`).
   - Body window picks correct 5 records by `chain_pos`.
   - Body window at boundary (chain_pos=1 → 3 records).
   - Unknown placeholder kept as-is.
   - Detail view shows button when configured, hides when not.

## Dev Agent Record

### Completion Notes List

- New module `ulog/_issue_template.py` (process-global + URL builder).
- `setup(issue_template_url=...)` wired in `ulog/setup.py`.
- New adapter method `body_window(chain_pos)` on `Adapter` base +
  `SQLiteAdapter` (others return `[]` — chain is SQL-only per B1).
- Detail view passes `issue_url` to template; `detail.html` renders
  button via `{% if issue_url %}`.
- 9 / 9 tests green; full suite 655 passed (no regression).

### File List

- `ulog/_issue_template.py` (NEW)
- `ulog/setup.py` — new `issue_template_url` kwarg
- `ulog/web/viewer/adapters.py` — `body_window` on Adapter + SQLite
- `ulog/web/viewer/views.py` — detail_view passes `issue_url`
- `ulog/web/templates/ulog/detail.html` — "Open issue" button
- `tests/test_issue_url.py` (NEW)
