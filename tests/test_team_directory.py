"""Tests for v0.4.3 — /team/ directory."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog
from ulog.web.viewer.views import _infer_github_url


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


def test_team_route_renders_without_indexer(tmp_path):
    """No --repo / no AuthorIndex → page renders with empty state."""
    db = _seed(tmp_path)
    resp = _client(db).get("/team/")
    assert resp.status_code == 200
    assert "No author indexer active" in resp.content.decode("utf-8")


def test_team_route_named_url(tmp_path):
    _seed(tmp_path)
    _client(tmp_path / "logs.sqlite")
    from django.urls import reverse
    assert reverse("ulog-team") == "/team/"


def test_infer_github_url_noreply_pattern():
    assert _infer_github_url("12345+jojo8356@users.noreply.github.com") == "https://github.com/jojo8356"
    assert _infer_github_url("jojo8356@users.noreply.github.com") == "https://github.com/jojo8356"


def test_infer_github_url_regular_email_returns_none():
    assert _infer_github_url("alice@example.com") is None
