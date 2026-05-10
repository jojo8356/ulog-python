"""Tests for the debug-only QA checklist page (/_qa/)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import ulog


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


def _make_django_client(db_path: Path, *, debug: bool):
    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db_path)
    os.environ["ULOG_LOGS_KIND"] = "sqlite"
    os.environ["ULOG_DEBUG"] = "1" if debug else "0"
    import django
    from django.apps import apps as django_apps
    if not django_apps.ready:
        django.setup()
    from django.conf import settings as _dj_settings
    _dj_settings.ULOG_LOGS_PATH = str(db_path)
    _dj_settings.ULOG_LOGS_KIND = "sqlite"
    # DEBUG is read at import time, so for tests we force-update:
    _dj_settings.DEBUG = debug
    from ulog.web.viewer import views as _views
    _views._adapter = None
    from django.test import Client
    return Client()


def test_qa_view_404_when_debug_off(sqlite_fixture):
    client = _make_django_client(sqlite_fixture, debug=False)
    resp = client.get("/_qa/")
    assert resp.status_code == 404


def test_qa_view_200_when_debug_on(sqlite_fixture):
    client = _make_django_client(sqlite_fixture, debug=True)
    resp = client.get("/_qa/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "QA manual checklist" in body
    assert "Epic 1" in body and "Epic 2" in body


def test_qa_view_includes_persistence_script(sqlite_fixture):
    client = _make_django_client(sqlite_fixture, debug=True)
    resp = client.get("/_qa/")
    body = resp.content.decode("utf-8")
    # Localstorage key prefix + reset handler
    assert "ulogQA:" in body
    assert "qa-reset" in body
    assert "localStorage.setItem" in body
    assert "localStorage.removeItem" in body


def test_qa_view_renders_all_checkboxes_with_unique_ids(sqlite_fixture):
    """Every checkbox must have a unique data-qa-id (else localStorage collides)."""
    import re
    client = _make_django_client(sqlite_fixture, debug=True)
    resp = client.get("/_qa/")
    body = resp.content.decode("utf-8")
    ids = re.findall(r'data-qa-id="([^"]+)"', body)
    assert len(ids) >= 50, f"expected ≥50 checkboxes, got {len(ids)}"
    assert len(ids) == len(set(ids)), "duplicate data-qa-id detected — localStorage would collide"


def test_qa_link_in_header_only_when_debug(sqlite_fixture):
    """The QA badge in the header must be hidden in production."""
    # Debug ON → link present
    client = _make_django_client(sqlite_fixture, debug=True)
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    assert 'href="/_qa/"' in body or "/_qa/" in body

    # Debug OFF → link absent
    client = _make_django_client(sqlite_fixture, debug=False)
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    assert "/_qa/" not in body


def test_debug_bar_visible_when_debug_on(sqlite_fixture):
    """The debug bar with 'Open QA checklist' button is visible across
    all pages when --debug is active."""
    client = _make_django_client(sqlite_fixture, debug=True)
    for path in ("/", "/r/1/", "/docs/"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        body = resp.content.decode("utf-8")
        assert 'data-debug-bar="true"' in body, f"debug bar missing on {path}"
        assert "DEBUG MODE" in body, f"debug-mode label missing on {path}"
        assert "Open QA checklist" in body, f"QA button missing on {path}"


def test_debug_bar_hidden_when_debug_off(sqlite_fixture):
    """No debug bar in production-mode page renders."""
    client = _make_django_client(sqlite_fixture, debug=False)
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    assert 'data-debug-bar="true"' not in body
    assert "DEBUG MODE" not in body
