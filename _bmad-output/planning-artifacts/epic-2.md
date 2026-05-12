---
docType: epic
epic_num: 2
title: v0.4 — Author attribution
project_name: ulog-python
source: extracted from _bmad-output/planning-artifacts/epics.md (lines 781-1023)
status: done
shipped: v0.4
stories_canonical: 11
stories_added_via_correct_course: 1
retrospective: _bmad-output/implementation-artifacts/epic-2-retro-2026-05-06.md
---

# Epic 2: v0.4 — Author attribution

When opening a log file in the viewer with a known git repo, every record is enriched with the git author of the source line. The user can filter records by author, see "Authored by Lin Wong (commit a3f7c12, 6 days ago)" in the detail panel, and click "view diff" to see the originating commit.

### Story 2.1: `AuthorIndex` API + git blame --porcelain parsing

As a developer integrating author attribution programmatically,
I want `AuthorIndex(repo_root).author_for(file, line) -> Author | None` to resolve any (file, line) pair to a git author via `git blame --porcelain`,
So that I can query authorship without using the viewer.

**Acceptance Criteria:**

**Given** a valid git repo and `(file, line)` referring to tracked code
**When** `idx.author_for("path/to/file.py", 42)` is called
**Then** an `Author(name, email, sha, ts)` is returned (FR70).

**Given** the same `(file, line)` is queried twice
**When** the file's mtime hasn't changed
**Then** the second call uses the cached result (FR82) — no `subprocess.run(['git', 'blame'])` invocation.

**Given** a repo with 100K records spanning 30 unique files
**When** `idx.build()` is invoked
**Then** ≤ 30 forks of `git blame` are observed (FR83).

**Given** the implementation
**When** the source is reviewed
**Then** no `import git` (GitPython) appears anywhere — only `subprocess` + stdlib parsing.

---

### Story 2.2: CLI flags `--repo`, `--no-author-index`, `--rebuild-author-index`

As a viewer user,
I want CLI flags to control author indexing (auto-detect / override / skip / force-rebuild),
So that I can adapt the viewer to different repo layouts and refresh strategies.

**Acceptance Criteria:**

**Given** `ulog web ./logs.sqlite` (no flag)
**When** the viewer starts
**Then** it walks parents of cwd until `.git/` is found and uses that as repo root (FR74).

**Given** no `.git/` is found in cwd parents
**When** the viewer starts
**Then** all records' author resolves to `<unknown>` and stderr prints a one-line warning (FR74).

**Given** `ulog web --repo /path/to/qlnes ./logs.sqlite`
**When** the viewer starts
**Then** `/path/to/qlnes` is used as the git root (FR74).

**Given** `ulog web --no-author-index ./logs.sqlite`
**When** the viewer starts
**Then** the indexer is skipped and the Authors sidebar section is hidden (FR73).

**Given** `ulog web --rebuild-author-index ./logs.sqlite`
**When** the viewer starts
**Then** the cache is invalidated and rebuilt from scratch.

---

### Story 2.3: Lazy index build with stderr progress

As a viewer user opening a 100K-record DB for the first time,
I want the index to build lazily on viewer load with progress printed to stderr,
So that I see what's happening during the ≤5s startup budget.

**Acceptance Criteria:**

**Given** a fresh viewer launch with `--repo` set and no existing cache
**When** the index builds
**Then** progress lines are printed to stderr like `ulog: indexing authors... 30 files, 12500/100000 records (12%)` (FR71).

**Given** the index build completes
**When** the budget is measured
**Then** total wall-time ≤ 5s on a 100K-record DB / 30-file repo (NFR-PERF-30).

---

### Story 2.4: `authors` cache table + sidecar SQLite for JSONL/CSV

As a viewer user opening a JSONL or CSV log file,
I want author cache to live in a sidecar `<logs>.authors.sqlite` next to the source file,
So that subsequent loads reuse the cache without re-blaming.

**Acceptance Criteria:**

**Given** an SQLite log DB at `./logs.sqlite` with author indexing enabled
**When** the index builds
**Then** an `authors` table exists in the SAME DB with PK `(file, line)` and columns `(author_name, author_email, commit_sha, commit_ts)` (FR72).

**Given** a JSONL log file at `./logs.jsonl` with author indexing enabled
**When** the index builds
**Then** a sidecar SQLite `./logs.jsonl.authors.sqlite` is created with the same schema (Decision A3).

**Given** the same JSONL file is reloaded after a fresh build
**When** the viewer starts
**Then** no new `git blame` invocation occurs (cache reused, mtime checked).

---

### Story 2.5: `<unknown>` author handling

As a viewer user with logs that reference files not in the current repo,
I want those records to show `<unknown>` in the Authors sidebar with a count,
So that I can include or exclude them deliberately.

**Acceptance Criteria:**

**Given** a record references `external/lib.py:42` which is not present in `--repo`
**When** the index queries for that pair
**Then** `idx.author_for(...)` returns `None`
**And** the record's author display is `<unknown>` (FR75).

**Given** records with `<unknown>` author exist
**When** the Authors sidebar renders
**Then** an `<unknown> (N)` entry appears with the count of such records.

---

### Story 2.6: Authors sidebar section with ghost counts

As a viewer user filtering by author,
I want a multi-select Authors sidebar section that honors the v0.2.1 ghost-count contract,
So that ticking authors doesn't zero out other authors' counts.

**Acceptance Criteria:**

**Given** the Authors section shows 4 authors with counts (412, 89, 24, 3)
**When** the user ticks "Lin Wong" alone
**Then** the records list filters to Lin's records, but the OTHER authors' counts remain non-zero (computed against all-filters-EXCEPT-author per PRD-v0.2.1) (FR79).

**Given** the section
**When** rendered
**Then** it sits between "Files" and "Time range" sections (FR76).

---

### Story 2.7: Multi-select OR + URL query string + "Show unknown"

As a viewer user combining author filters,
I want multi-select with OR semantics (tick Johan + Sara → records by either), persisted in URL,
So that I can share the URL of a specific author combination.

**Acceptance Criteria:**

**Given** "Johan" and "Sara" are ticked
**When** the page reloads
**Then** records filter to `author IN (johan@..., sara@...)`
**And** the URL contains `?author=johan@...&author=sara@...` (FR77).

**Given** "Show unknown" checkbox (default ON)
**When** unchecked
**Then** records with `<unknown>` author are hidden from the list (FR78).

---

### Story 2.8: Detail-view "Authored by" panel

As a viewer user investigating a specific record,
I want a detail-view sub-section with the author's name, email, commit short-sha, relative date, and links to "all records from this author" + "view diff",
So that I can pivot from one record to context.

**Acceptance Criteria:**

**Given** a record's detail view with author resolved
**When** the page renders
**Then** the "Authored by" panel shows: name + truncated email + 7-char short-sha + relative date (`6 days ago`) + 2 links (FR80).

**Given** the "view diff" link
**When** clicked
**Then** it navigates to `/diff/<commit_sha>`.

---

### Story 2.9: `/diff/<sha>` view with sha validation

As a viewer user clicking "view diff",
I want the server to validate the sha (hex regex + `git rev-parse --verify`) and render `git show <sha>` output safely,
So that no shell injection or arbitrary command is possible.

**Acceptance Criteria:**

**Given** a request to `/diff/a3f7c12abc`
**When** the server handles it
**Then** the sha is validated against `[0-9a-f]{4,40}` first (NFR-SEC-30, FR81).

**Given** an invalid sha (e.g. `abc; rm -rf /`)
**When** the server validates it
**Then** the request returns 400 Bad Request without invoking any subprocess.

**Given** a valid sha
**When** the server runs `git rev-parse --verify <sha>` followed by `git show <sha>`
**Then** the output is HTML-escaped and rendered in `<pre class="font-mono whitespace-pre overflow-x-auto">` (Decision D4).

**Given** the sha is valid hex but unreachable in the repo
**When** the server runs `rev-parse --verify`
**Then** it returns 404 with a friendly message.

---

### Story 2.10: 4 PRD-v0.4 §2.3 edge cases as tests

As a release manager,
I want each of the 4 PRD-v0.4 §2.3 edge cases (line deleted, file renamed, squashed/rebased, submodule, no-git) covered by ≥1 test in `tests/test_author_index.py`,
So that the indexer's behavior on git pathologies is regression-protected.

**Acceptance Criteria:**

**Given** a synthetic repo where a file shrunk and a record references a now-out-of-range line
**When** `idx.author_for(...)` is called
**Then** it returns `None` and the record gets `blame_skip_reason="line-out-of-range"` (PRD-v0.4 §2.3).

**Given** a synthetic repo with `git mv` of a file
**When** `idx.author_for(...)` is called on the new path with a record from the old path
**Then** `git blame --follow -C -M` is used and resolves the author correctly.

**Given** a cached `commit_sha` no longer reachable after `git gc`
**When** `/diff/<sha>` is requested
**Then** `git rev-parse --verify` fails and a 404 is returned with the cached author/date still visible in the detail panel.

**Given** a file under a `.gitmodules`-tracked path
**When** `idx.author_for(...)` is called
**Then** the blame runs against the submodule's git history.

**Given** `--repo` points at a directory with no `.git`
**When** the viewer starts
**Then** all records get `<unknown>` author and a stderr warning is printed (FR74).

---

### Story 2.11: Doc page `/docs/author-filter.md`

As a new author-filter user,
I want a doc page covering how it works, what `<unknown>` means, the "code author vs commit author" distinction, and a worked example,
So that I understand the feature without reading the PRD.

**Acceptance Criteria:**

**Given** the viewer is running
**When** the user navigates to `/docs/author-filter/`
**Then** the page renders covering: indexer mechanics, `<unknown>` semantics, code-author-vs-commit-author note, "find errors in code Lin wrote this week" worked example (NFR-DOC-30).

---

## Annex — Stories added via correct-course (post-epic perf patch)

Le slot 2.12 a été sauté pendant la numérotation. La seule story post-epic est 2.13.

### Story 2.13: Viewer perf hotpath — memoize + GROUP BY for AuthorsSummary

Découverte le 2026-05-06 quand l'utilisateur a généré une DB démo de 43K records : la page mettait 4,2 s à charger (cold) et 5,4 s avec filtre auteur. Le bottleneck était `compute_authors_summary` qui parcourait tous les records à chaque requête. Patch : memoization + GROUP BY SQL pour rester sous la cible PRD-v0.4.1 (page-load < 3 s).

→ Spec : https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/implementation-artifacts/2-13-perf-hotpath-authors-summary-memoize.md

---

## References

- **Retrospective :** https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/implementation-artifacts/epic-2-retro-2026-05-06.md
- **Source PRD :** https://github.com/jojo8356/ulog-python/blob/main/docs/prds/PRD-v0.4-commit-author-filter.md
- **Perf patch PRD :** https://github.com/jojo8356/ulog-python/blob/main/docs/prds/PRD-v0.4.1-viewer-perf-hotpath.md
- **Architecture :** https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/planning-artifacts/architecture.md
- **Monolithic epics file :** https://github.com/jojo8356/ulog-python/blob/main/_bmad-output/planning-artifacts/epics.md — Epic 2 lives at lines 781–1023
