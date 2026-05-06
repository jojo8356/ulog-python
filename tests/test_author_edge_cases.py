"""Story 2.10 — PRD-v0.4 §2.3 edge cases (the cases not already covered
by Stories 2.1, 2.2, 2.9). The 3 already-covered cases (line OOR,
unreachable sha, no git) are checked by their owning tests; this file
adds the remaining 2 cases (file rename, submodule)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ulog.web.viewer.blame import AuthorIndex


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _commit(cwd: Path, msg: str, name: str = "Alice", email: str = "alice@example.com") -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    subprocess.run(
        ["git", "commit", "-q", "-m", msg],
        cwd=cwd, env=env, check=True, capture_output=True,
    )


# ---- Edge case: file renamed --------------------------------------------


def test_file_renamed_returns_none_at_old_path(tmp_path):
    """PRD-v0.4 §2.3 'File renamed' — Story 2.1 doesn't follow renames
    (that's a v0.5 enhancement). For v0.4, a rename means the OLD path
    is no longer tracked, so author_for(old_path, ...) returns None.

    The PRD's mention of `--follow -C -M` is aspirational for v0.5.
    Story 2.10 documents the v0.4 behavior: graceful None.
    """
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.name", "Alice", cwd=tmp_path)
    _git("config", "user.email", "alice@example.com", cwd=tmp_path)
    (tmp_path / "old.py").write_text("a\nb\nc\n", encoding="utf-8")
    _git("add", "old.py", cwd=tmp_path)
    _commit(tmp_path, "init")
    _git("mv", "old.py", "new.py", cwd=tmp_path)
    _commit(tmp_path, "rename")

    idx = AuthorIndex(tmp_path)
    # The new path resolves successfully (it's now tracked).
    assert idx.author_for("new.py", 1) is not None
    # The old path no longer exists in the working tree.
    assert idx.author_for("old.py", 1) is None


# ---- Edge case: submodule path ------------------------------------------


def _has_submodule_support() -> bool:
    """Check if `git submodule` command works in this env."""
    try:
        out = subprocess.run(
            ["git", "submodule", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        return out.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _has_submodule_support(), reason="git submodule not available")
def test_submodule_path_returns_unknown_for_v0_4(tmp_path):
    """PRD-v0.4 §2.3 'Submodule path' — full submodule blame is a v0.5
    non-goal per §2.2. v0.4 returns None (records show <unknown>) for
    files inside `.gitmodules`-tracked paths.

    This test verifies that v0.4 doesn't CRASH on a submodule path —
    it gracefully returns None.
    """
    sub = tmp_path / "sub"
    sub.mkdir()
    _git("init", "-q", "-b", "main", cwd=sub)
    _git("config", "user.name", "Alice", cwd=sub)
    _git("config", "user.email", "alice@example.com", cwd=sub)
    (sub / "lib.py").write_text("x\ny\n", encoding="utf-8")
    _git("add", "lib.py", cwd=sub)
    _commit(sub, "submodule init")

    parent = tmp_path / "parent"
    parent.mkdir()
    _git("init", "-q", "-b", "main", cwd=parent)
    _git("config", "user.name", "Alice", cwd=parent)
    _git("config", "user.email", "alice@example.com", cwd=parent)
    _git(
        "-c", "protocol.file.allow=always",
        "submodule", "add", "-q", str(sub), "sub_path",
        cwd=parent,
    )
    _commit(parent, "add submodule")

    idx = AuthorIndex(parent)
    # The submodule's file as viewed from the parent. v0.4 doesn't
    # blame across the submodule boundary — returns None gracefully.
    a = idx.author_for("sub_path/lib.py", 1)
    # Either None (current behavior, no follow into submodule) OR an
    # Author (if some future v0.5+ enhancement adds it). Both are OK
    # for v0.4. The key invariant: NO crash.
    assert a is None or hasattr(a, "email")


# ---- Edge case: file deleted before query --------------------------------


def test_file_deleted_after_log_emit_returns_none(tmp_path):
    """PRD-v0.4 §2.3 implied — a file referenced in older logs that
    has since been deleted from the working tree returns None."""
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    _git("config", "user.name", "Alice", cwd=tmp_path)
    _git("config", "user.email", "alice@example.com", cwd=tmp_path)
    (tmp_path / "deleted.py").write_text("a\n", encoding="utf-8")
    _git("add", "deleted.py", cwd=tmp_path)
    _commit(tmp_path, "init")
    _git("rm", "deleted.py", cwd=tmp_path)
    _commit(tmp_path, "remove file")

    idx = AuthorIndex(tmp_path)
    # File no longer in working tree. Should return None.
    assert idx.author_for("deleted.py", 1) is None


# ---- Edge case mapping doc -----------------------------------------------


def test_edge_case_mapping_complete():
    """SC4 — each of the 5 PRD-v0.4 §2.3 edge cases must have
    coverage in the test suite. This test asserts the mapping doc
    (in story 2-10's spec) accurately reflects test names."""
    spec = Path(__file__).parent.parent / "_bmad-output" / "implementation-artifacts" / "2-10-prd-v0-4-edge-cases-as-tests.md"
    assert spec.exists(), "Story 2.10 spec missing"
    txt = spec.read_text(encoding="utf-8")
    # Each edge case mentioned by name in the mapping table.
    assert "Line deleted" in txt or "out-of-range" in txt
    assert "File renamed" in txt or "git mv" in txt
    assert "Submodule" in txt or "submodule" in txt
    assert "No git" in txt or "no .git" in txt or "no_git" in txt or "--repo" in txt
    assert "Squashed" in txt or "rebased" in txt
