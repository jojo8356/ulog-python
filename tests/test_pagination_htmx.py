"""Tests for v0.8 — HTMX pagination on list.html."""

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


def _seed_many(tmp_path: Path, n: int = 150) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=50)
    log = ulog.get_logger()
    for i in range(n):
        log.info("record %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_pagination_carries_htmx_attrs(tmp_path):
    """When > 100 records, Prev/Next get hx-* attrs."""
    db = _seed_many(tmp_path, 150)
    body = _client(db).get("/").content.decode("utf-8")
    assert "data-pagination" in body
    # Next link present, with hx-get pointing at page=2.
    assert 'hx-get="?' in body
    assert "page=2" in body
    assert 'hx-target="closest main"' in body
    assert 'hx-push-url="true"' in body


def test_pagination_fallback_href_still_present(tmp_path):
    """Graceful degradation: href= is still there for no-JS users."""
    db = _seed_many(tmp_path, 150)
    body = _client(db).get("/").content.decode("utf-8")
    # The Next link MUST have both href and hx-get (same target).
    assert 'href="?' in body and 'hx-get="?' in body


def test_pagination_absent_for_small_archive(tmp_path):
    db = _seed_many(tmp_path, 5)
    body = _client(db).get("/").content.decode("utf-8")
    assert "data-pagination" not in body
