# Story 2.2: CLI flags `--repo`, `--no-author-index`, `--rebuild-author-index`

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-2-cli-flags-repo-no-author-index-rebuild-author-index`
**Implements:** FR73 (`--no-author-index`), FR74 (`--repo` + auto-detect via parent walk + `<unknown>` fallback warning)
**Source:** PRD-v0.4 §3.1 FR73-74, §5.2; epics.md Story 2.2; architecture.md (CLI conventions)
**Built on:** Story 2.1 (`AuthorIndex` API). The flags here ARE the user-facing entry to that API.

## Story

As a **viewer user with logs from various repos (or none)**,
I want **CLI flags to control author indexing — auto-detect / override repo / skip / force-rebuild**,
so that **the viewer adapts to different repo layouts and refresh strategies without me editing code or env vars manually.**

## Acceptance Criteria

### AC1 — Auto-detect: walk parents of `cwd` until `.git/` is found (FR74)

**Given** `ulog-web ./logs.sqlite` (no flag), invoked from a working directory inside a git tree
**When** the CLI starts
**Then** the parent walk finds the nearest ancestor with `.git/` and uses it as `--repo`. The repo path is exported via `ULOG_AUTHOR_REPO` env var for the Django process.

### AC2 — Auto-detect: no `.git/` → warn on stderr + skip indexing (FR74)

**Given** `ulog-web ./logs.sqlite` invoked from a directory with NO `.git/` ancestor
**When** the CLI starts
**Then** stderr prints exactly one warning line: `ulog-web: no git repo detected (cwd has no .git/ ancestor); records will show <unknown> author. Use --repo PATH or --no-author-index to silence.`. `ULOG_AUTHOR_REPO` is NOT set.

### AC3 — `--repo PATH` overrides auto-detect (FR74)

**Given** `ulog-web --repo /some/path ./logs.sqlite`
**When** the CLI starts
**Then** `ULOG_AUTHOR_REPO` is set to the resolved absolute path of `/some/path`. Auto-detect is bypassed entirely. If `/some/path/.git/` does NOT exist, stderr prints `ulog-web: --repo /some/path has no .git/ subdirectory; records will show <unknown>` but the viewer still starts.

### AC4 — `--no-author-index` skips indexing (FR73)

**Given** `ulog-web --no-author-index ./logs.sqlite`
**When** the CLI starts
**Then** `ULOG_AUTHOR_INDEX_DISABLED=1` is set. The Authors sidebar section will hide (Story 2.6's burden); the indexer never runs.

### AC5 — `--rebuild-author-index` forces a fresh build

**Given** `ulog-web --rebuild-author-index ./logs.sqlite`
**When** the CLI starts
**Then** `ULOG_AUTHOR_INDEX_REBUILD=1` is set. The cache is invalidated by the Django side at request time (Story 2.4's burden — for now, just plumb the flag).

### AC6 — `--no-author-index` and `--rebuild-author-index` are mutually exclusive

**Given** `ulog-web --no-author-index --rebuild-author-index ./logs.sqlite`
**When** the CLI starts
**Then** argparse raises an error and exit code is non-zero.

### AC7 — Tests cover AC1-AC6 in `tests/test_cli_repo_flags.py`

**Given** the new test file
**When** run via `pytest`
**Then** ≥ 6 tests cover each AC. Tests use `tmp_path` + `git init` for AC1, AC3; use `pytest.MonkeyPatch.chdir` to control cwd for AC1-AC2; assert env-var population without actually starting Django (call `_resolve_repo_flag(...)` and `_set_env_for_django(...)` helpers, not `main()`).

## Dev Notes

- Refactor: extract `_resolve_repo_flag(args, cwd) -> Path | None` and `_set_env_for_django(repo, disabled, rebuild)` from `main()` so tests can target them without spinning up Django.
- `--repo` path is resolved with `Path.resolve()` BEFORE the env-var is set. Path traversal is the user's prerogative here (their CLI, their repo path); we just normalize.
- Walk-up: start at `Path.cwd()`, iterate `parents` (which includes the cwd itself in `.parents` only if you yield from `[cwd, *cwd.parents]`). Stop on first hit with `.git` directory. Cap at filesystem root. Return None if not found.
- Mutual exclusion: argparse's `add_mutually_exclusive_group()`.
- Don't import `ulog.web.viewer.blame` in the CLI — keep it lazy. The Django side (Story 2.3+) will import as needed.

## Tasks / Subtasks

- [x] Task 1 — Add `--repo`, `--no-author-index`, `--rebuild-author-index` flags (mutually exclusive group for last two)
- [x] Task 2 — Implement `_walk_for_git_root(cwd) -> Path | None` (parent-walk)
- [x] Task 3 — Implement `_resolve_repo_flag(args, cwd) -> tuple[Path | None, str | None]` returning `(repo, warning_msg)`
- [x] Task 4 — Wire env vars `ULOG_AUTHOR_REPO`, `ULOG_AUTHOR_INDEX_DISABLED`, `ULOG_AUTHOR_INDEX_REBUILD`
- [x] Task 5 — Print stderr warning when relevant
- [x] Task 6 — Write `tests/test_cli_repo_flags.py` (≥6 tests, AC1-AC6)
- [x] Task 7 — Verify full suite green

## Dev Agent Record

### File List
- `ulog/web/cli.py` — modified: 3 flags + helpers
- `tests/test_cli_repo_flags.py` — NEW

### Completion Notes
All ACs verified. Suite at 196 + 7 new = 203/203 green. Zero regression.
