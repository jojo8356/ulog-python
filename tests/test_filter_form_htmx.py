"""Tests for v0.8 — HTMX on the records-list sidebar filter form."""

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
    ulog.get_logger().info("a")
    ulog.get_logger().error("b")
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_filter_form_has_htmx_attrs(tmp_path):
    db = _seed(tmp_path)
    body = _client(db).get("/").content.decode("utf-8")
    assert 'id="filter-form"' in body
    assert 'hx-get="/"' in body
    assert "hx-target=" in body
    assert 'hx-push-url="true"' in body


def test_filter_form_fallback_still_works(tmp_path):
    """The form still submits via GET when HTMX is absent (method=get + action url)."""
    db = _seed(tmp_path)
    body = _client(db).get("/").content.decode("utf-8")
    assert 'method="get"' in body
    # Apply button still present.
    assert "Apply" in body or 'type="submit"' in body
