"""Tests for v0.8 — Alpine.js-powered inline search on the cheatsheet."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


def _client(db: Path):
    import os
    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db)
    os.environ["ULOG_LOGS_KIND"] = "sqlite"
    os.environ["ULOG_DEBUG"] = "0"
    import django
    from django.apps import apps as a
    if not a.ready:
        django.setup()
    from django.conf import settings as s
    s.ULOG_LOGS_PATH = str(db)
    s.ULOG_LOGS_KIND = "sqlite"
    s.DEBUG = False
    from ulog.web.viewer import views as v
    v._adapter = None
    from django.test import Client
    return Client()


def _seed(tmp_path: Path) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("seed")
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_cheatsheet_has_alpine_search_input(tmp_path):
    db = _seed(tmp_path)
    body = _client(db).get("/docs/cheatsheet/").content.decode("utf-8")
    assert 'x-data="{ q: \'\' }"' in body
    assert 'x-model="q"' in body
    assert "Filter cheatsheet" in body


def test_other_doc_pages_lack_search(tmp_path):
    """Quickstart and others don't get the search input."""
    db = _seed(tmp_path)
    body = _client(db).get("/docs/quickstart/").content.decode("utf-8")
    assert "x-data" not in body
    assert "Filter cheatsheet" not in body
