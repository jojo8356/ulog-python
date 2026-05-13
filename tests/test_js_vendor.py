"""Tests for v0.8.2 — Alpine + HTMX vendored under static/ulog/js/."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog

JS_DIR = Path(__file__).resolve().parent.parent / "ulog/web/static/ulog/js"


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


def test_alpine_bundle_committed():
    p = JS_DIR / "alpine.min.js"
    assert p.exists(), f"missing {p}; run `make js-vendor`"
    assert p.stat().st_size > 10_000, "alpine.min.js too small — corrupt?"


def test_htmx_bundle_committed():
    p = JS_DIR / "htmx.min.js"
    assert p.exists(), f"missing {p}; run `make js-vendor`"
    assert p.stat().st_size > 10_000, "htmx.min.js too small — corrupt?"


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


def test_base_template_links_vendored_assets(tmp_path):
    db = _seed(tmp_path)
    body = _client(db).get("/").content.decode("utf-8")
    assert "/static/ulog/js/alpine.min.js" in body
    assert "/static/ulog/js/htmx.min.js" in body


def test_base_template_no_longer_uses_cdn(tmp_path):
    """Should NOT load Alpine/HTMX from jsdelivr anymore."""
    db = _seed(tmp_path)
    body = _client(db).get("/").content.decode("utf-8")
    assert "cdn.jsdelivr.net/npm/alpinejs" not in body
    assert "cdn.jsdelivr.net/npm/htmx" not in body
