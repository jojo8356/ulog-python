"""Story 2.8 — detail-view "Authored by" panel."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import ulog
from ulog.web.viewer.blame import (
    Author,
    AuthorIndex,
    _FileCache,
    set_global_index,
)
from ulog.web.viewer.views import _relative_date


@pytest.fixture(autouse=True)
def _reset():
    set_global_index(None)
    yield
    set_global_index(None)


@pytest.fixture
def sqlite_fixture(tmp_path: Path) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger("svc").info("hello world")
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


# ---- AC5: relative date helper -------------------------------------------


def test_relative_date_now():
    now = int(time.time())
    s = _relative_date(now)
    assert s in ("just now", "1 minute ago", "0 minutes ago")  # tolerate clock skew


def test_relative_date_minutes():
    assert _relative_date(int(time.time()) - 120) == "2 minutes ago"
    assert _relative_date(int(time.time()) - 60) == "1 minute ago"


def test_relative_date_hours():
    assert _relative_date(int(time.time()) - 3 * 3600) == "3 hours ago"


def test_relative_date_days():
    assert _relative_date(int(time.time()) - 6 * 86400) == "6 days ago"


def test_relative_date_months():
    assert _relative_date(int(time.time()) - 60 * 86400) == "2 months ago"


def test_relative_date_years():
    assert _relative_date(int(time.time()) - 800 * 86400) == "2 years ago"


def test_relative_date_in_future():
    assert _relative_date(int(time.time()) + 1000) == "in the future"


# ---- AC1 + AC3: panel renders with all fields ----------------------------


def test_authored_by_panel_renders(sqlite_fixture, tmp_path):
    a = Author(
        name="Alice",
        email="alice@example.com",
        sha="abc1234567890" * 3 + "abc",  # 42 chars - truncate to 40
        ts=int(time.time()) - 6 * 86400,
    )
    # Replace sha length to be exactly 40 chars
    a = Author(name="Alice", email="alice@example.com", sha="a" * 40, ts=int(time.time()) - 6 * 86400)
    basename = "test_authors_detail_panel.py"  # the test file emitting the log
    idx = AuthorIndex(tmp_path)
    stub = tmp_path / basename
    stub.write_text("stub\n", encoding="utf-8")
    mtime = os.stat(stub).st_mtime
    idx._cache[basename] = _FileCache(mtime=mtime, blames={i: a for i in range(1, 500)})
    set_global_index(idx)

    client = _make_django_client(sqlite_fixture)
    resp = client.get("/r/1/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert 'data-authored-by-panel="true"' in body
    assert "Alice" in body
    assert "alice@example.com" in body
    assert "aaaaaaa" in body  # 7-char short sha (a*7)
    # Relative date present
    assert "6 days ago" in body or "5 days ago" in body  # tolerate boundary
    # 2 links present
    assert "view all records from this author" in body
    assert "view diff" in body
    assert 'href="/diff/' + "a" * 40 + '/"' in body


def test_authored_by_panel_hidden_when_no_author(sqlite_fixture):
    """AC2 — when idx has no entry for this record, panel is absent."""
    set_global_index(None)
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/r/1/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert 'data-authored-by-panel="true"' not in body
