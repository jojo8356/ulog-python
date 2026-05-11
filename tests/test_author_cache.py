"""Story 2.4 — authors cache table + sidecar SQLite for JSONL/CSV."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

import ulog
from ulog.web.viewer.adapters import JSONLAdapter, SQLiteAdapter
from ulog.web.viewer.blame import (
    Author,
    AuthorIndex,
    _drop_authors_table,
    _load_authors,
    _persist_authors,
    build_index_at_startup,
    cache_path_for,
    set_global_index,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    set_global_index(None)
    yield
    set_global_index(None)


def _setup_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Alice"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "alice@example.com"], cwd=tmp_path, check=True)
    (tmp_path / "foo.py").write_text("a\nb\nc\n", encoding="utf-8")
    subprocess.run(["git", "add", "foo.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"],
        cwd=tmp_path,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Alice",
            "GIT_AUTHOR_EMAIL": "alice@example.com",
            "GIT_COMMITTER_NAME": "Alice",
            "GIT_COMMITTER_EMAIL": "alice@example.com",
        },
        check=True,
    )
    return tmp_path


def _jsonl_log(repo: Path) -> Path:
    log = repo / "logs.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-01-01T00:00:00Z",
                        "level": "INFO",
                        "logger": "x",
                        "msg": f"line{i}",
                        "file": "foo.py",
                        "line": i,
                    }
                )
                for i in (1, 2, 3)
            ]
        ),
        encoding="utf-8",
    )
    return log


# ---- Schema + persist + load ---------------------------------------------


def test_persist_creates_authors_table_with_correct_schema(tmp_path):
    """AC1 — schema columns + PK"""
    db = tmp_path / "cache.sqlite"
    idx = AuthorIndex("/tmp")
    a = Author(name="A", email="a@x", sha="abc" * 13 + "a", ts=1700000000)
    from ulog.web.viewer.blame import _FileCache

    idx._cache["foo.py"] = _FileCache(mtime=0.0, blames={5: a})
    n = _persist_authors(idx, db)
    assert n == 1
    conn = sqlite3.connect(str(db))
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(authors)").fetchall()]
        assert set(cols) == {
            "file",
            "line",
            "author_name",
            "author_email",
            "commit_sha",
            "commit_ts",
        }
        # PK = (file, line)
        pk_rows = [r for r in conn.execute("PRAGMA table_info(authors)").fetchall() if r[5] > 0]
        pk_cols = sorted(r[1] for r in pk_rows)
        assert pk_cols == ["file", "line"]
    finally:
        conn.close()


def test_persist_then_load_roundtrip(tmp_path):
    """AC4 + AC5 — persist + reload preserves Author"""
    db = tmp_path / "cache.sqlite"
    idx_a = AuthorIndex("/tmp")
    a = Author(name="Alice", email="alice@x", sha="abc" * 13 + "a", ts=1700000000)
    b = Author(name="Bob", email="bob@x", sha="def" * 13 + "f", ts=1700000100)
    from ulog.web.viewer.blame import _FileCache

    idx_a._cache["foo.py"] = _FileCache(mtime=0.0, blames={1: a, 2: b})
    idx_a._cache["bar.py"] = _FileCache(mtime=0.0, blames={10: a})
    assert _persist_authors(idx_a, db) == 3

    idx_b = AuthorIndex("/tmp")
    loaded = _load_authors(idx_b, db)
    assert loaded == 3
    assert idx_b._cache["foo.py"].blames[1] == a
    assert idx_b._cache["foo.py"].blames[2] == b
    assert idx_b._cache["bar.py"].blames[10] == a


def test_load_returns_zero_when_table_missing(tmp_path):
    db = tmp_path / "cache.sqlite"
    db.touch()  # empty file, no schema
    idx = AuthorIndex("/tmp")
    assert _load_authors(idx, db) == 0


# ---- cache_path_for ------------------------------------------------------


def test_cache_path_for_sqlite_adapter_returns_same_db(tmp_path):
    """AC2 — same DB for SQLite log sources"""
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger("x").info("hi")
    for h in __import__("logging").getLogger().handlers:
        h.flush()
    ulog.clear()
    adapter = SQLiteAdapter(db)
    assert cache_path_for(adapter) == db


def test_cache_path_for_jsonl_adapter_returns_sidecar(tmp_path):
    """AC3 — sidecar `.authors.sqlite` for JSONL"""
    log = tmp_path / "logs.jsonl"
    log.write_text("", encoding="utf-8")
    adapter = JSONLAdapter(log)
    expected = Path(str(log) + ".authors.sqlite")
    assert cache_path_for(adapter) == expected


# ---- End-to-end: build → persist → reload --------------------------------


def test_build_persists_then_subsequent_load_uses_cache(tmp_path):
    """AC6 — second `build_index_at_startup` reads from cache, no fresh blame."""
    repo = _setup_repo(tmp_path)
    log = _jsonl_log(repo)
    adapter = JSONLAdapter(log)

    # First build: fresh.
    sink1 = io.StringIO()
    idx1 = build_index_at_startup(adapter, repo, progress_stream=sink1)
    assert "from cache" not in sink1.getvalue()
    assert idx1.author_for("foo.py", 2) is not None

    # Second build: cache hit.
    set_global_index(None)
    adapter2 = JSONLAdapter(log)  # fresh adapter
    sink2 = io.StringIO()
    idx2 = build_index_at_startup(adapter2, repo, progress_stream=sink2)
    assert "from cache" in sink2.getvalue()
    a = idx2.author_for("foo.py", 2)
    assert a is not None
    assert a.email == "alice@example.com"


def test_rebuild_flag_drops_cache(tmp_path):
    """AC6 + Story 2.2 plumbing: rebuild=True forces fresh blame."""
    repo = _setup_repo(tmp_path)
    log = _jsonl_log(repo)
    adapter = JSONLAdapter(log)

    # Warm cache.
    build_index_at_startup(adapter, repo, progress_stream=io.StringIO())
    sidecar = Path(str(log) + ".authors.sqlite")
    assert sidecar.exists()

    # Rebuild forces fresh blame.
    set_global_index(None)
    adapter2 = JSONLAdapter(log)
    sink = io.StringIO()
    build_index_at_startup(adapter2, repo, progress_stream=sink, rebuild=True)
    assert "from cache" not in sink.getvalue()


def test_drop_authors_table_is_idempotent(tmp_path):
    db = tmp_path / "missing.sqlite"
    # Doesn't exist yet — must be a no-op.
    _drop_authors_table(db)
    assert not db.exists()
    # Now create + drop.
    sqlite3.connect(str(db)).close()
    _drop_authors_table(db)  # no schema yet — still ok
    assert db.exists()
