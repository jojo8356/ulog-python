"""Story 2.6 — Authors sidebar block render + ghost-count plumbing."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import ulog
from ulog.web.viewer.adapters import Filters
from ulog.web.viewer.blame import (
    Author,
    AuthorIndex,
    _FileCache,
    set_global_index,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    set_global_index(None)
    yield
    set_global_index(None)


@pytest.fixture
def sqlite_fixture(tmp_path: Path) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger("svc").info("hi from svc")
    ulog.get_logger("audio").error("boom")
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


def _populate_idx(tmp_path: Path, files_to_authors: dict[str, Author]) -> AuthorIndex:
    """Populate idx with stub files so mtime checks pass."""
    idx = AuthorIndex(tmp_path)
    for f, a in files_to_authors.items():
        path = tmp_path / f
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stub\n", encoding="utf-8")
        mtime = os.stat(path).st_mtime
        # Build cache for any line — match the test fixture's actual record file/line
        idx._cache[f] = _FileCache(mtime=mtime, blames={})
        # Add Author for whatever lines the records emit (use a wide range).
        for line in range(1, 1000):
            idx._cache[f].blames[line] = a
    return idx


def test_filters_dataclass_has_authors_and_show_unknown_fields():
    """AC0 — sanity: Filters extended"""
    f = Filters()
    assert f.authors == []
    assert f.show_unknown is True
    assert f.is_empty()
    f2 = Filters(authors=["x@y"])
    assert not f2.is_empty()


def test_authors_block_hidden_when_idx_is_none(sqlite_fixture, tmp_path):
    """AC5 — when no idx is set in the singleton, the Authors block is absent"""
    set_global_index(None)
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert 'data-authors-block="true"' not in body


def test_authors_block_renders_when_idx_is_set(sqlite_fixture, tmp_path):
    """AC1 + AC2 — Authors block rendered + each author shown with email"""
    a = Author(name="Alice", email="alice@example.com", sha="a" * 40, ts=1700000000)
    # SQL handler stores record.filename (BASENAME) in the `file` column,
    # so the idx must key on basename. Stub the basename file under
    # AuthorIndex's repo_root (tmp_path) so mtime-check passes.
    basename = Path(__file__).name  # "test_authors_sidebar.py"
    idx = AuthorIndex(tmp_path)
    stub = tmp_path / basename
    stub.write_text("stub\n", encoding="utf-8")
    mtime = os.stat(stub).st_mtime
    idx._cache[basename] = _FileCache(
        mtime=mtime,
        blames={i: a for i in range(1, 500)},
    )
    set_global_index(idx)

    client = _make_django_client(sqlite_fixture)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert 'data-authors-block="true"' in body
    # Author name appears
    assert "Alice" in body
    # Email partially shown (truncated to 20 chars max but real one is short)
    assert "alice@example.com" in body
    # "Show unknown" toggle is present
    assert "show_unknown" in body


def test_authors_block_includes_unknown_when_present(sqlite_fixture, tmp_path):
    """AC3 — <unknown> row shown last when unknown_count > 0"""
    # idx with NO blames → all records go to <unknown>
    idx = AuthorIndex(tmp_path)
    set_global_index(idx)
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert 'data-authors-block="true"' in body
    # <unknown> entry present (HTML-escaped)
    assert "&lt;unknown&gt;" in body


def test_parse_filters_reads_author_query_param():
    """Story 2.7 prep — _parse_filters honors ?author=foo&author=bar"""
    from django.test import RequestFactory
    from ulog.web.viewer.views import _parse_filters

    req = RequestFactory().get("/", {"author": ["a@x", "b@y"]})
    f = _parse_filters(req)
    assert f.authors == ["a@x", "b@y"]


def test_parse_filters_show_unknown_default_on():
    from django.test import RequestFactory
    from ulog.web.viewer.views import _parse_filters

    req = RequestFactory().get("/")
    f = _parse_filters(req)
    assert f.show_unknown is True


def test_parse_filters_show_unknown_off_via_query():
    from django.test import RequestFactory
    from ulog.web.viewer.views import _parse_filters

    req = RequestFactory().get("/", {"show_unknown": "0"})
    f = _parse_filters(req)
    assert f.show_unknown is False
