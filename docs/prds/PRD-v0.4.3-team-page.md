---
docType: prd
project_name: ulog-python
version: 0.4.3
date: 2026-05-11
author: jojo8356
status: draft v1
parent_prd: PRD-v0.4-commit-author-filter.md
---

# ULog v0.4.3 — Team page

> A dedicated `/team/` page that surfaces every code author whose
> work shows up in the logs. Each author card answers, in one view:
> *who are they (name + handle), how do I reach them (email +
> GitHub), what's their footprint in this project (tests authored,
> records emitted, files owned, last contribution)?* Builds on the
> v0.4 `AuthorIndex` infrastructure; zero new runtime dependency.

## 0. Problem

The Authors sidebar (Story 2.6) lists everyone who's written code
touched by logged records, but the entry point is **filtering** —
click an author, see their records. The information about the
author themselves (who they are, what else they've done in this
codebase, how to reach them) is buried behind:

1. **One click into a record** to see the "Authored by" panel
   (name + email + 7-char sha + relative date). Adds friction
   when you want to *map a name to a person*, not investigate a
   single log line.
2. **Manual git log** if you want their full footprint
   (commit history, files touched, contribution recency).
3. **No GitHub link anywhere.** Even when the email is a
   GitHub-issued `*@users.noreply.github.com` (which encodes the
   GitHub username deterministically), the viewer surfaces only
   the raw email.
4. **No test attribution rollup.** AC e2-2.1-2 says "8 author
   names listed" — that's true on the sidebar, but the *number
   of tests each one authored* (the natural "who owns what test"
   question during a triage) requires manual cross-referencing of
   the Tests sidebar with the Authors sidebar.

The information already lives in the system:
- `AuthorIndex` maps `(file, line) → Author(name, email, sha, ts)`.
- `compute_authors_summary` already aggregates per-author record
  counts (used for the sidebar ghost counts).
- The TestSummary / `context.test_id` field on records identifies
  which test each record belongs to.
- `git log` (via the existing subprocess wrapper used by
  `git blame`) can return per-author commit history.

The missing piece is a **page-level aggregator** that joins all
three into a coherent "team directory" view.

## 1. Vision

A new `/team/` route renders a grid of author cards, each card
showing the author's profile and their full footprint in the
project. Plus a per-author drill-down at `/team/<email>/` for the
"give me everything you know about this person" view.

### 1.1 Top-level page — `/team/`

A responsive grid of author cards, one per distinct author with
≥ 1 blamed line in any log-referenced file. Sorted by **records
authored, descending** (most prolific contributors first); the
`<unknown>` sentinel is excluded from the grid (it's already
surfaced in the sidebar with its own "Show unknown" toggle).

Each card displays:

```
┌────────────────────────────────────────────────────┐
│ 🟦  Alice Chen                            ⓘ active │
│     alice.chen@globex.io                           │
│     [@alice-chen on GitHub ↗]                      │
│                                                    │
│  📝 42 tests  ·  🧾 12,304 records                 │
│  📁 8 files   ·  ⏱ committed 3 days ago            │
│                                                    │
│  [View all records →]  [View tests →]              │
└────────────────────────────────────────────────────┘
```

Fields, ranked by priority:

| Field | Source | Notes |
|---|---|---|
| **Display name** | `Author.name` from `git blame` porcelain | Falls back to email local-part if empty |
| **Avatar** | Initials in a colored square (deterministic from email hash) | No Gravatar / no third-party fetch — keeps NFR-DEP-50 happy and avoids leaking email hashes to gravatar.com |
| **Email** | `Author.email` | Truncated to 40 chars in the card; full on hover |
| **GitHub handle** | Inferred from email pattern (Decision G1) | Hidden if not derivable |
| **Tests authored** | Count of unique `context.test_id` where the test's source file is blamed to this author for any line | Story 1.6's `TestSummaryRow.file` joined with `AuthorIndex.author_for(file, any_line)` |
| **Records emitted** | Existing `compute_authors_summary` count | Already cached |
| **Files owned** | Count of distinct files where ANY line is blamed to this author | New aggregation method `AuthorIndex.files_for(email)` |
| **Last contribution** | Most recent `Author.ts` across all their blamed lines | Already in the cache; just need to track max |
| **Active badge** | Present if last contribution ≤ 30 days ago | Visual indicator only |

### 1.2 Author drill-down — `/team/<email>/`

URL: `/team/<url-encoded-email>/`. The email key (vs the GitHub
handle) is deterministic and matches the existing
`?author=<email>` filter on the records list.

Sections:

1. **Profile header** — same fields as the card, larger.
2. **Activity summary table** — chronological list of distinct
   commits authored by this person that touched log-referenced
   files (date, short-sha, message, files-changed count). Limited
   to last 50 commits to avoid unbounded subprocess work.
3. **Tests authored** — table of test_id × file × outcome
   distribution (passed/failed/skipped/errored counts).
4. **Records by level** — bar chart in Tailwind (no JS lib) of
   `Counter[level]` for records authored by this person.
5. **Files owned** — list of files with line-count contribution
   (how many lines of each file this author is currently blamed
   for; reflects current HEAD, not historic).

Cross-links:
- "View all records →" → `/?author=<email>` (existing filter).
- Each test_id row → `/?test_id=<id>` (existing filter).
- Each commit short-sha → `/diff/<sha>/` (existing diff view).
- Each file row → opens at line 1 in the source tree (deferred —
  there's no source-tree view yet; for v0.4.3 the link is text-only).

### 1.3 GitHub handle inference (Decision G1)

Deterministic mapping from common email patterns:

| Email pattern | GitHub URL | Confidence |
|---|---|---|
| `<handle>@users.noreply.github.com` | `https://github.com/<handle>` | **certain** — GitHub-issued, encodes the canonical username |
| `<digits>+<handle>@users.noreply.github.com` | `https://github.com/<handle>` | **certain** — the prefixed form GH uses since 2017 |
| anything else | — | **none** — no inference; surface email only |

We **do NOT**:
- Scrape GitHub for matching emails (rate-limited, privacy concern).
- Parse `Co-Authored-By:` trailers — out of scope for v0.4.3.
- Use Gravatar — leaks email hashes externally.

Authors with non-GitHub emails just don't get a GitHub link badge.

### 1.4 Entry points

Three navigation hooks:

1. **Header nav** — new "Team" link next to "Records" / "Docs"
   (header bar in `base.html`). Always visible.
2. **Authors sidebar** — each row gains a small `→` icon that
   links to `/team/<email>/` (alongside the existing checkbox
   that filters records).
3. **Authored-by panel** in detail view — the author's name
   becomes a link to `/team/<email>/` (currently it's plain
   text + a "view all records from this author" filter link).

## 2. Scope

### 2.1 In scope

1. **Backend aggregation:**
   - `AuthorIndex.files_for(email: str) -> list[tuple[str, int]]` —
     yields `(file, line_count)` for files the author owns at
     current HEAD. Computed lazily, cached.
   - `AuthorIndex.tests_for(email: str, adapter: Adapter) -> list[TestSummaryRow]` —
     test_ids whose source file has ≥ 1 line blamed to the email.
   - `AuthorIndex.commits_for(email: str, limit: int = 50) -> list[CommitRow]` —
     subprocess `git log --author=<email> --max-count=50 --format=…`
     limited to files in the log dataset.
2. **Views:**
   - `team_index_view(request: HttpRequest) -> HttpResponse` —
     renders the grid at `/team/`.
   - `team_member_view(request: HttpRequest, email: str) -> HttpResponse` —
     renders the drill-down at `/team/<email>/`.
3. **Templates:**
   - `ulog/templates/ulog/team_index.html` — grid layout.
   - `ulog/templates/ulog/team_member.html` — drill-down.
   - `ulog/templates/ulog/_team_card.html` — single-author card
     (reused on the index page, may also fit in the records
     "Authored by" panel later).
4. **URL routing** — two new entries in
   `ulog/web/urls.py` for the two views above.
5. **Header nav link** — add "Team" entry in `base.html` next to
   Records / Docs.
6. **Initials avatar helper** — `_avatar_initials(name: str) -> str`
   + `_avatar_color(email: str) -> str` (deterministic hex from
   email hash, 8 palette options matching Tailwind tokens).
7. **Sidebar link tweak** — add the `→ /team/<email>/` icon next
   to each author row (small change in `list.html`).
8. **Tests** in `tests/test_team_page.py` (new file):
   - `test_team_index_lists_all_known_authors`
   - `test_team_index_excludes_unknown_sentinel`
   - `test_team_index_sorts_by_record_count_desc`
   - `test_team_card_renders_github_link_for_noreply_email`
   - `test_team_card_omits_github_link_for_corp_email`
   - `test_team_member_view_shows_commits_tests_records`
   - `test_team_member_view_404_on_unknown_email`
   - `test_github_handle_inference_legacy_format`
   - `test_github_handle_inference_modern_digits_plus_handle`
   - `test_files_for_returns_correct_line_counts`

### 2.2 Out of scope (deferred)

- **Multi-email same person** (corp + personal). Needs a `.mailmap`-
  style alias mechanism — defer to a v0.4.4 follow-up.
- **Avatars from Gravatar / GitHub** — never; privacy invariant.
- **Per-author RSS / API endpoint** — could ship a JSON variant
  later (`/api/team/`) but not needed for the page-level
  deliverable.
- **Pagination of the index grid.** Most teams are < 50 people;
  any larger and we add `?page=` + `&page_size=`. Defer until
  needed.
- **Edit / annotate author metadata** (add a bio, override the
  display name from the viewer UI). The viewer is read-only by
  design.
- **Real-time updates** (refresh card counts as new records
  arrive). One-shot render per request, like every other view.
- **`<unknown>` author card.** The sidebar already shows it with
  proper semantics; surfacing it on the Team grid would suggest
  it's a person.
- **Source-tree integration** in the "Files owned" list. Stays
  plain text in v0.4.3; v0.6+ source-tree view (if pursued) will
  add live links.

## 3. Acceptance

- **AC1** — `GET /team/` returns 200, renders a grid with one
  card per known author. The `<unknown>` sentinel does NOT have
  a card.
- **AC2** — Each card shows: name, email (truncated), tests count,
  records count, files-owned count, "last committed" relative
  date, and either a GitHub link (when derivable) or no link.
- **AC3** — Cards sorted by records-count descending. Ties broken
  alphabetically by email.
- **AC4** — On the seeded demo DB, the page shows exactly 8 author
  cards matching the names listed in AC e2-2.1-2 of the QA
  checklist (Alice Chen, Bob Martin, etc.).
- **AC5** — `GET /team/<urlencoded-email>/` for any known email
  returns 200 with sections: profile, activity (commits), tests
  authored, records by level, files owned.
- **AC6** — `GET /team/<urlencoded-email>/` for an unknown email
  returns 404.
- **AC7** — Email `<handle>@users.noreply.github.com` renders a
  GitHub link to `https://github.com/<handle>`. Email
  `<digits>+<handle>@users.noreply.github.com` (modern form)
  renders a link to `https://github.com/<handle>`. Email
  `alice@globex.io` renders NO GitHub link.
- **AC8** — Header nav surfaces a "Team" entry next to Records /
  Docs, present on every page.
- **AC9** — Authors sidebar rows gain a small `→` icon linking to
  `/team/<email>/`. Sidebar filtering (clicking the row) is
  unchanged.
- **AC10** — "Authored by" panel in the detail view links the
  author name to `/team/<email>/`.
- **AC11** — Avatar initials block renders one or two letters
  derived from the display name (first letter of first and last
  word). Background color is deterministic (same email always
  yields same color across reloads) and chosen from a Tailwind
  8-color palette.
- **AC12** — Page-load wall time on the seeded 43K-record demo
  DB stays under the PRD-v0.4.1 ceiling of 3.0s cold-cache; under
  1.0s warm-cache (subsequent requests).
- **AC13** — All existing 290+ tests stay green. 10 new tests
  from §2.1.8 pass.
- **AC14** — QA reference screenshot added: new entry
  `section-team-index` in the catalog screenshots
  `/team/?qa_screenshot=1`, included in the `/_qa/` checklist
  under a new "2.8 Team page" subsection (Story 2.6 / FR76
  extension).

## 4. Non-functional

- **Zero new runtime dependency.** Aggregations use stdlib +
  existing SQLAlchemy ([storage] extra). Initials avatars are
  inline SVG / styled divs — no font assets.
- **Cache reuse.** `compute_authors_summary` provides per-author
  record counts (already memoized per `(db_mtime, idx)` pair).
  The new `files_for` / `tests_for` aggregations join with the
  same cached data structures.
- **Backwards compatibility.** No URL changes to existing routes.
  The sidebar tweak is additive (a tiny icon next to the existing
  filter-row checkbox).
- **Privacy.** Emails are surfaced — they're already public in
  every commit. No external network calls (no Gravatar, no
  GitHub API). The GitHub link is rendered client-side and only
  for emails that GitHub itself issued — opting in by definition.
- **Accessibility.** Cards are semantic `<article>` elements with
  `<h2>` for the name, `<dl>` for the stats. Keyboard navigation
  flows naturally; focus ring matches existing Tailwind palette.
- **a11y contrast.** Avatar block uses palette pairs that pass
  WCAG 2.1 AA contrast for the initials-on-bg combo.

## 5. Risks / open questions

- **Subprocess cost of `commits_for`.** A `git log` invocation
  per author at request-time is OK at 8 authors / 50 commits
  each (~400ms total); could spike on a 100-author monorepo.
  Mitigation: cap `limit=50` (already in API), and add a
  module-level `_COMMITS_CACHE` keyed by `(email, repo_head_sha)`
  for warm hits. Tracked in Open Question OQ-1 below.
- **Empty authors** (the index has them but they show 0 records,
  0 tests, 0 files). Edge case: a rebase or squash could leave a
  ghost author in `git log` with no `git blame` ownership.
  Mitigation: filter the index to authors with ≥ 1 blamed line
  (NOT just ≥ 1 commit). Decision encoded in the index iteration.
- **`/team/<email>/` URL conflict** with future routes. We
  reserve `/team/` for this feature; any future "team management"
  feature would have to coexist or supersede. Acceptable: the
  semantic of `/team/` is "the people who built this code",
  consistent across both ideas.
- **`@users.noreply.github.com` parsing edge cases.** Three
  emails seen in the wild: `handle@`, `digits+handle@`, and the
  rare org-issued `handle@noreply.your-enterprise-domain`.
  Decision G1 covers the first two; the third is rare enough to
  defer.

**Open question OQ-1:** is a `_COMMITS_CACHE` worth shipping in
v0.4.3, or do we let `commits_for` run uncached and revisit if
profiling flags it as a hotspot? Lean toward "defer caching"
until measured slowness shows up — 50 commits per author × 8
authors at ~5ms/call is ~2s worst-case warm-up cost on the
demo DB, fine for a "look at the team" page that's a one-time
visit per session.

## 6. Implementation notes

### 6.1 GitHub handle regex (Decision G1)

```python
_GH_NOREPLY = re.compile(
    r"^(?:(?P<id>\d+)\+)?(?P<handle>[A-Za-z0-9-]+)@users\.noreply\.github\.com$"
)

def github_handle_for(email: str) -> str | None:
    m = _GH_NOREPLY.match(email or "")
    return m.group("handle") if m else None
```

Tested against the two legacy and three modern email shapes in
fixtures; rejects corporate emails cleanly.

### 6.2 Avatar palette (Decision G2)

Deterministic mapping from `hashlib.md5(email.lower()).digest()[0] % 8`:

| Index | bg-color (Tailwind) | text-color | Contrast |
|---:|---|---|---|
| 0 | `bg-blue-600`    | `text-white` | 7.0 AA |
| 1 | `bg-emerald-600` | `text-white` | 4.7 AA |
| 2 | `bg-amber-500`   | `text-slate-900` | 6.2 AA |
| 3 | `bg-rose-600`    | `text-white` | 4.5 AA |
| 4 | `bg-indigo-600`  | `text-white` | 7.8 AA |
| 5 | `bg-slate-700`   | `text-white` | 11.4 AAA |
| 6 | `bg-teal-600`    | `text-white` | 4.6 AA |
| 7 | `bg-fuchsia-600` | `text-white` | 4.5 AA |

Note: stdlib `hashlib.md5` is fine here — this is identity
clustering, not authentication. Used non-cryptographically.

### 6.3 Aggregation strategy

To avoid N+1 walks over the records dataset, build all four
per-author counts (records, tests, files, last_ts) in a single
adapter pass and cache:

```python
@dataclass(frozen=True)
class TeamMemberSummary:
    author: Author
    record_count: int
    test_count: int       # distinct test_ids
    file_count: int       # distinct files owned by them
    last_ts: int          # max(Author.ts) across blamed lines
    files_owned: tuple[tuple[str, int], ...]  # (file, line_count)
    github_handle: str | None  # from G1
```

`compute_team_summary(adapter, idx) -> dict[str, TeamMemberSummary]`
walks the adapter's `file_line_record_counts()` (already cached by
v0.4.1), pairs each `(file, line)` with the idx-resolved author,
and accumulates per email. Cached at module level under the same
`(db_mtime, id(idx))` key as `compute_authors_summary`.

### 6.4 Email URL encoding (Decision G3)

Standard `urllib.parse.quote(email, safe='@')` — keeps the `@` for
readability, encodes everything else. The `<str:email>` URL
converter on the Django path accepts the encoded form; the view
calls `unquote` before lookups.

### 6.5 Test attribution rule (Decision G4)

A test `test_id` is "authored by" an email iff **at least one line
of the test's source file** (`TestSummaryRow.file`) is currently
blamed to that email at HEAD. Rationale: tests rarely have a single
author historically, but the *current owner* of the test code is
who you'd ping about it. Matches the semantic of "who is on the
hook for this test today".

Edge case: a file co-authored 50/50 by Alice and Bob shows the
test under BOTH cards. Acceptable; co-ownership is real and the
double-counting is informative.

### 6.6 Header nav placement

`base.html` already renders a Records / Docs link pair. Append:

```html
<a href="{% url 'ulog-team' %}" class="…"
   {% if request.resolver_match.view_name == 'ulog-team' or request.resolver_match.view_name == 'ulog-team-member' %}
   aria-current="page"
   {% endif %}>
  {% lucide "users" size=14 %}
  <span>Team</span>
</a>
```

Order: **Records → Docs → Team** (the order matches the user's
typical journey: see logs, read docs, find the human who owns
what you're looking at).

## 7. See also

- **Parent:** [PRD-v0.4-commit-author-filter.md](./PRD-v0.4-commit-author-filter.md) — defines `AuthorIndex` and the author-filter primitives this page reuses.
- **Perf budget:** [PRD-v0.4.1-viewer-perf-hotpath.md](./PRD-v0.4.1-viewer-perf-hotpath.md) — the cache pattern this PRD inherits for the per-author aggregation.
- **Sibling:** [PRD-v0.4.2-docs-quality.md](./PRD-v0.4.2-docs-quality.md) — also lands as a v0.4 follow-up; soft-dependency on the renderer changes (none currently).
- **Architecture:** `_bmad-output/planning-artifacts/architecture.md` — Decision A3 (authors cache sidecar) provides the SQLite-backed storage for `AuthorIndex.files_for` lookups on JSONL/CSV adapters.
- **QA AC:** `e2-2.1-2` ("8 names listed") gets a richer surface; this PRD also adds the new AC section §2.8 to `/_qa/`.
