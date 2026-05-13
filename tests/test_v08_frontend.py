"""Tests for v0.8 — Alpine.js + HTMX integration."""

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


def test_base_template_loads_alpine_and_htmx(tmp_path):
    db = _seed(tmp_path)
    body = _client(db).get("/").content.decode("utf-8")
    assert "alpinejs@3.14" in body
    assert "htmx.org@2.0" in body
    # Alpine is `defer`red so the FOUC-prevention script fires first.
    assert 'defer src="https://cdn.jsdelivr.net/npm/alpinejs' in body


def test_multi_track_form_has_htmx_attrs(tmp_path):
    db = _seed(tmp_path)
    body = _client(db).get("/multi-track/").content.decode("utf-8")
    assert 'hx-get="/multi-track/"' in body
    assert "hx-target=" in body
    assert "data-multi-track-root" in body
    assert 'hx-push-url="true"' in body


def test_multi_track_form_works_without_htmx_fallback(tmp_path):
    """Without `HX-Request`, the view returns a full page (no partial)."""
    db = _seed(tmp_path)
    resp = _client(db).get("/multi-track/", {"from": "2026-05-01T00:00", "to": "2026-05-02T00:00"})
    body = resp.content.decode("utf-8")
    # Full page contains <html and the form.
    assert "<html" in body
    assert "<form" in body
