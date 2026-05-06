# Author filter (v0.4)

When a multi-author project produces a stack trace, the natural diagnostic
question is: "who wrote this?". ULog v0.4's **author filter** answers it
directly inside the viewer — tick a name in the **AUTHORS** sidebar and
the records list narrows to logs originating from code that author
last touched (per `git blame`).

## How it works

On viewer startup, `ulog-web` runs a one-time `git blame --porcelain`
walk over the unique `(file, line)` pairs in your loaded log:

1. Walks loaded records, collects unique `(file, line)` pairs.
2. Runs `git blame -L <line>,<line> --porcelain <file>` per file
   (one process per file, batched via multiple `-L` ranges) — typically
   ≤ 30 forks for a 100K-record / 30-file log.
3. Caches the result in an `authors` table (same SQLite as `logs` for
   `.sqlite` sources; sidecar `<logs>.authors.sqlite` for JSONL/CSV).
4. Reuses the cache on subsequent loads; invalidated only when the
   source file's mtime changes (or `--rebuild-author-index` is passed).

## CLI flags

```bash
# Auto-detect: walks parents of cwd until .git/ is found
ulog-web ./logs.sqlite

# Explicit repo path
ulog-web --repo /path/to/repo ./logs.sqlite

# Skip the indexer entirely (faster startup, hides the AUTHORS section)
ulog-web --no-author-index ./logs.sqlite

# Force rebuild (drops the cached authors table first)
ulog-web --rebuild-author-index ./logs.sqlite
```

## What "&lt;unknown&gt;" means

Records whose source `(file, line)` doesn't resolve to a tracked git
author are bucketed under **&lt;unknown&gt;** in the sidebar. This happens
when:

- The file is not tracked in `--repo` (logs from a different machine).
- The line is now out-of-range (e.g. logs emitted at line 280 but the
  file has since been shrunk to 200 lines).
- The file has been deleted from the working tree.
- The file has been renamed (v0.4 doesn't follow renames; v0.5+ may).

`<unknown>` records are **shown by default** (the "Show unknown"
checkbox at the bottom of AUTHORS is ticked). Untick it to hide them.

## Code author vs commit author

The author shown is the **code author** of the source line, per
`git blame` — i.e. the person who last *touched* that line. This is
NOT the same as the **commit author** of any specific record. If you
emit a log from `foo.py:42` and `foo.py:42` was last modified by Alice
in commit `a3f7c12`, ULog attributes the record to Alice, regardless of
who is currently running the program.

The "view diff" link in the detail panel opens `git show <sha>` so you
can see the full commit that introduced that line.

## Multi-select OR + URL

Tick "Alice" + "Bob" → records by either. The selection is persisted
in the URL: `?author=alice@example.com&author=bob@example.com`. Share
the URL to share the filter.

## Worked example: "Find errors in code Lin wrote this week"

1. Open the viewer: `ulog-web ./logs.sqlite`
2. Tick **ERROR** in the Level sidebar (top-left).
3. Tick **Lin Wong** in the Authors sidebar.
4. Set the time range to "from this week" (e.g. `2026-05-01T00:00:00Z`).
5. Read what's left: errors in code Lin authored this week.

## Performance

- Indexer adds ≤ 5s to startup for a 100K-record log on a 30-file repo
  (NFR-PERF-30).
- Page load with author filter active stays ≤ 500ms once the index is
  built (NFR-PERF-31).
- Subsequent launches reuse the cache → near-instant startup.

## Security

- The `/diff/<sha>/` endpoint validates `<sha>` against `^[0-9a-f]{4,40}$`
  before invoking any subprocess. Shell metacharacters are structurally
  impossible.
- `git rev-parse --verify` confirms the sha is reachable in `--repo`
  before `git show` runs. Unknown shas return 404, not 500.
- All `subprocess.run` invocations use list args + `shell=False` (no
  shell expansion). Path separator `--` blocks ref/path ambiguity.

## No new dependency

The whole feature uses `subprocess` + stdlib parsing. **No GitPython,
no pygit2** (NFR-DEP-30). The `git` binary on PATH is the only
external requirement.

## Troubleshooting

**"records will show &lt;unknown&gt; author" warning at startup**
: `cwd` has no `.git/` ancestor. Pass `--repo PATH` explicitly or
  `--no-author-index` to silence.

**"sha not reachable in &lt;repo&gt;" on /diff/**
: The cached commit was garbage-collected after `git gc` or rebase.
  The cached author + date stay visible in the detail panel; only the
  diff is lost.

**No AUTHORS sidebar block visible**
: Either you passed `--no-author-index` or no `.git/` was detected at
  startup. Check the stderr output of `ulog-web` for the warning line.

**Indexer is slow**
: For 100K records / 30 files the budget is ≤ 5s. If you exceed that,
  either (a) your repo has many more unique files in the log, or (b)
  you're on slow storage. Run with `--rebuild-author-index` once after
  upgrades, then let the cache do its work.
