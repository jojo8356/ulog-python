---
docType: prd
project_name: ulog-python
version: 0.4.0
date: 2026-05-04
author: jojo8356
status: draft v1
parent_prd: PRD-v0.2-storage-and-ui.md
---

# ULog v0.4 — Commit author filter

> Each log record originates from a specific source-file:line. v0.4
> enriches records with the **git commit author** who last touched
> that line (`git blame`-derived) and exposes a **"By author"
> sidebar filter** — drill into "errors in code Johan wrote", "logs
> from Lin's recent additions", etc. Useful for code review, blame
> attribution (in a kind way), and pair-programming retrospectives.

---

## 0. The 30-second pitch

When a multi-author project produces a stack trace, the natural
diagnostic question is: "who wrote this?". Currently the answer
requires:

1. Open the source file at the line.
2. `git blame -L line,line file`.
3. Note the author email + commit hash.
4. Repeat for every relevant log line.

ULog v0.4 collapses this to: **tick "Lin Erwan" in the sidebar →
list filters to logs originating from code Lin authored**. The data
comes from a one-time `git blame` walk over the host repo at startup,
cached to a sidecar table.

Bonus payoff: pair-programming retros where you can answer "did our
refactor break anything?" by filtering ERROR records to the people
who pushed that week.

---

## 1. Vision

### 1.1 Why this exists

`git blame` is one of the most under-used cross-references in the
debugger toolbox because it lives outside the IDE/log-viewer loop.
Engineers use it for one-off questions but rarely as a filter axis.
Once you can filter logs by author, three workflows unlock:

1. **Code review of merged PRs** — "show me ERROR logs from code
   Sara merged this week" → filter on author + time-range.
2. **Onboarding** — a new contributor inherits a bug; filter to the
   person who originally wrote that module to find the right
   reviewer.
3. **Pair programming retros** — at session end, see what your code
   logged across the run, side-by-side with what your partner's code
   logged.

### 1.2 What v0.4 isn't

- A blame tool. We use `git blame`'s output but don't replace
  it. For deep blame archeology (chains, follow-renames, etc.) the
  user opens the IDE.
- A code review tool. No PR comments, no approvals.
- A vanity tool. "Logs by author" is a debugging axis, not a
  scoreboard. The UI does NOT show counts in a way that can be
  abused for performance review.
- An attribution lawyer. No license-aware blame; we just look at git.

### 1.3 Target user (carried + new)

- **Marco** (carried) — solo dev. Author filter shows just his name
  for now; useful when he eventually invites contributors.
- **Lin** (carried) — pipeline integrator. Reads CI artefacts from
  a multi-author team. Filter axis is essential.
- **Sara** (carried) — library developer. Reviews her own changes'
  log impact post-merge.
- **Johan** (NEW) — tech lead of a 5-person team. Uses the author
  filter during quarterly retros to map "where do our logs cluster?"
  by-author; informs refactor priorities.

### 1.4 Success Criteria

| SC | Description |
|---|---|
| SC1 | ≥ 90 % of `(file, line)` pairs from the logs of a representative repo (qlnes, ulog-python) resolve to a non-`<unknown>` author after a clean `--repo` index run. |
| SC2 | The NFR-PERF-30 budget (≤ 5 s indexer / 100 K records / 30-file repo) holds on 3 reference repos: `qlnes`, `ulog-python`, and one external 100 K-LOC repo (`cpython` quick-clone). |
| SC3 | Zero regression of NFR-PERF-31 page-load (≤ 500 ms) when `--no-author-index` is set, measured against the v0.3 baseline on the same fixture. |
| SC4 | The four edge cases listed in §2.3 each have at least one passing test in `tests/test_author_index.py`. |

---

## 2. Scope (v0.4)

### 2.1 In scope

#### 2.1.1 Author-attribution indexer

A startup-time + on-demand indexer:

1. On `ulog-web <path> --repo <git-root>` (default: try `cwd`),
   the script walks the loaded log records, collects unique
   `(file, line)` pairs.
2. For each unique pair, runs `git blame -L line,line --porcelain
   path/to/file` against `<git-root>` and parses the author email
   + name + commit hash.
3. Caches the result in a sidecar `authors` table next to the main
   `logs` table (or as a JSON file alongside JSONL/CSV inputs).
4. Updates the cache lazily on records added since last indexing.

The indexer is **opt-in via `--repo`** because it only makes sense
when the loaded logs come from code in a known repo.

#### 2.1.2 Author sidebar filter

New sidebar section under "Files":

```
AUTHORS
☐ Johan Nalin (johan@…)         (412)
☐ Lin Wong (lin@…)              (89)
☐ Sara Patel (sara@…)            (24)
☐ <unknown> (no git blame data) (3)
```

Multi-select with OR semantics (tick Johan + Sara → records
authored by either). Counts follow the v0.2.1 ghost-count rules —
each row shows what'd be added if you ticked it.

#### 2.1.3 Detail-view "Authored by" panel

Open a record's detail view; new sub-section:

```
Authored by  Lin Wong <lin@example.com>  (a3f7c12)
              committed 2026-04-28, 6 days ago
              [view all records from this author]
              [view diff: a3f7c12]
```

The "view diff" link `git show a3f7c12 -- path/to/file:line` opens
in a small modal (rendered via the same minimal markdown renderer
v0.2 ships) — no JS dep beyond what's already loaded.

#### 2.1.4 Time-window filter integration

Author filter composes with the existing time-range — "show me
records authored by Lin AND emitted in the last 24h" answers
"what is Lin's recent code logging?".

A subtlety: the author of CODE doesn't change with log emission
time. v0.4 makes this explicit: the author is sourced from
`git blame` (last to modify the line), NOT from the time of log
emission. Documented in the docs page.

#### 2.1.5 CLI flag + config

```bash
# Auto-detect repo via cwd
ulog-web ./logs.sqlite

# Explicit repo (e.g. log file is in a different dir than the source)
ulog-web --repo /path/to/qlnes ./logs.sqlite

# Skip the indexer (faster startup, no author filter)
ulog-web --no-author-index ./logs.sqlite
```

### 2.2 Explicit non-goals (deferred to v0.5+)

- **Co-author detection**. `Co-Authored-By:` trailers in commit
  messages aren't parsed in v0.4 — only the primary author. v0.5
  may add.
- **Cross-repo blame**. If the log file references a file outside
  `--repo`, that record gets `<unknown>` author. v0.5 multi-repo.
- **Visual blame heatmap**. No "20% of errors come from this person"
  pie chart — explicitly out of scope per the "vanity tool" non-goal.
- **Mailmap normalization**. v0.4 does NOT apply
  `.mailmap` rewrites (multiple emails → canonical name). v0.5.
- **Real-time blame as code changes**. v0.4 caches at startup +
  refresh on demand. WebSocket-style "files changed, refresh blame"
  is v0.6.
- **Inline diff viewer**. The "view diff" link spawns the user's
  configured `git show` — no in-UI syntax-highlighted diff. v0.5.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| **Line deleted** — log emitted at `foo.py:280` but `foo.py` now has 200 lines | Record gets `<unknown>` author with diagnostic field `blame_skip_reason="line-out-of-range"`. Archeology via `git log -S` is non-goal (v0.5+). |
| **File renamed** | `git blame --follow -C -M` is used on first attempt. If rename detection fails, record gets `<unknown>` + `blame_skip_reason="file-not-tracked"`. |
| **Squashed / rebased commit** — cached `commit_sha` no longer reachable after `git gc` | `/diff/<sha>` validates via `git rev-parse --verify` and returns a friendly 404; the cached author + date stay visible in the detail panel. |
| **Submodule path** — file under a `.gitmodules`-tracked path | Blamed against the **submodule's** git history (auto-detect via `git rev-parse --show-toplevel` from the file's parent dir). Cross-repo blame across the superproject remains a v0.5+ non-goal (§2.2). |
| **No git repo at `--repo`** | Covered by FR74: all records `<unknown>` + stderr warn at startup. |

---

## 3. Functional Requirements

### 3.1 Indexer

| FR | Description |
|---|---|
| FR70 | `ulog.web.viewer.blame.AuthorIndex(repo_root)` exposes `author_for(file, line) -> Author | None`. Uses `git blame --porcelain` under the hood; parses with stdlib (no GitPython dep). |
| FR71 | Index built lazily: first time `ulog-web` loads records, it walks unique `(file, line)` pairs and runs `git blame` per file (one process per file, batched by `-L` ranges). Progress printed to stderr. |
| FR72 | Cache table `authors`: `(file, line, author_name, author_email, commit_sha, commit_ts)`. PK = `(file, line)`. Persisted in the same SQLite as logs, or in a sidecar `<logs>.authors.sqlite` for JSONL/CSV sources. |
| FR73 | `--no-author-index` skips the indexer; the sidebar section just hides. |
| FR74 | `--repo PATH` sets the git root explicitly. Default: walk parents of cwd until a `.git/` is found; if none, treat all records as `<unknown>` author and warn. |
| FR75 | If a file in the records is not present in the repo (e.g. logs from a different machine), the record's author is `<unknown>`. The author count `(<unknown>: N)` is shown. |

### 3.2 Sidebar UI

| FR | Description |
|---|---|
| FR76 | New "Authors" section between "Files" and "Time range". Lists every distinct author (name + email truncated to 20 chars + ghost-count). |
| FR77 | Multi-select with OR. URL query string: `?author=johan@example.com&author=lin@example.com`. |
| FR78 | "Show unknown" checkbox at the bottom toggles `<unknown>` records (default: ON, so unknowns aren't accidentally hidden). |
| FR79 | Counts ghost-mode (per v0.2.1) — author count ignores its own filter axis. |

### 3.3 Detail-view panel

| FR | Description |
|---|---|
| FR80 | Detail-view shows "Authored by" panel below "Context": name + email + commit short-sha + relative date (`6 days ago`) + 2 links (all records from this author, view diff). |
| FR81 | "View diff" link triggers `git show <sha>` in a server-side handler (`/diff/<sha>`) which streams `git show` output rendered as code. Server validates the sha is reachable in `--repo` (avoid arbitrary command injection). |

### 3.4 Performance

| FR | Description |
|---|---|
| FR82 | Indexer caches per `(file, line)` pair; subsequent runs reuse the cache when the file's mtime hasn't changed. Re-blame on file change. |
| FR83 | One `git blame` invocation per (unique-file, repo) — uses `-L` ranges to minimize forks. For 100K records spanning ~30 files: ≤ 30 forks at startup. |

---

## 4. Non-functional requirements

| NFR | Budget |
|---|---|
| NFR-PERF-30 | Indexer adds ≤ 5 s to startup for a 100K-record DB on a 30-file repo. Optional `--no-author-index` opts out. |
| NFR-PERF-31 | UI page-load with author filter active stays ≤ 500 ms (the join is on the indexed `authors` table). |
| NFR-DEP-30 | No new Python dep (uses subprocess + stdlib only). `git` binary on PATH required if `--repo` is set or auto-detected. |
| NFR-COMPAT-30 | Linux + macOS + Windows. Windows: `git` from Git for Windows is enough; no special handling. |
| NFR-DOC-30 | New `/docs/author-filter.md` page covering: how it works, what `<unknown>` means, the "code author vs commit author" distinction, the worked example "find errors in code Lin wrote this week". |
| NFR-SEC-30 | The `/diff/<sha>` view validates the sha is reachable in `--repo` via `git rev-parse --verify <sha>` before invoking `git show`. Rejects shell-special characters in the sha (must match `[0-9a-f]{4,40}`). |

---

## 5. API surface (sketch)

### 5.1 Programmatic AuthorIndex

```python
from ulog.web.viewer.blame import AuthorIndex

idx = AuthorIndex(repo_root="/path/to/qlnes")
idx.build()
author = idx.author_for("qlnes/audio/renderer.py", 280)
# Author(name="Johan", email="johan@example.com", sha="a3f7c12", ts=...)
```

### 5.2 CLI

```bash
# Auto-detect (most users)
ulog-web ./logs.sqlite

# Explicit repo path
ulog-web --repo /path/to/qlnes ./logs.sqlite

# Skip the indexer (faster startup, no author filter)
ulog-web --no-author-index ./logs.sqlite
```

### 5.3 URL filter syntax

```
http://127.0.0.1:8765/?author=johan@example.com&author=lin@example.com&level=ERROR
```

---

## 6. Worked examples

### 6.1 "Find errors in code Lin wrote this week"

1. Tick **ERROR** in Level.
2. Tick **Lin Wong** in Authors.
3. Set `from = 2026-04-28T00:00:00Z` in Time range.
4. → list shows just the relevant records.
5. Click any → detail view shows the assertion, traceback, AND
   "Authored by Lin Wong (commit a3f7c12, 6 days ago)".

### 6.2 "Pair-programming retro: what did our session log?"

After a 2-hour Marco+Sara pairing session ending at 17:00:

1. Set time range from `15:00Z` to `17:00Z`.
2. Tick Marco AND Sara in Authors.
3. → side-by-side records from both contributors during the session.
4. Filter "Failed only" (v0.3) shows specifically the bugs they hit.

### 6.3 "Who wrote this confusing log message?"

1. Search `q = "cycle drift exceeded budget"`.
2. List → 1 result.
3. Click → "Authored by Johan, commit a3f7c12, 6 days ago".

---

## 7. Roadmap continuation

- **v0.5** — co-authors + mailmap + multi-repo support.
- **v0.6** — real-time blame (file watcher).
- **v0.7** — diff-aware filtering ("show records first emitted after
  commit X").
- **v1.0** — feature freeze.

---

## 8. Open questions

1. **Privacy in shared logs**. A log file shared with a vendor would
   leak emails. Add `--anonymize-authors` flag that hashes name +
   email? v0.5 if anyone asks.
2. **Stale cache invalidation**. We invalidate by file mtime, but
   `git checkout` doesn't always touch mtimes (depends on
   `core.checkstat`). Workaround: `--rebuild-author-index` flag. Or
   key cache by file+commit-sha-of-HEAD instead of mtime.
3. **Performance on huge files**. `git blame` on a 10K-line file is
   slow. v0.4 batches by file+line-ranges; v0.5 may add streaming
   parse to start showing partial results sooner.
4. **GUI-blame viewer integration**. macOS' `gitup`, Windows'
   GitExtensions, Linux's `gitg` — we don't try to launch any of
   them. Just `git show` in a modal. Acceptable.

---

## 9. Definition of Done — v0.4

- [ ] `ulog/web/viewer/blame.py` with `AuthorIndex`.
- [ ] CLI flags `--repo`, `--no-author-index`,
       `--rebuild-author-index`.
- [ ] UI sidebar Authors section with multi-select + ghost counts.
- [ ] Detail-view "Authored by" panel.
- [ ] `/diff/<sha>` server view with sha validation + `git show`.
- [ ] `/docs/author-filter.md` page.
- [ ] ≥ 15 new tests covering: indexer correctness on a synthetic
       repo, cache invalidation on file mtime, sha validation,
       sidebar filter wiring.
- [ ] Tag `v0.4.0` + push.
