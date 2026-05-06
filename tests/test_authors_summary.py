"""Story 2.5 — `<unknown>` author handling + AuthorsSummary aggregation."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ulog.web.viewer.adapters import JSONLAdapter
from ulog.web.viewer.blame import (
    Author,
    AuthorIndex,
    AuthorsSummary,
    _FileCache,
    compute_authors_summary,
)


def _jsonl(tmp_path: Path, records: list[dict]) -> Path:
    log = tmp_path / "logs.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return log


def _make_idx(tmp_path: Path, blames: dict[tuple[str, int], Author | None]) -> AuthorIndex:
    """Build an AuthorIndex with pre-populated blames (no real git).

    Creates stub files on disk under tmp_path so the AuthorIndex's
    mtime-based cache validation finds them.
    """
    idx = AuthorIndex(tmp_path)
    by_file: dict[str, dict[int, Author | None]] = {}
    for (f, l), a in blames.items():
        by_file.setdefault(f, {})[l] = a
    for f, blames_map in by_file.items():
        path = tmp_path / f
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("stub\n", encoding="utf-8")
        mtime = os.stat(path).st_mtime
        idx._cache[f] = _FileCache(mtime=mtime, blames=blames_map)
    return idx


def test_summary_with_idx_none_groups_all_unknown(tmp_path):
    """AC4 — when idx is None, every record falls into <unknown>."""
    log = _jsonl(tmp_path, [
        {"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
         "msg": "a", "file": "foo.py", "line": 1},
        {"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
         "msg": "b", "file": "bar.py", "line": 2},
    ])
    summary = compute_authors_summary(JSONLAdapter(log), idx=None)
    assert summary.unknown_count == 2
    assert summary.known_entries == []


def test_summary_with_all_known(tmp_path):
    """AC1 — basic happy path."""
    a1 = Author(name="Alice", email="alice@x", sha="a" * 40, ts=1700000000)
    log = _jsonl(tmp_path, [
        {"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
         "msg": "m1", "file": "foo.py", "line": 1},
        {"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
         "msg": "m2", "file": "foo.py", "line": 1},  # same line
    ])
    idx = _make_idx(tmp_path, {("foo.py", 1): a1})
    summary = compute_authors_summary(JSONLAdapter(log), idx=idx)
    assert summary.unknown_count == 0
    assert summary.known_entries == [(a1, 2)]


def test_summary_mixed_known_and_unknown(tmp_path):
    """AC3 — None blames count toward <unknown>"""
    a1 = Author(name="Alice", email="alice@x", sha="a" * 40, ts=1700000000)
    log = _jsonl(tmp_path, [
        {"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
         "msg": "k1", "file": "foo.py", "line": 1},
        {"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
         "msg": "u1", "file": "external.py", "line": 99},
        {"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
         "msg": "u2", "file": "another.py", "line": 1},
    ])
    idx = _make_idx(tmp_path, {
        ("foo.py", 1): a1,
        ("external.py", 99): None,
        ("another.py", 1): None,
    })
    summary = compute_authors_summary(JSONLAdapter(log), idx=idx)
    assert summary.known_entries == [(a1, 1)]
    assert summary.unknown_count == 2


def test_summary_known_sorted_by_count_desc(tmp_path):
    """AC2 — known authors sorted by count descending"""
    a1 = Author(name="Alice", email="alice@x", sha="a" * 40, ts=1)
    a2 = Author(name="Bob", email="bob@x", sha="b" * 40, ts=2)
    log = _jsonl(tmp_path, [
        # 1 record from Alice
        {"ts": "x", "level": "INFO", "logger": "x", "msg": "a", "file": "foo.py", "line": 1},
        # 3 records from Bob
        {"ts": "x", "level": "INFO", "logger": "x", "msg": "b1", "file": "bar.py", "line": 1},
        {"ts": "x", "level": "INFO", "logger": "x", "msg": "b2", "file": "bar.py", "line": 1},
        {"ts": "x", "level": "INFO", "logger": "x", "msg": "b3", "file": "bar.py", "line": 1},
    ])
    idx = _make_idx(tmp_path, {("foo.py", 1): a1, ("bar.py", 1): a2})
    summary = compute_authors_summary(JSONLAdapter(log), idx=idx)
    # Bob first (3), Alice second (1)
    assert summary.known_entries == [(a2, 3), (a1, 1)]


def test_summary_unknown_always_last(tmp_path):
    """AC2 — <unknown> entry is always last, even with high count"""
    a1 = Author(name="Alice", email="alice@x", sha="a" * 40, ts=1)
    log = _jsonl(tmp_path, [
        {"ts": "x", "level": "INFO", "logger": "x", "msg": "k", "file": "foo.py", "line": 1},
        # 5 unknown records (line numbers start at 1 — Python logging convention)
        *[
            {"ts": "x", "level": "INFO", "logger": "x", "msg": f"u{i}",
             "file": "ext.py", "line": i}
            for i in range(1, 6)
        ],
    ])
    idx = _make_idx(tmp_path, {("foo.py", 1): a1, **{("ext.py", i): None for i in range(1, 6)}})
    summary = compute_authors_summary(JSONLAdapter(log), idx=idx)
    # Last entry must be (None, 5) regardless of higher count.
    assert summary.entries[-1] == (None, 5)
    assert summary.entries[0] == (a1, 1)
