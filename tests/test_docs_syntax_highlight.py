"""Tests for PRD-v0.8.1 — Prism.js syntax highlighting on /docs/*."""

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


def _make_client(tmp_path: Path):
    import os

    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("seed")
    for h in logging.getLogger().handlers:
        h.flush()

    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db)
    os.environ["ULOG_LOGS_KIND"] = "sqlite"
    os.environ["ULOG_DEBUG"] = "0"
    import django
    from django.apps import apps as django_apps

    if not django_apps.ready:
        django.setup()
    from django.conf import settings as _dj_settings

    _dj_settings.ULOG_LOGS_PATH = str(db)
    _dj_settings.ULOG_LOGS_KIND = "sqlite"
    _dj_settings.DEBUG = False
    from ulog.web.viewer import views as _views

    _views._adapter = None
    from django.test import Client

    return Client()


def test_docs_page_links_prism_css(tmp_path):
    client = _make_client(tmp_path)
    resp = client.get("/docs/quickstart/")
    body = resp.content.decode("utf-8")
    assert "prismjs@1.30" in body
    assert "prism.min.css" in body


def test_docs_page_loads_prism_core_and_languages(tmp_path):
    client = _make_client(tmp_path)
    resp = client.get("/docs/quickstart/")
    body = resp.content.decode("utf-8")
    assert "prism-core" in body
    for lang in ("python", "bash", "sql", "json", "yaml"):
        assert f"prism-{lang}" in body


def test_docs_page_dark_theme_swap_present(tmp_path):
    client = _make_client(tmp_path)
    resp = client.get("/docs/quickstart/")
    body = resp.content.decode("utf-8")
    assert "prism-tomorrow" in body  # dark theme
    assert 'data-theme="dark"' in body
    assert 'data-theme="light"' in body
