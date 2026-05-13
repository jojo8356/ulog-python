"""Tests for the new cheatsheet doc page."""

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


def test_cheatsheet_renders(tmp_path):
    db = _seed(tmp_path)
    resp = _client(db).get("/docs/cheatsheet/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "Cheat sheet" in body
    # Spot-check: contains references to multiple CLI commands.
    for cmd in ("ulog web", "ulog verify", "ulog incidents", "ulog snapshot", "ulog export-html"):
        assert cmd in body


def test_cheatsheet_listed_in_docs_index(tmp_path):
    db = _seed(tmp_path)
    body = _client(db).get("/docs/").content.decode("utf-8")
    assert "Cheat sheet" in body


def test_docs_index_lists_v0_5_v0_6_pages(tmp_path):
    db = _seed(tmp_path)
    body = _client(db).get("/docs/").content.decode("utf-8")
    assert "Forensic black box" in body
    assert "Static HTML export" in body
