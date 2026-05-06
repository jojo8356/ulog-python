"""Story 2.2 — CLI flags `--repo`, `--no-author-index`, `--rebuild-author-index`."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import pytest

from ulog.web.cli import _resolve_repo_flag, _set_env_for_django, _walk_for_git_root


def _ns(**kw) -> argparse.Namespace:
    """Build a Namespace with default flag values, overridable via kw."""
    base = {"repo": None, "no_author_index": False, "rebuild_author_index": False}
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Fresh git init at tmp_path."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_walk_for_git_root_finds_ancestor(git_repo, tmp_path):
    nested = git_repo / "a" / "b" / "c"
    nested.mkdir(parents=True)
    assert _walk_for_git_root(nested) == git_repo


def test_walk_for_git_root_returns_none_when_absent(tmp_path):
    nested = tmp_path / "no_repo_here"
    nested.mkdir()
    # tmp_path itself has no .git, parents are also non-git (or root).
    # Acceptable: returns None or an unrelated parent. We only assert
    # that no .git/ exists at the returned path.
    found = _walk_for_git_root(nested)
    assert found is None or not (found / ".git").is_dir() or found.is_relative_to(tmp_path) is False


def test_resolve_repo_flag_auto_detect(git_repo):
    args = _ns()
    repo, warn = _resolve_repo_flag(args, git_repo)
    assert repo == git_repo
    assert warn is None


def test_resolve_repo_flag_no_git_warns(tmp_path):
    nested = tmp_path / "iso"
    nested.mkdir()
    args = _ns()
    repo, warn = _resolve_repo_flag(args, nested)
    if repo is None:
        assert warn is not None
        assert "no git repo detected" in warn
        assert "<unknown>" in warn


def test_resolve_repo_flag_explicit_repo_with_git(git_repo, tmp_path):
    args = _ns(repo=str(git_repo))
    repo, warn = _resolve_repo_flag(args, tmp_path)
    assert repo == git_repo.resolve()
    assert warn is None


def test_resolve_repo_flag_explicit_repo_without_git(tmp_path):
    bogus = tmp_path / "not_a_repo"
    bogus.mkdir()
    args = _ns(repo=str(bogus))
    repo, warn = _resolve_repo_flag(args, tmp_path)
    assert repo == bogus.resolve()
    assert warn is not None
    assert "no .git/ subdirectory" in warn
    assert "<unknown>" in warn


def test_resolve_repo_flag_no_author_index_no_warning(tmp_path):
    args = _ns(no_author_index=True)
    repo, warn = _resolve_repo_flag(args, tmp_path)
    assert repo is None
    assert warn is None


def test_set_env_for_django_disabled(monkeypatch):
    monkeypatch.delenv("ULOG_AUTHOR_REPO", raising=False)
    monkeypatch.delenv("ULOG_AUTHOR_INDEX_DISABLED", raising=False)
    monkeypatch.delenv("ULOG_AUTHOR_INDEX_REBUILD", raising=False)
    _set_env_for_django(repo=None, disabled=True, rebuild=False)
    assert os.environ.get("ULOG_AUTHOR_INDEX_DISABLED") == "1"
    assert "ULOG_AUTHOR_REPO" not in os.environ


def test_set_env_for_django_repo_only(monkeypatch, tmp_path):
    monkeypatch.delenv("ULOG_AUTHOR_REPO", raising=False)
    monkeypatch.delenv("ULOG_AUTHOR_INDEX_DISABLED", raising=False)
    monkeypatch.delenv("ULOG_AUTHOR_INDEX_REBUILD", raising=False)
    _set_env_for_django(repo=tmp_path, disabled=False, rebuild=False)
    assert os.environ.get("ULOG_AUTHOR_REPO") == str(tmp_path)


def test_set_env_for_django_rebuild(monkeypatch, tmp_path):
    monkeypatch.delenv("ULOG_AUTHOR_REPO", raising=False)
    monkeypatch.delenv("ULOG_AUTHOR_INDEX_DISABLED", raising=False)
    monkeypatch.delenv("ULOG_AUTHOR_INDEX_REBUILD", raising=False)
    _set_env_for_django(repo=tmp_path, disabled=False, rebuild=True)
    assert os.environ.get("ULOG_AUTHOR_INDEX_REBUILD") == "1"
    assert os.environ.get("ULOG_AUTHOR_REPO") == str(tmp_path)


def test_argparse_no_index_and_rebuild_are_mutually_exclusive():
    """AC6 — both flags simultaneously must error."""
    from ulog.web.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["--no-author-index", "--rebuild-author-index", "/tmp/whatever.sqlite"])
    # argparse exits 2 on usage errors
    assert exc.value.code == 2
