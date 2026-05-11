"""Story 2.9 — `/diff/<sha>` view + sha validation (FR81 / NFR-SEC-30)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import ulog
from ulog.web.viewer.views import _validate_sha


@pytest.fixture
def repo_with_commits(tmp_path: Path) -> tuple[Path, str]:
    """Build a small repo with one commit; return (repo_path, full_sha)."""
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
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return tmp_path, sha


@pytest.fixture
def sqlite_fixture(tmp_path: Path) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger("svc").info("hi")
    import logging

    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    return db


def _make_django_client(db_path: Path):
    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db_path)
    os.environ["ULOG_LOGS_KIND"] = "sqlite"
    os.environ["ULOG_DEBUG"] = "0"
    import django
    from django.apps import apps as django_apps

    if not django_apps.ready:
        django.setup()
    from django.conf import settings as _dj_settings

    _dj_settings.ULOG_LOGS_PATH = str(db_path)
    _dj_settings.ULOG_LOGS_KIND = "sqlite"
    from ulog.web.viewer import views as _views

    _views._adapter = None
    from django.test import Client

    return Client()


# ---- AC1: sha format validation ------------------------------------------


def test_validate_sha_accepts_valid_hex():
    assert _validate_sha("a1b2c3d") is True
    assert _validate_sha("ABCDEF1234") is True  # case-insensitive
    assert _validate_sha("0" * 40) is True
    assert _validate_sha("abcd") is True  # min len 4


def test_validate_sha_rejects_invalid():
    assert _validate_sha("") is False
    assert _validate_sha("abc") is False  # too short
    assert _validate_sha("a" * 41) is False  # too long
    assert _validate_sha("xyz123") is False  # non-hex
    assert _validate_sha("abc; rm -rf /") is False  # shell injection attempt
    assert _validate_sha("../etc/passwd") is False  # path traversal attempt
    assert _validate_sha("abc 123") is False  # space


# ---- AC1: invalid sha returns 400 ----------------------------------------


def test_diff_view_invalid_sha_returns_400(sqlite_fixture, monkeypatch):
    monkeypatch.setenv("ULOG_AUTHOR_REPO", "/tmp")
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/diff/abc;rm/")
    assert resp.status_code == 400
    assert b"invalid sha" in resp.content


def test_diff_view_too_short_sha_returns_400(sqlite_fixture, monkeypatch):
    monkeypatch.setenv("ULOG_AUTHOR_REPO", "/tmp")
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/diff/abc/")
    assert resp.status_code == 400


# ---- AC2: missing repo env returns 503 ----------------------------------


def test_diff_view_no_repo_env_returns_503(sqlite_fixture, monkeypatch):
    monkeypatch.delenv("ULOG_AUTHOR_REPO", raising=False)
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/diff/abcdef1234/")
    assert resp.status_code == 503
    assert b"no --repo" in resp.content


# ---- AC3: unknown sha returns 404 ----------------------------------------


def test_diff_view_unknown_sha_returns_404(sqlite_fixture, repo_with_commits, monkeypatch):
    repo, _ = repo_with_commits
    monkeypatch.setenv("ULOG_AUTHOR_REPO", str(repo))
    client = _make_django_client(sqlite_fixture)
    # Valid hex format but not in repo
    resp = client.get("/diff/0123456789abcdef0123456789abcdef01234567/")
    assert resp.status_code == 404
    assert b"not reachable" in resp.content


# ---- AC4: valid sha renders diff ----------------------------------------


def test_diff_view_valid_sha_renders_diff(sqlite_fixture, repo_with_commits, monkeypatch):
    repo, sha = repo_with_commits
    monkeypatch.setenv("ULOG_AUTHOR_REPO", str(repo))
    client = _make_django_client(sqlite_fixture)
    resp = client.get(f"/diff/{sha}/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert 'data-diff-content="true"' in body
    assert sha[:7] in body
    # Commit message + diff content present
    assert "init" in body  # commit message
    assert "foo.py" in body  # filename in diff


def test_diff_view_short_sha_resolves(sqlite_fixture, repo_with_commits, monkeypatch):
    repo, full_sha = repo_with_commits
    monkeypatch.setenv("ULOG_AUTHOR_REPO", str(repo))
    client = _make_django_client(sqlite_fixture)
    short = full_sha[:7]
    resp = client.get(f"/diff/{short}/")
    assert resp.status_code == 200


def test_diff_view_html_escapes_content(sqlite_fixture, repo_with_commits, monkeypatch):
    """Decision D4 — content is HTML-escaped via Django auto-escape."""
    repo, _sha = repo_with_commits
    # Add a file with HTML-like content + commit
    (repo / "evil.py").write_text("<script>alert('xss')</script>\n", encoding="utf-8")
    subprocess.run(["git", "add", "evil.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "<script>"],
        cwd=repo,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "A",
            "GIT_AUTHOR_EMAIL": "a@x",
            "GIT_COMMITTER_NAME": "A",
            "GIT_COMMITTER_EMAIL": "a@x",
        },
        check=True,
    )
    new_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    monkeypatch.setenv("ULOG_AUTHOR_REPO", str(repo))
    client = _make_django_client(sqlite_fixture)
    resp = client.get(f"/diff/{new_sha}/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # Raw <script> must be HTML-escaped, NOT executable
    assert "<script>alert" not in body
    assert "&lt;script&gt;alert" in body
