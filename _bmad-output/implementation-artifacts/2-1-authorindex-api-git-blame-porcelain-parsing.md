# Story 2.1: `AuthorIndex` API + git blame --porcelain parsing

Status: done

**Epic:** 2 — v0.4 Author attribution (FIRST story; foundational programmatic API)
**Story key:** `2-1-authorindex-api-git-blame-porcelain-parsing`
**Implements:** FR70 (programmatic API), FR82 (per-(file,line) cache + mtime invalidation), FR83 (≤1 fork per unique file via `-L` ranges), NFR-DEP-30 (no GitPython — `subprocess` + stdlib only)
**Source:** `docs/prds/PRD-v0.4-commit-author-filter.md` §3.1 (FR70-75), §3.4 (FR82-83), §4 (NFR-DEP-30, NFR-PERF-30), §5.1 (programmatic API sketch); `_bmad-output/planning-artifacts/architecture.md` lines 57-58, 252, 597, 995, 1086, 1205, 1208; `_bmad-output/planning-artifacts/epics.md` Story 2.1
**Foundation for:** ALL of Epic 2 (Stories 2.2-2.11 depend on this API existing). Specifically:
  - Story 2.2 — CLI flags wire `--repo` to `AuthorIndex(repo_root)`
  - Story 2.3 — lazy build orchestrator calls `idx.build()` with progress
  - Story 2.4 — cache table persistence layer reads/writes via `idx`
  - Stories 2.6-2.8 — UI consumes `idx.author_for(...)` per record
  - Story 2.9 — `/diff/<sha>` reuses the subprocess-git contract

---

## Story

As a **developer integrating author attribution programmatically** (CI bots, dashboards, IDE plugins),
I want **`AuthorIndex(repo_root).author_for(file, line) -> Author | None` to resolve any (file, line) pair to a git author via `git blame --porcelain`**,
so that **I can query authorship without spinning up the viewer, and the viewer's UI layers (Stories 2.2-2.11) build on this single source of truth.**

## Acceptance Criteria

### AC1 — `Author` dataclass exists with the four required fields (FR70)

**Given** a developer imports `from ulog.web.viewer.blame import Author`
**When** they inspect the type
**Then** `Author` is a frozen `@dataclass` (or `NamedTuple`) with exactly these fields:
  - `name: str`
  - `email: str`
  - `sha: str` (40-char full hex; truncate at display time, not at storage time)
  - `ts: int` (Unix timestamp from `author-time`; tz handled at display time, not stored)

### AC2 — `AuthorIndex(repo_root).author_for(file, line)` returns `Author` for tracked code (FR70)

**Given** `tmp_path` contains a fresh `git init` with one committed file `foo.py` (3 lines, author "Alice <alice@example.com>")
**When** `AuthorIndex(tmp_path).author_for("foo.py", 2)` is called
**Then** the return value is `Author(name="Alice", email="alice@example.com", sha=<40-char-hex>, ts=<unix>)`. Path is interpreted relative to `repo_root` (the developer passes a repo-relative path; `AuthorIndex` does NOT resolve absolute paths against cwd).

### AC3 — Caching: second call with unchanged file mtime does NOT spawn a subprocess (FR82)

**Given** `idx.author_for("foo.py", 2)` was called once and returned `Author(...)`
**When** the same call is made again WITHOUT modifying `foo.py`'s mtime
**Then** the second call MUST NOT invoke `subprocess.run([..., "git", "blame", ...])` (verified via a monkeypatch on `subprocess.run` in the test). The cached `Author` is returned instead.

### AC4 — Caching: file mtime change invalidates the cache for that file (FR82)

**Given** `idx.author_for("foo.py", 2)` was called once and cached
**When** `foo.py` is rewritten (mtime advances) and `idx.author_for("foo.py", 2)` is called
**Then** a fresh `git blame --porcelain` IS invoked for that file (verified via monkeypatch counter). The cache for `foo.py` is invalidated as a unit (per-file, not per-line); other cached files' entries are untouched.

### AC5 — Per-file batched build: ≤ N forks for N unique files (FR83)

**Given** a synthetic repo with 30 unique files and 100 distinct `(file, line)` requests across them
**When** `idx.build_for_pairs(pairs)` is called once with the full list of pairs
**Then** `subprocess.run([..., "git", "blame", ...])` was invoked ≤ 30 times — exactly once per unique file, using `-L` ranges to cover all requested lines in that file. The N=1 case (one file, 50 lines) MUST NOT spawn 50 forks; it MUST spawn exactly 1.

### AC6 — `git blame --porcelain` parser handles repeated-SHA blocks correctly

**Given** a real `git blame --porcelain` output where two consecutive lines share the same commit SHA (only the first chunk has full headers; subsequent chunks have just `<sha> <orig> <final>` followed by the `\t<source>` line)
**When** the parser walks the output
**Then** the SHA-only chunks correctly resolve to the same `Author` data carried over from the most-recent fully-headered chunk. The parser is a state machine over the documented porcelain format, NOT a regex on `^author ` (which would fail the repeated-SHA case).

### AC7 — `author_for` returns `None` for line-out-of-range / file-not-tracked (FR75)

**Given** `foo.py` is 5 lines long and tracked
**When** `idx.author_for("foo.py", 999)` is called (line beyond file length)
**Then** the return value is `None` (NOT a stale Author, NOT an exception leaking subprocess details).
**And given** `idx.author_for("not_in_repo.py", 1)` is called (path not tracked)
**Then** the return value is `None`.
*(Detailed edge-case behavior — `blame_skip_reason` field, file-renamed `-C -M` follow — is Story 2.10's burden; this story just makes sure the happy path returns Author and the unhappy path returns None without crashing.)*

### AC8 — No `import git`, no `import pygit2`, no GitPython (NFR-DEP-30)

**Given** the implementation
**When** `grep -rE "^(from|import)\s+(git|pygit2)" ulog/` is run
**Then** zero matches outside test files. The only git invocation is `subprocess.run(["git", ...], cwd=str(self._repo_root), capture_output=True, text=True, check=False)`. Verified via a `tests/` regression check using a hard-coded grep + assert.

### AC9 — `pyproject.toml` `dependencies = []` invariant preserved (SC4)

**Given** the diff for this story
**When** `pyproject.toml` is inspected
**Then** the `dependencies = []` line is unchanged. No new top-level dep. (Sub-deps for the test fixtures: standard `pytest` + stdlib `subprocess` + `dataclasses`.)

### AC10 — Test file `tests/test_author_index.py` covers AC1-AC9

**Given** the new test file
**When** run via `pytest tests/test_author_index.py`
**Then** at least 10 tests cover the ACs above:
  - 1 happy-path (AC2)
  - 2 cache (hit / mtime-invalidate, AC3+AC4)
  - 1 batched build fork-count (AC5)
  - 1 porcelain repeated-SHA parser (AC6)
  - 2 None-returns (AC7: line OOR, file untracked)
  - 1 GitPython grep (AC8)
  - 1 dataclass shape (AC1)
  - 1 invocation-arg sanity (`-L`, `--porcelain`, `cwd` set)

## Tasks / Subtasks

- [x] **Task 1** — Create `ulog/web/viewer/blame.py` with `Author` dataclass + `AuthorIndex` class skeleton (AC1)
- [x] **Task 2** — Implement `_blame_file(file, lines)` — single subprocess call with batched `-L` ranges (AC5, AC8)
- [x] **Task 3** — Implement porcelain state-machine parser `_parse_porcelain(out, requested_lines)` (AC6)
- [x] **Task 4** — Implement `author_for(file, line)` with mtime-based cache (AC2, AC3, AC4, AC7)
- [x] **Task 5** — Implement `build_for_pairs(pairs)` for batched startup-time build (AC5)
- [x] **Task 6** — Write `tests/test_author_index.py` (15 tests covering AC1-AC9 + invocation sanity)
- [x] **Task 7** — Run full suite (181 + 15 new = 196 passed), verify green, no regressions
- [x] **Task 8** — Verify `pyproject.toml` unchanged (AC9), `grep` regression check (AC8)

## Dev Notes

### File location & module layout (architecture-mandated)

- **NEW file**: `ulog/web/viewer/blame.py`
- Imported as `from ulog.web.viewer.blame import AuthorIndex, Author`
- Lives **inside** the viewer subpackage (per architecture line 995, 1086, 1205) — NOT at the top-level `ulog/` root. Do NOT add to `ulog/__init__.py`.
- Tests: NEW file `tests/test_author_index.py`

### `git blame --porcelain` output format (state-machine reference)

The parser MUST be a state machine, not a regex match on `^author `. Documented format:

```
<40-char-sha> <orig-line> <final-line> [<num-lines-in-group>]
author <Name>
author-mail <<email>>
author-time <unix-ts>
author-tz <+offset>
committer <Name>
committer-mail <<email>>
committer-time <unix-ts>
committer-tz <+offset>
summary <subject-line>
[boundary]
[previous <sha> <path>]
filename <path>
\t<source-line-content>
```

**The repeated-SHA optimization** (AC6): when a SHA has appeared earlier in the SAME blame output, subsequent occurrences emit ONLY the SHA-line + the `\t<source>` line. NO author/email/time/etc. headers. The parser MUST keep a `dict[sha, Author]` lookup of "already seen" headers and re-use them on subsequent SHA-only blocks.

**`author-mail` parsing**: the email is wrapped in `<...>`. Strip exactly one leading `<` and one trailing `>`. Don't be clever: empty email → empty string, malformed → return as-is and let the test catch it.

**Encoding**: invoke with `text=True` (decoded as UTF-8 by `subprocess.run`). If the repo has authors with non-UTF-8 names, use `errors="replace"` — never crash. Wrap in `subprocess.run(..., encoding="utf-8", errors="replace")`.

### `subprocess.run` invocation (security + portability)

```python
result = subprocess.run(
    ["git", "blame", "--porcelain", "-L", f"{a},{b}", "--", str(rel_path)],
    cwd=str(self._repo_root),
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    check=False,    # we read returncode ourselves; non-zero is "file not tracked" → return None
    timeout=30,     # paranoia: pathological repos shouldn't hang the indexer
)
```

**The `--` separator is non-negotiable**: it disambiguates pathnames from refs/options. Prevents `git blame foo.py` from being interpreted as `git blame foo.py` (the file) vs `git blame foo.py^` (a ref ending in `.py`). Always pass `--` before any user-provided path.

**`check=False` is intentional**: a path not tracked in git returns non-zero (`fatal: no such path 'foo.py' in HEAD`). We catch that as "file not tracked → return None", not as an exception. We use `result.returncode` ourselves.

**`shell=False` is implicit** (it's the default for `subprocess.run` with a list arg). Do NOT use `shell=True` ever — the path could contain shell metacharacters from a malicious log producer.

### Batched `-L` for AC5 (FR83)

When `build_for_pairs(pairs)` receives multiple lines for the same file, batch them into ONE invocation:

```python
# pairs = [("foo.py", 2), ("foo.py", 5), ("foo.py", 9)]
# Group by file:
by_file = {"foo.py": [2, 5, 9]}

# For each file, ONE subprocess call with multiple -L args:
result = subprocess.run(
    ["git", "blame", "--porcelain",
     "-L", "2,2", "-L", "5,5", "-L", "9,9",
     "--", "foo.py"],
    ...
)
```

`git blame` accepts MULTIPLE `-L` flags in a single invocation — each `-L a,b` adds a range to be blamed. The output is the union, in the order of the `-L` flags. The parser must populate `dict[line, Author]` from the porcelain output and look up requested lines.

**Optimization not required for v0.4**: collapsing adjacent lines into a single `-L a,b` (e.g. `-L 2,5` for `[2,3,4,5]`) is a CPU optimization. For 100K records / 30 files we have on average 3K lines per file; even sparse, ≤30 forks is the dominant constraint. Keep the simple per-line `-L l,l` flags for v0.4. Future v0.5 can collapse if benchmarks demand.

### Cache invariants (FR82)

```python
class _FileCache:
    mtime: float                    # st_mtime at last build
    blames: dict[int, Author | None]  # line → Author or None (line-out-of-range)

class AuthorIndex:
    self._cache: dict[str, _FileCache]  # file (rel-path str) → cache entry
```

**Cache invalidation rule**: on `author_for(file, line)`, if `os.stat(repo_root / file).st_mtime != self._cache[file].mtime`, **drop the entire `_FileCache` entry** for that file and re-blame. NEVER do per-line invalidation — `git blame` over a stale mtime returns wrong results for ALL lines in that file (line numbers shifted, content changed, etc.).

**`stat` failure**: `FileNotFoundError` on stat → file no longer exists → return None and DELETE the cache entry. `PermissionError` on stat → propagate (it's a system bug worth surfacing, not a "file not tracked" case).

**Threading**: v0.4 is single-threaded (the indexer runs at viewer startup, before the WSGI worker pool spawns). Document this constraint with a 1-line comment in `AuthorIndex.__init__`. Do NOT add a `threading.Lock` — premature.

### Parsing edge cases (carry to AC6)

- **First line of output is sometimes blank**: `git blame --porcelain` may emit a leading newline on some platforms. Lstrip the output before splitting.
- **Boundary commits**: the line `boundary` (no value) appears in some chunks (initial commit). Skip it; it doesn't change parsing.
- **`previous <sha> <path>`**: appears for renamed files. Skip it for v0.4 (Story 2.10 may revisit for `--follow` semantics).
- **`filename <path>`**: this is the repository-relative path to the file at the commit being blamed. May differ from the requested file under rename. Ignore for v0.4 (we just want author/email/sha/ts).
- **Trailing line**: every chunk ends with the source line prefixed by `\t`. The parser sees `\t...` as "end of chunk, advance state machine to expect next chunk-header".

### Tests — what to write

```python
# tests/test_author_index.py — skeleton

import os
import subprocess
import time
from pathlib import Path

import pytest

from ulog.web.viewer.blame import Author, AuthorIndex


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a fresh git repo with one file, one commit."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Alice"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "alice@example.com"], cwd=tmp_path, check=True)
    foo = tmp_path / "foo.py"
    foo.write_text("line1\nline2\nline3\n", encoding="utf-8")
    subprocess.run(["git", "add", "foo.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"],
        cwd=tmp_path,
        env={**os.environ, "GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@example.com",
             "GIT_COMMITTER_NAME": "Alice", "GIT_COMMITTER_EMAIL": "alice@example.com"},
        check=True,
    )
    return tmp_path


def test_author_dataclass_has_four_fields():
    """AC1"""
    a = Author(name="x", email="y", sha="z" * 40, ts=0)
    assert a.name == "x" and a.email == "y" and a.sha == "z" * 40 and a.ts == 0


def test_author_for_returns_author_on_tracked_line(repo):
    """AC2"""
    idx = AuthorIndex(repo)
    a = idx.author_for("foo.py", 2)
    assert a is not None
    assert a.name == "Alice"
    assert a.email == "alice@example.com"
    assert len(a.sha) == 40 and all(c in "0123456789abcdef" for c in a.sha)
    assert a.ts > 0


def test_cache_hit_no_subprocess(repo, monkeypatch):
    """AC3"""
    idx = AuthorIndex(repo)
    idx.author_for("foo.py", 2)  # warm cache
    calls = [0]
    real_run = subprocess.run
    def counting_run(*args, **kw):
        calls[0] += 1
        return real_run(*args, **kw)
    monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", counting_run)
    idx.author_for("foo.py", 2)
    idx.author_for("foo.py", 3)  # different line, same file, still cached
    assert calls[0] == 0


def test_mtime_change_reblaames(repo, monkeypatch):
    """AC4"""
    idx = AuthorIndex(repo)
    idx.author_for("foo.py", 2)  # warm
    # advance mtime by rewriting the file
    (repo / "foo.py").write_text("X\nY\nZ\n", encoding="utf-8")
    os.utime(repo / "foo.py", (time.time() + 10, time.time() + 10))
    calls = [0]
    real_run = subprocess.run
    def counting_run(*args, **kw):
        calls[0] += 1
        return real_run(*args, **kw)
    monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", counting_run)
    idx.author_for("foo.py", 2)
    assert calls[0] == 1  # exactly one re-blame


def test_batched_build_one_fork_per_file(repo, monkeypatch):
    """AC5"""
    # repo has 1 file, query 3 lines → 1 fork (not 3)
    idx = AuthorIndex(repo)
    calls = [0]
    real_run = subprocess.run
    def counting_run(*args, **kw):
        if args and "blame" in args[0]:
            calls[0] += 1
        return real_run(*args, **kw)
    monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", counting_run)
    idx.build_for_pairs([("foo.py", 1), ("foo.py", 2), ("foo.py", 3)])
    assert calls[0] == 1


def test_porcelain_repeated_sha_parser(repo):
    """AC6 — file with 3 lines all from same commit; 2nd+3rd are SHA-only chunks"""
    idx = AuthorIndex(repo)
    a1 = idx.author_for("foo.py", 1)
    a2 = idx.author_for("foo.py", 2)
    a3 = idx.author_for("foo.py", 3)
    # All three resolve to the same commit, even though porcelain output
    # had headers only on line 1. Parser must propagate.
    assert a1 is not None and a2 is not None and a3 is not None
    assert a1.sha == a2.sha == a3.sha
    assert a1.email == a2.email == "alice@example.com"


def test_line_out_of_range_returns_none(repo):
    """AC7"""
    idx = AuthorIndex(repo)
    assert idx.author_for("foo.py", 999) is None


def test_untracked_file_returns_none(repo):
    """AC7"""
    (repo / "untracked.py").write_text("x\n", encoding="utf-8")
    idx = AuthorIndex(repo)
    assert idx.author_for("untracked.py", 1) is None


def test_no_gitpython_import():
    """AC8 — grep regression"""
    import subprocess as sp
    out = sp.run(
        ["grep", "-rE", r"^(from|import)\s+(git|pygit2)", "ulog/"],
        capture_output=True, text=True,
    )
    assert out.stdout == "", f"GitPython/pygit2 import found in ulog/:\n{out.stdout}"


def test_invocation_uses_porcelain_and_L_and_cwd(repo, monkeypatch):
    """AC2 + invocation-arg sanity"""
    captured: list[tuple] = []
    real_run = subprocess.run
    def capturing_run(args, **kw):
        captured.append((args, kw))
        return real_run(args, **kw)
    monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", capturing_run)
    idx = AuthorIndex(repo)
    idx.author_for("foo.py", 2)
    blame_calls = [c for c in captured if "blame" in c[0]]
    assert len(blame_calls) == 1
    args, kw = blame_calls[0]
    assert "--porcelain" in args
    assert "-L" in args and "2,2" in args
    assert kw.get("cwd") == str(repo)
    assert "--" in args
```

### Why the porcelain parser is a state machine, not a regex (AC6 deep dive)

Naive regex `re.search(r"^author (.+)$", out, re.MULTILINE)` finds the FIRST `author` line and assumes it applies to all blamed lines. For a file where lines 1-3 are all from the same commit, porcelain output is:

```
abc123... 1 1 3
author Alice
author-mail <alice@example.com>
author-time 1234567890
...
filename foo.py
\tline1
abc123... 2 2
\tline2
abc123... 3 3
\tline3
```

A regex grabs Alice once, but the parser needs to know lines 2 and 3 ALSO map to Alice (via the SHA `abc123...` lookup). The state machine:

1. **STATE: expecting chunk header** — read a line. If it matches `^([0-9a-f]{40}) (\d+) (\d+)( (\d+))?$`, extract sha/orig/final. Goto STATE: maybe-headers.
2. **STATE: maybe-headers** — read lines. If line starts with `\t`, transition to STATE: chunk-done with the source line (and propagate the most recent Author for this sha). If line is one of the known header keys (`author`, `author-mail`, `author-time`, etc.), parse and store. Stay in this state.
3. **STATE: chunk-done** — store the resolved `(line_num, Author)` mapping. Goto STATE: expecting chunk header.

When a sha is seen for the first time, the headers populate `_seen_authors[sha] = Author(...)`. On a repeat-SHA chunk, no headers appear; the chunk transitions DIRECTLY from header-line to `\t<source>`. The parser uses `_seen_authors[sha]` to resolve the Author.

The key invariant: every chunk ends with `\t<source>` and the parser knows it's done with that chunk. The presence/absence of headers between header-line and `\t<source>` determines first-vs-repeat.

### Key design decisions captured here so the dev doesn't relitigate them

- **Path representation**: `str` (relative POSIX path). NOT `pathlib.Path`. Reason: this is the cache key + the value passed to `git blame -- <path>`. Using `Path` adds round-trip surprises on Windows (backslash vs slash). Stay flat.
- **Frozen dataclass for Author**: makes it hashable (the `Set[Author]` aggregation in Story 2.6 is cleaner). Use `@dataclass(frozen=True, slots=True)`.
- **No `__hash__` custom**: frozen dataclass auto-generates one based on all fields. `slots=True` reduces per-Author memory by ~40% — relevant at 100K records.
- **Module-level `subprocess` import**: needed for monkeypatch in tests (`monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", ...)`). Don't `from subprocess import run` — that would defeat the monkeypatch idiom.
- **Test fixture authors with Alice**: not Johan/Lin/Sara (the PRD personas) — keeps test independence from PRD-narrative drift.
- **`git config user.{name,email}` in the fixture**: mandatory because `git commit` will refuse without identity, and CI may run without a global gitconfig.

## Project Context Reference

`/home/jojokes/Documents/programmation/projets/autres/ulog-python/_bmad-output/project-context.md` — confirmed loaded; no v0.4-specific entries beyond what's in PRD-v0.4 + architecture.md.

## Change Log

- 2026-05-06: Initial story creation. Covers AC1-AC10. Ready for Dev Story.

## Dev Agent Record

### File List

- `ulog/web/viewer/blame.py` — NEW. ~155 LOC. `Author` frozen dataclass + `AuthorIndex` class + `_FileCache` + module-level `_parse_porcelain` state-machine.
- `tests/test_author_index.py` — NEW. 15 tests, ~250 LOC. Covers AC1-AC9 + invocation-arg sanity (porcelain flag, `-L` flags, `--` separator, cwd).

### Completion Notes

- All 10 ACs verified via 15 tests, 196/196 suite green (181 prior + 15 new), 0 regressions, mypy clean for the new module.
- Porcelain state-machine handles repeated-SHA optimization correctly: 3-line single-commit file produces 3 chunks where lines 2+3 have only the SHA-line + `\t<source>` (no headers); parser resolves them via `seen_authors[sha]` lookup. Test `test_porcelain_repeated_sha_parser` covers this. Test `test_porcelain_parser_handles_two_authors` covers the multi-commit case where lines DO have distinct headers.
- `--` separator + `cwd=str(repo_root)` + `shell=False` (default) form the security boundary. Path traversal attempts (`../../etc/passwd`) are not tracked → `git blame` exits non-zero → returns None. No shell injection surface.
- Single-threaded contract documented in module docstring. No locking. v0.5+ may revisit if WSGI worker pools share an `AuthorIndex` instance (unlikely — startup-time build means workers have a populated cache by request time).
- Mtime race window (file modified between mtime-check and blame-execution) is theoretically possible but irrelevant for v0.4 (single-threaded indexer running before WSGI workers spawn). Not a hot-loop concern.
- AC9 invariant verified: `pyproject.toml` unchanged. `dependencies = []` regression test runs every suite invocation.
- AC8 grep regression test scans `ulog/` for any `^(from|import)\s+(git|pygit2)` — runs on every suite invocation, fails fast if a future story accidentally adds GitPython.

### Code Review Notes

Self-review findings — none requiring patches:

1. **Path traversal attempts**: blocked structurally. `--` separator prevents ref/path ambiguity; `cwd=str(repo_root)` constrains git's path resolution to the repo; non-tracked paths return non-zero → `None`. No shell metacharacter risk (list-arg subprocess + `shell=False` default).
2. **Subprocess timeout (30s)**: defensive bound for pathological repos. NFR-PERF-30 budget is 5s for 100K records / 30 files (~1.5s wall on average), so 30s/file is well clear of normal operation.
3. **`author-mail` parsing edge cases**: emails with internal `>` are rare (RFC-disallowed); current strip handles `<...>` wrapper only when both delimiters present; otherwise returns string as-is. Acceptable for v0.4; Story 2.10 may revisit.
4. **`os.utime` mtime advance in tests**: explicit forward shift (`time.time() + 100`) eliminates filesystem mtime granularity flakes (some platforms only have 1-second resolution).
5. **Test fixture `_git_commit` env-injection**: explicit `GIT_AUTHOR_*` + `GIT_COMMITTER_*` env vars guarantee CI-safe identity; no dependency on global gitconfig.

No adversarial subagent review run for this story — standalone module with clear contract, narrow surface, regression-protected by 15 tests + 2 pre-existing global invariants (NFR-DEP-30 grep, dependencies=[] check).

### Risk Assessment

- **Regression risk**: NONE for existing 181 tests (no shared state with the new module). Suite stays at 196/196 across `pytest`, `--ulog-db`, `-n auto`, and the killer combo.
- **Performance risk**: NONE measured at this scope; build_for_pairs is the perf-critical entry point and FR83 enforced at fork-count level.
- **Security risk**: addressed via list-arg subprocess + `--` separator + `cwd` constraint. No new attack surface.
