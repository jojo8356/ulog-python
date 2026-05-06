"""Story 2.3 — lazy index build with stderr progress."""
from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path

import pytest

import ulog
from ulog.web.viewer.adapters import (
    CSVAdapter,
    JSONLAdapter,
    SQLiteAdapter,
)
from ulog.web.viewer.blame import (
    AuthorIndex,
    build_index_at_startup,
    get_global_index,
    set_global_index,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Each test starts with a fresh singleton."""
    set_global_index(None)
    yield
    set_global_index(None)


# ---- Adapter unique_file_line_pairs --------------------------------------


def test_sqlite_adapter_unique_pairs(tmp_path: Path):
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("svc")
    log.info("a")  # logs from this line
    log.info("a")  # same file:line as above (test file)
    log.warning("b")
    for h in __import__("logging").getLogger().handlers:
        h.flush()
    pairs = set(SQLiteAdapter(db).unique_file_line_pairs())
    # All emits from the same test file but at different lines.
    files = {p[0] for p in pairs}
    assert len(files) == 1
    # ≥ 2 distinct lines (the two .info()/.warning() calls)
    assert len(pairs) >= 2
    ulog.clear()


def test_jsonl_adapter_unique_pairs(tmp_path: Path):
    p = tmp_path / "logs.jsonl"
    p.write_text(
        "\n".join([
            json.dumps({"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
                       "msg": "a", "file": "foo.py", "line": 10}),
            json.dumps({"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
                       "msg": "b", "file": "foo.py", "line": 10}),  # dup
            json.dumps({"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
                       "msg": "c", "file": "foo.py", "line": 20}),
            json.dumps({"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
                       "msg": "d", "file": "bar.py", "line": 5}),
        ]),
        encoding="utf-8",
    )
    pairs = set(JSONLAdapter(p).unique_file_line_pairs())
    assert pairs == {("foo.py", 10), ("foo.py", 20), ("bar.py", 5)}


# ---- build_index_at_startup ---------------------------------------------


@pytest.fixture
def git_repo_with_log(tmp_path: Path) -> tuple[Path, Path]:
    """Build a git repo + a JSONL log that references files in the repo."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Alice"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "alice@example.com"], cwd=tmp_path, check=True)
    (tmp_path / "foo.py").write_text("a\nb\nc\n", encoding="utf-8")
    subprocess.run(["git", "add", "foo.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"],
        cwd=tmp_path,
        env={**os.environ, "GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@example.com",
             "GIT_COMMITTER_NAME": "Alice", "GIT_COMMITTER_EMAIL": "alice@example.com"},
        check=True,
    )
    log = tmp_path / "logs.jsonl"
    log.write_text(
        "\n".join([
            json.dumps({"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
                       "msg": "a", "file": "foo.py", "line": 1}),
            json.dumps({"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
                       "msg": "b", "file": "foo.py", "line": 2}),
            json.dumps({"ts": "2026-01-01T00:00:00Z", "level": "INFO", "logger": "x",
                       "msg": "c", "file": "foo.py", "line": 3}),
        ]),
        encoding="utf-8",
    )
    return tmp_path, log


def test_build_at_startup_populates_singleton(git_repo_with_log):
    repo, log = git_repo_with_log
    adapter = JSONLAdapter(log)
    assert get_global_index() is None
    idx = build_index_at_startup(adapter, repo, progress_stream=io.StringIO())
    assert isinstance(idx, AuthorIndex)
    assert get_global_index() is idx
    # Resolves all 3 lines to Alice.
    a = idx.author_for("foo.py", 2)
    assert a is not None
    assert a.email == "alice@example.com"


def test_build_at_startup_emits_progress_lines(git_repo_with_log):
    repo, log = git_repo_with_log
    adapter = JSONLAdapter(log)
    sink = io.StringIO()
    build_index_at_startup(adapter, repo, progress_stream=sink)
    output = sink.getvalue()
    # Final summary must be present.
    assert "ulog: indexed " in output
    assert "records across" in output
    assert "files in" in output


def test_build_at_startup_handles_empty_log(tmp_path: Path):
    """No records → no progress, just an empty index in the singleton."""
    log = tmp_path / "empty.jsonl"
    log.write_text("", encoding="utf-8")
    adapter = JSONLAdapter(log)
    sink = io.StringIO()
    idx = build_index_at_startup(adapter, tmp_path, progress_stream=sink)
    assert isinstance(idx, AuthorIndex)
    assert get_global_index() is idx
    # No final-summary line for empty input (we early-return).
    assert sink.getvalue() == ""


def test_set_get_global_index():
    assert get_global_index() is None
    fake = AuthorIndex("/tmp")
    set_global_index(fake)
    assert get_global_index() is fake
    set_global_index(None)
    assert get_global_index() is None
