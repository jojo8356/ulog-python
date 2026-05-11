"""Story 2.11 — `/docs/author-filter/` page render."""

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


def test_author_filter_doc_page_renders(sqlite_fixture):
    """AC1 + AC4 — page renders, no raw markdown syntax leaking"""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/author-filter/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # AC2 — content checks
    assert "Author filter" in body
    assert "git blame" in body
    assert "&lt;unknown&gt;" in body or "<unknown>" in body
    assert "--repo" in body or "--repo" in body
    assert "code author" in body.lower()
    assert "find errors in code lin wrote" in body.lower() or "lin wrote this week" in body.lower()
    # AC4 — markdown syntax not leaking (no raw ``` or ## or **)
    assert "```" not in body  # fenced code blocks rendered (in-house renderer)
    # Must contain rendered code (inline backticks → <code class="..."> at minimum)
    assert "<code" in body or "<pre" in body


def test_author_filter_doc_page_listed_in_index(sqlite_fixture):
    """AC3"""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "Author filter" in body
    assert "/docs/author-filter/" in body


def test_author_filter_doc_page_includes_cli_flags(sqlite_fixture):
    """AC2 — CLI flags listed"""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/author-filter/")
    body = resp.content.decode("utf-8")
    assert "--no-author-index" in body
    assert "--rebuild-author-index" in body


def test_author_filter_doc_page_includes_security_section(sqlite_fixture):
    """AC2 — security section + sha regex documented"""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/author-filter/")
    body = resp.content.decode("utf-8")
    assert "Security" in body or "security" in body
    # Sha regex (literal pattern in markdown)
    assert "[0-9a-f]" in body
