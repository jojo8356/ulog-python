"""Tests for v0.10 phase 2 — Fleet sidebar tree."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog
from ulog.fleet import probe


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


def test_fleet_sidebar_renders_when_probes_present(tmp_path):
    db = tmp_path / "p.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)

    @probe(target="payments.internal", parents=["db.internal"])
    def check():
        return True

    check()
    for h in logging.getLogger().handlers:
        h.flush()

    body = _client(db).get("/").content.decode("utf-8")
    assert ">Fleet<" in body
    assert "payments.internal" in body
    assert "db.internal" in body


def test_fleet_sidebar_hidden_without_probes(tmp_path):
    db = tmp_path / "noprobe.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("regular")
    for h in logging.getLogger().handlers:
        h.flush()

    body = _client(db).get("/").content.decode("utf-8")
    assert ">Fleet<" not in body
