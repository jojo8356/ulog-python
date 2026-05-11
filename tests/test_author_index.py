"""Tests for `ulog.web.viewer.blame.AuthorIndex` — Story 2.1 (FR70, FR82, FR83, NFR-DEP-30)."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from ulog.web.viewer.blame import Author, AuthorIndex

# ---- fixtures ------------------------------------------------------------


def _git(*args: str, cwd: Path) -> None:
    """Run a git command silently; raises on non-zero."""
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _git_commit(cwd: Path, msg: str, name: str = "Alice", email: str = "alice@example.com") -> None:
    """Commit staged files with explicit author identity (CI-safe)."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    }
    subprocess.run(
        ["git", "commit", "-q", "-m", msg],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Fresh git repo with one tracked file `foo.py` (3 lines, all from one commit)."""
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.name", "Alice", cwd=tmp_path)
    _git("config", "user.email", "alice@example.com", cwd=tmp_path)
    foo = tmp_path / "foo.py"
    foo.write_text("line1\nline2\nline3\n", encoding="utf-8")
    _git("add", "foo.py", cwd=tmp_path)
    _git_commit(tmp_path, "init")
    return tmp_path


# ---- AC1: dataclass shape ------------------------------------------------


def test_author_dataclass_has_four_fields():
    a = Author(name="x", email="y", sha="0" * 40, ts=0)
    assert a.name == "x"
    assert a.email == "y"
    assert a.sha == "0" * 40
    assert a.ts == 0


def test_author_is_frozen_and_hashable():
    a = Author(name="x", email="y", sha="0" * 40, ts=0)
    with pytest.raises((AttributeError, Exception)):
        a.name = "z"  # type: ignore[misc]
    # Must be hashable for Set[Author] aggregation in Story 2.6.
    assert hash(a) == hash(Author(name="x", email="y", sha="0" * 40, ts=0))


# ---- AC2: happy path -----------------------------------------------------


def test_author_for_returns_author_on_tracked_line(repo):
    idx = AuthorIndex(repo)
    a = idx.author_for("foo.py", 2)
    assert a is not None
    assert a.name == "Alice"
    assert a.email == "alice@example.com"
    assert len(a.sha) == 40
    assert all(c in "0123456789abcdef" for c in a.sha)
    assert a.ts > 0


# ---- AC3: cache hit ------------------------------------------------------


def test_cache_hit_does_not_invoke_subprocess(repo, monkeypatch):
    idx = AuthorIndex(repo)
    a1 = idx.author_for("foo.py", 2)
    assert a1 is not None

    calls = [0]
    real_run = subprocess.run

    def counting_run(*args, **kwargs):
        calls[0] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", counting_run)
    a2 = idx.author_for("foo.py", 2)
    assert a2 == a1
    assert calls[0] == 0  # zero subprocess calls on a cache hit


# ---- AC4: mtime invalidation ---------------------------------------------


def test_mtime_change_invalidates_cache(repo, monkeypatch):
    idx = AuthorIndex(repo)
    idx.author_for("foo.py", 2)  # warm cache

    # Rewrite the file and bump mtime forward.
    (repo / "foo.py").write_text("X\nY\nZ\n", encoding="utf-8")
    future = time.time() + 100
    os.utime(repo / "foo.py", (future, future))

    calls = [0]
    real_run = subprocess.run

    def counting_run(*args, **kwargs):
        if args and len(args[0]) >= 2 and args[0][1] == "blame":
            calls[0] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", counting_run)
    idx.author_for("foo.py", 2)
    assert calls[0] == 1, "mtime change must trigger exactly one re-blame"


# ---- AC5: batched build, ≤ N forks for N unique files --------------------


def test_batched_build_one_fork_per_file(repo, monkeypatch):
    idx = AuthorIndex(repo)

    calls = [0]
    real_run = subprocess.run

    def counting_run(*args, **kwargs):
        if args and len(args[0]) >= 2 and args[0][1] == "blame":
            calls[0] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", counting_run)
    idx.build_for_pairs([("foo.py", 1), ("foo.py", 2), ("foo.py", 3)])
    assert calls[0] == 1, "3 lines / 1 file must produce exactly 1 git fork (FR83)"


def test_batched_build_two_files_two_forks(tmp_path):
    """N=2 unique files → 2 forks, regardless of how many lines per file."""
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.name", "Alice", cwd=tmp_path)
    _git("config", "user.email", "alice@example.com", cwd=tmp_path)
    (tmp_path / "a.py").write_text("a1\na2\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b1\nb2\nb3\n", encoding="utf-8")
    _git("add", ".", cwd=tmp_path)
    _git_commit(tmp_path, "init")

    idx = AuthorIndex(tmp_path)
    idx.build_for_pairs(
        [
            ("a.py", 1),
            ("a.py", 2),
            ("b.py", 1),
            ("b.py", 2),
            ("b.py", 3),
        ]
    )
    # Now query — should be cached.
    assert idx.author_for("a.py", 1) is not None
    assert idx.author_for("b.py", 3) is not None


# ---- AC6: porcelain repeated-SHA parser ----------------------------------


def test_porcelain_repeated_sha_parser(repo):
    """All 3 lines from same commit; lines 2+3 are SHA-only chunks in
    porcelain output (no headers). Parser must resolve via seen_authors."""
    idx = AuthorIndex(repo)
    a1 = idx.author_for("foo.py", 1)
    a2 = idx.author_for("foo.py", 2)
    a3 = idx.author_for("foo.py", 3)
    assert a1 is not None
    assert a2 is not None
    assert a3 is not None
    assert a1.sha == a2.sha == a3.sha
    assert a1.email == a2.email == a3.email == "alice@example.com"


def test_porcelain_parser_handles_two_authors(tmp_path):
    """Two distinct commits by different authors — both must resolve."""
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.name", "Alice", cwd=tmp_path)
    _git("config", "user.email", "alice@example.com", cwd=tmp_path)
    (tmp_path / "x.py").write_text("alice-line\n", encoding="utf-8")
    _git("add", "x.py", cwd=tmp_path)
    _git_commit(tmp_path, "alice", name="Alice", email="alice@example.com")
    (tmp_path / "x.py").write_text("alice-line\nbob-line\n", encoding="utf-8")
    _git("add", "x.py", cwd=tmp_path)
    _git_commit(tmp_path, "bob", name="Bob", email="bob@example.com")

    idx = AuthorIndex(tmp_path)
    a1 = idx.author_for("x.py", 1)
    a2 = idx.author_for("x.py", 2)
    assert a1 is not None
    assert a2 is not None
    assert a1.email == "alice@example.com"
    assert a2.email == "bob@example.com"
    assert a1.sha != a2.sha


# ---- AC7: None on miss ---------------------------------------------------


def test_line_out_of_range_returns_none(repo):
    idx = AuthorIndex(repo)
    assert idx.author_for("foo.py", 999) is None


def test_untracked_file_returns_none(repo):
    (repo / "untracked.py").write_text("x\n", encoding="utf-8")
    # Note: NOT staged + committed.
    idx = AuthorIndex(repo)
    assert idx.author_for("untracked.py", 1) is None


def test_nonexistent_file_returns_none(repo):
    idx = AuthorIndex(repo)
    assert idx.author_for("does_not_exist.py", 1) is None


# ---- AC8: no GitPython ---------------------------------------------------


def test_no_gitpython_or_pygit2_import_in_ulog():
    """Hard regression check: NFR-DEP-30 + AC8."""
    out = subprocess.run(
        ["grep", "-rE", r"^(from|import)\s+(git|pygit2)", "ulog/"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout == "", f"GitPython/pygit2 import found in ulog/:\n{out.stdout}"


# ---- AC9: no new dep -----------------------------------------------------


def test_pyproject_dependencies_still_empty():
    """SC4 / NFR-DEP-50 invariant: no new top-level dep added."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    # Match the canonical empty-deps line regardless of whitespace.
    assert "dependencies = []" in text, (
        "pyproject.toml must keep `dependencies = []`. "
        "If you genuinely need a new dep, escalate per NFR-DEP-50."
    )


# ---- invocation arg sanity ----------------------------------------------


def test_invocation_uses_porcelain_L_separator_and_cwd(repo, monkeypatch):
    captured: list = []
    real_run = subprocess.run

    def capturing_run(args, **kw):
        captured.append((list(args), dict(kw)))
        return real_run(args, **kw)

    monkeypatch.setattr("ulog.web.viewer.blame.subprocess.run", capturing_run)
    idx = AuthorIndex(repo)
    idx.author_for("foo.py", 2)

    blame_calls = [c for c in captured if "blame" in c[0]]
    assert len(blame_calls) == 1
    args, kw = blame_calls[0]
    assert "--porcelain" in args
    assert "-L" in args
    assert "2,2" in args
    assert "--" in args  # path separator (security: prevents ref/path ambiguity)
    assert kw.get("cwd") == str(repo)
    # Path comes AFTER --
    sep_idx = args.index("--")
    assert args[sep_idx + 1] == "foo.py"
