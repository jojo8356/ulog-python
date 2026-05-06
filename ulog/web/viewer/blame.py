"""Author attribution via `git blame --porcelain` (PRD-v0.4 §3.1, §3.4).

Story 2.1: programmatic API for resolving (file, line) pairs to git
authors. Per-(file,line) cache with mtime-based invalidation. Batched
`-L` ranges to keep ≤ N forks for N unique files (FR83). Stdlib only —
NO GitPython, NO pygit2 (NFR-DEP-30).

Story 2.3: orchestrator `build_index_at_startup(adapter, repo)` collects
unique (file, line) pairs from a loaded log adapter, batches them per
file, calls `idx.build_for_pairs(...)`, and stores the result in a
module-level singleton accessible via `get_global_index()`. Progress is
printed to stderr (FR71).

Single-threaded by contract: the indexer runs at viewer startup, before
any WSGI worker pool exists. No locking is provided.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .adapters import Adapter


@dataclass(frozen=True, slots=True)
class Author:
    name: str
    email: str
    sha: str  # 40-char hex; truncate at display time
    ts: int  # unix epoch seconds (author-time)


@dataclass
class _FileCache:
    mtime: float
    blames: dict[int, Author | None]


class AuthorIndex:
    def __init__(self, repo_root: str | Path) -> None:
        self._repo_root = Path(repo_root)
        self._cache: dict[str, _FileCache] = {}

    def author_for(self, file: str, line: int) -> Author | None:
        cached = self._cache_lookup(file)
        if cached is not None and line in cached.blames:
            return cached.blames[line]
        # Negative-cache short-circuit: file was missing at build time
        # (mtime == 0.0). Don't re-attempt — record the line as None
        # and return without spawning a subprocess.
        if cached is not None and cached.mtime == 0.0:
            cached.blames[line] = None
            return None
        # Cache miss for this line — re-blame the file (cheap because
        # one fork covers all lines via -L). For now blame the single
        # requested line; build_for_pairs() is the batched path.
        results = self._blame_file(file, [line])
        cache = self._cache.setdefault(file, _FileCache(mtime=self._mtime(file) or 0.0, blames={}))
        cache.blames.update(results)
        cache.blames.setdefault(line, None)  # ensure None on miss
        return cache.blames.get(line)

    def build_for_pairs(self, pairs: Iterable[tuple[str, int]]) -> None:
        """Batched build: group pairs by file, one subprocess per file
        with multiple `-L` ranges. ≤ N forks for N unique files (FR83)."""
        by_file: dict[str, list[int]] = defaultdict(list)
        for f, ln in pairs:
            by_file[f].append(ln)
        for f, lines in by_file.items():
            unique_lines = sorted(set(lines))
            results = self._blame_file(f, unique_lines)
            mtime = self._mtime(f) or 0.0
            cache = self._cache.setdefault(f, _FileCache(mtime=mtime, blames={}))
            cache.mtime = mtime
            cache.blames.update(results)
            for ln in unique_lines:
                cache.blames.setdefault(ln, None)

    # -- internals --

    def _mtime(self, file: str) -> float | None:
        try:
            return os.stat(self._repo_root / file).st_mtime
        except FileNotFoundError:
            return None

    def _cache_lookup(self, file: str) -> _FileCache | None:
        """Return cache entry if mtime unchanged; else drop and return None.

        Special case (negative cache): when the cached entry was built
        for a file that NEVER existed in `repo_root` (mtime stored as
        0.0 by build_for_pairs / author_for), don't re-attempt the
        blame on every lookup. This avoids an O(N) subprocess storm
        for records referencing files outside the repo (e.g.
        `pytest_plugin.py` records when --repo points elsewhere).
        """
        cached = self._cache.get(file)
        if cached is None:
            return None
        current = self._mtime(file)
        if current is None:
            # File doesn't exist on disk under repo_root.
            if cached.mtime == 0.0:
                # Negative cache — file was already missing at build
                # time. Keep the entry; all lookups return None without
                # re-blaming.
                return cached
            # File USED to exist, now vanished — invalidate.
            self._cache.pop(file, None)
            return None
        if current != cached.mtime:
            self._cache.pop(file, None)
            return None
        return cached

    def _blame_file(self, file: str, lines: Iterable[int]) -> dict[int, Author | None]:
        """Run `git blame --porcelain` for the requested lines in one
        subprocess. Returns dict[line, Author | None]; lines not
        resolved (out-of-range, untracked) map to None."""
        line_list = sorted(set(lines))
        if not line_list:
            return {}

        # Build the -L args: one range per line for v0.4 (collapse to
        # contiguous ranges is a v0.5 optimization — see story Dev Notes).
        l_flags: list[str] = []
        for ln in line_list:
            l_flags.extend(["-L", f"{ln},{ln}"])

        result = subprocess.run(
            ["git", "blame", "--porcelain", *l_flags, "--", file],
            cwd=str(self._repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            # File not tracked / line out of range / other git-side error.
            # Map all requested lines to None — caller distinguishes by
            # presence of the key, not by truthiness.
            return {ln: None for ln in line_list}
        return _parse_porcelain(result.stdout, set(line_list))


# ---- Cache persistence (Story 2.4) ---------------------------------------

_AUTHORS_SCHEMA = """
CREATE TABLE IF NOT EXISTS authors (
    file TEXT NOT NULL,
    line INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    author_email TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    commit_ts INTEGER NOT NULL,
    PRIMARY KEY (file, line)
)
"""


def cache_path_for(adapter: "Adapter") -> Path:
    """Return the SQLite path where the authors cache lives for `adapter`.

    SQLite log sources reuse the same DB (so `authors` sits beside `logs`).
    JSONL/CSV sources use a sidecar `<logs>.authors.sqlite` (Decision A3).
    """
    from .adapters import CSVAdapter, JSONLAdapter, SQLiteAdapter

    if isinstance(adapter, SQLiteAdapter):
        # SQLAlchemy URL form: 'sqlite:///path/to/file' — extract path.
        url = str(adapter._engine.url)
        if url.startswith("sqlite:///"):
            return Path(url[len("sqlite:///"):])
        # Fallback (shouldn't happen for our use).
        return Path(url)
    if isinstance(adapter, (JSONLAdapter, CSVAdapter)):
        # Adapters store path implicitly; we must reconstruct.
        # JSONLAdapter / CSVAdapter both stored their original path during
        # __init__ — but only as the source for parsing. We use the
        # adapter's `_source_path` attribute, set below in adapters.py.
        src = getattr(adapter, "_source_path", None)
        if src is None:
            raise RuntimeError(
                "JSONL/CSV adapter is missing _source_path; cannot resolve sidecar"
            )
        return Path(str(src) + ".authors.sqlite")
    raise TypeError(f"unknown adapter kind: {type(adapter).__name__}")


def _persist_authors(idx: "AuthorIndex", db_path: Path) -> int:
    """Write idx's resolved (file, line) → Author entries to the
    `authors` table at db_path. Returns count written. Skips entries
    where the Author is None (line OOR / untracked)."""
    rows: list[tuple[str, int, str, str, str, int]] = []
    for f, fc in idx._cache.items():
        for line, author in fc.blames.items():
            if author is None:
                continue
            rows.append((f, line, author.name, author.email, author.sha, author.ts))
    if not rows:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(_AUTHORS_SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO authors "
            "(file, line, author_name, author_email, commit_sha, commit_ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def _load_authors(idx: "AuthorIndex", db_path: Path) -> int:
    """Populate idx's cache from the `authors` table at db_path.
    Returns count loaded. Returns 0 if the table doesn't exist yet."""
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        # Check the table exists; otherwise fresh DB → no cache.
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='authors'"
        ).fetchone()
        if row is None:
            return 0
        cur = conn.execute(
            "SELECT file, line, author_name, author_email, commit_sha, commit_ts "
            "FROM authors"
        )
        count = 0
        for f, line, name, email, sha, ts in cur:
            cache = idx._cache.setdefault(
                f, _FileCache(mtime=idx._mtime(f) or 0.0, blames={})
            )
            cache.blames[int(line)] = Author(name=name, email=email, sha=sha, ts=int(ts))
            count += 1
        return count
    finally:
        conn.close()


def _drop_authors_table(db_path: Path) -> None:
    """Drop the `authors` table at db_path. Used by --rebuild-author-index."""
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DROP TABLE IF EXISTS authors")
        conn.commit()
    finally:
        conn.close()


# ---- Author summary aggregation (Story 2.5) ------------------------------


@dataclass(frozen=True)
class AuthorsSummary:
    """Sidebar-ready aggregation: list of (Author | None, count).

    `None` represents the `<unknown>` bucket — records where
    `idx.author_for(...)` returned None (untracked file, line OOR, etc.)
    OR records aggregated when no indexer is active.

    Sort order: known authors by count desc, then `<unknown>` last.
    """
    entries: tuple[tuple[Author | None, int], ...]

    @property
    def unknown_count(self) -> int:
        for author, count in self.entries:
            if author is None:
                return count
        return 0

    @property
    def known_entries(self) -> list[tuple[Author, int]]:
        return [(a, c) for a, c in self.entries if a is not None]


_AUTHORS_SUMMARY_CACHE: tuple[tuple[float, int], AuthorsSummary] | None = None


def _adapter_db_mtime(adapter: "Adapter") -> float:
    """Best-effort source-file mtime for cache invalidation. 0.0 on failure."""
    from .adapters import CSVAdapter, JSONLAdapter, SQLiteAdapter

    try:
        if isinstance(adapter, SQLiteAdapter):
            url = str(adapter._engine.url)
            if url.startswith("sqlite:///"):
                return os.stat(url[len("sqlite:///"):]).st_mtime
        if isinstance(adapter, (JSONLAdapter, CSVAdapter)):
            src = getattr(adapter, "_source_path", None)
            if src is not None:
                return os.stat(src).st_mtime
    except OSError:
        pass
    return 0.0


def invalidate_authors_summary_cache() -> None:
    """Drop the memoized AuthorsSummary so the next call recomputes.
    Called by `set_global_index` and explicitly by tests."""
    global _AUTHORS_SUMMARY_CACHE
    _AUTHORS_SUMMARY_CACHE = None


def compute_authors_summary(
    adapter: "Adapter",
    idx: AuthorIndex | None,
) -> AuthorsSummary:
    """Aggregate records into per-author counts (Story 2.5 + PRD-v0.4.1 perf).

    PRD-v0.4.1 optimizations:
    1. Memoized at module level keyed by (db_mtime, id(idx)).
    2. Iterates `adapter.file_line_record_counts()` (≤ unique pairs)
       instead of all records.

    When `idx is None`, every record falls into `<unknown>`. Otherwise
    each unique (file, line) is resolved via `idx.author_for(...)` once
    and the count for that pair flows to that bucket.
    """
    global _AUTHORS_SUMMARY_CACHE

    cache_key = (_adapter_db_mtime(adapter), id(idx) if idx is not None else 0)
    if _AUTHORS_SUMMARY_CACHE is not None and _AUTHORS_SUMMARY_CACHE[0] == cache_key:
        return _AUTHORS_SUMMARY_CACHE[1]

    counts: dict[Author | None, int] = defaultdict(int)
    if idx is None:
        # Sum all record counts under <unknown> in one pass.
        for _f, _l, n in adapter.file_line_record_counts():
            counts[None] += n
    else:
        # One author_for per unique pair, multiplied by its record count.
        for f, l, n in adapter.file_line_record_counts():
            a = idx.author_for(f, l)
            counts[a] += n

    known_sorted = sorted(
        ((a, c) for a, c in counts.items() if a is not None),
        key=lambda pair: (-pair[1], pair[0].email, pair[0].name),
    )
    entries: list[tuple[Author | None, int]] = list(known_sorted)
    if None in counts:
        entries.append((None, counts[None]))
    summary = AuthorsSummary(entries=tuple(entries))
    _AUTHORS_SUMMARY_CACHE = (cache_key, summary)
    return summary


# ---- Module-level singleton (Story 2.3) ----------------------------------

_AUTHOR_INDEX: AuthorIndex | None = None


def get_global_index() -> AuthorIndex | None:
    """Return the populated singleton built at viewer startup, or None
    when no index was built (CLI ran with `--no-author-index`, no .git/
    detected, or build failed)."""
    return _AUTHOR_INDEX


def set_global_index(idx: AuthorIndex | None) -> None:
    """Set the module-level singleton. Used by `build_index_at_startup`
    and by tests. Invalidates the cached AuthorsSummary so the next
    request recomputes against the new index."""
    global _AUTHOR_INDEX
    _AUTHOR_INDEX = idx
    invalidate_authors_summary_cache()


def build_index_at_startup(
    adapter: "Adapter",
    repo: str | Path,
    *,
    progress_stream: IO[str] = sys.stderr,
    rebuild: bool | None = None,
) -> AuthorIndex:
    """Build the AuthorIndex from `adapter`'s unique (file, line) pairs.

    Story 2.4 cache flow:
        1. Resolve cache_path via `cache_path_for(adapter)`.
        2. If `rebuild` is True, drop the cached `authors` table first.
        3. Try `_load_authors(...)` from the cache. If it returns > 0
           AND covers ALL the unique pairs, use the cached result.
        4. Otherwise build fresh, persist to the cache, return.

    Prints progress to `progress_stream` (default stderr) per FR71:
        ulog: indexed 100000 records across 30 files in 4.21s [from cache]
        or:
        ulog: indexed 100000 records across 30 files in 4.21s

    The populated AuthorIndex is also stored in the module singleton
    for downstream view consumption (`get_global_index()`).
    """
    if rebuild is None:
        rebuild = os.environ.get("ULOG_AUTHOR_INDEX_REBUILD") == "1"

    idx = AuthorIndex(repo)
    cache_path: Path | None
    try:
        cache_path = cache_path_for(adapter)
    except Exception:
        cache_path = None

    if cache_path is not None and rebuild:
        _drop_authors_table(cache_path)

    pairs: list[tuple[str, int]] = list(adapter.unique_file_line_pairs())
    total = len(pairs)
    if total == 0:
        set_global_index(idx)
        return idx

    # Try to satisfy the request from the cache.
    if cache_path is not None and not rebuild:
        loaded = _load_authors(idx, cache_path)
        if loaded > 0:
            cached_pairs = {
                (f, line) for f, fc in idx._cache.items() for line in fc.blames
            }
            if all(p in cached_pairs for p in pairs):
                # Every requested pair is in the cache; skip the build.
                n_files = len({p[0] for p in pairs})
                print(
                    f"ulog: indexed {total} records across {n_files} files "
                    f"from cache",
                    file=progress_stream,
                )
                set_global_index(idx)
                return idx

    # Group by file so we can emit progress at file boundaries AND every
    # ~10% of records (whichever is sparser).
    by_file: dict[str, list[int]] = defaultdict(list)
    for f, l in pairs:
        by_file[f].append(l)
    n_files = len(by_file)

    start = time.monotonic()
    processed = 0
    progress_step = max(1, total // 10)  # 10% buckets
    next_emit = progress_step

    for f, lines in by_file.items():
        unique_lines = sorted(set(lines))
        idx.build_for_pairs([(f, l) for l in unique_lines])
        processed += len(unique_lines)
        if processed >= next_emit:
            pct = (processed * 100) // total
            print(
                f"ulog: indexing authors... {n_files} files, "
                f"{processed}/{total} records ({pct}%)",
                file=progress_stream,
            )
            next_emit += progress_step

    elapsed = time.monotonic() - start
    print(
        f"ulog: indexed {total} records across {n_files} files in {elapsed:.2f}s",
        file=progress_stream,
    )
    # Persist to cache for next launch.
    if cache_path is not None:
        try:
            _persist_authors(idx, cache_path)
        except Exception as e:
            print(
                f"ulog: warning — could not persist author cache: {e}",
                file=progress_stream,
            )
    set_global_index(idx)
    return idx


# ---- Porcelain parser ----------------------------------------------------


def _parse_porcelain(out: str, requested_lines: set[int]) -> dict[int, Author | None]:
    """State-machine parser over `git blame --porcelain` output.

    Format reminder:
        <40-hex-sha> <orig-line> <final-line> [<group-size>]
        author <Name>
        author-mail <<email>>
        author-time <unix-ts>
        ...other headers...
        filename <path>
        \\t<source-line>

    Repeated-SHA optimization: when a SHA appears more than once, only
    the first chunk has full headers. Subsequent chunks are just the
    SHA-line + the \\t<source> line. The parser MUST resolve repeat-SHA
    chunks via a `_seen_authors[sha]` lookup (AC6).
    """
    seen_authors: dict[str, Author] = {}
    result: dict[int, Author | None] = {}

    cur_sha: str | None = None
    cur_final_line: int | None = None
    cur_name: str | None = None
    cur_email: str | None = None
    cur_ts: int | None = None
    in_headers = False

    for raw_line in out.splitlines():
        if raw_line.startswith("\t"):
            # End of chunk: emit (cur_final_line, Author).
            if cur_sha is not None and cur_final_line is not None:
                if cur_name is not None and cur_email is not None and cur_ts is not None:
                    author = Author(name=cur_name, email=cur_email, sha=cur_sha, ts=cur_ts)
                    seen_authors[cur_sha] = author
                    result[cur_final_line] = author
                elif cur_sha in seen_authors:
                    result[cur_final_line] = seen_authors[cur_sha]
                else:
                    result[cur_final_line] = None
            # Reset chunk-local state.
            cur_sha = None
            cur_final_line = None
            cur_name = None
            cur_email = None
            cur_ts = None
            in_headers = False
            continue

        if not in_headers:
            # Expecting chunk header: "<sha> <orig> <final> [<group>]"
            parts = raw_line.split()
            if len(parts) >= 3 and len(parts[0]) == 40 and all(c in "0123456789abcdef" for c in parts[0]):
                cur_sha = parts[0]
                try:
                    cur_final_line = int(parts[2])
                except ValueError:
                    cur_final_line = None
                in_headers = True
            # else: leading blank line / boundary noise — skip
            continue

        # In header section.
        if raw_line.startswith("author-mail "):
            mail = raw_line[len("author-mail "):].strip()
            if mail.startswith("<") and mail.endswith(">"):
                mail = mail[1:-1]
            cur_email = mail
        elif raw_line.startswith("author-time "):
            try:
                cur_ts = int(raw_line[len("author-time "):].strip())
            except ValueError:
                cur_ts = None
        elif raw_line.startswith("author "):
            cur_name = raw_line[len("author "):].strip()
        # other headers (committer, summary, filename, boundary, previous) ignored

    # Fill missing requested lines with None.
    for ln in requested_lines:
        result.setdefault(ln, None)
    return result
