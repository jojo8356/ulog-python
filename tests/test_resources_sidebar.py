"""Tests for v0.9 phase 2 — Resources sidebar panel."""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path

import pytest

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    # Reset the resources cache between tests.
    from ulog.web.viewer import views as v
    v._RESOURCES_CACHE = None
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    v._RESOURCES_CACHE = None
    ulog.clear()


def _client(db: Path, resources_dir: Path | None):
    if resources_dir is not None:
        os.environ["ULOG_RESOURCES_DIR"] = str(resources_dir)
    else:
        os.environ.pop("ULOG_RESOURCES_DIR", None)
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


def test_resources_panel_renders_with_files(tmp_path):
    res_dir = tmp_path / "proj"
    res_dir.mkdir()
    (res_dir / "ok.json").write_text('{"a": 1}', encoding="utf-8")
    (res_dir / "bad.json").write_text("{", encoding="utf-8")
    db = _seed(tmp_path)

    body = _client(db, res_dir).get("/").content.decode("utf-8")
    assert ">Resources<" in body
    assert "ok.json" in body
    assert "bad.json" in body
    # Counters: 1 broken, 1 ok.
    assert "1✗ / 1✓" in body


def test_resources_panel_hidden_when_env_unset(tmp_path):
    db = _seed(tmp_path)
    body = _client(db, None).get("/").content.decode("utf-8")
    assert ">Resources<" not in body
