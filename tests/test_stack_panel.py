"""Tests for v0.12 phase 2 — call-stack panel rendering."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    from ulog import _stack as s
    s.configure(False, False)
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    s.configure(False, False)
    ulog.clear()


def _seed_with_stack(tmp_path: Path) -> tuple[Path, int]:
    db = tmp_path / "stack.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1, capture_stack=True)
    ulog.get_logger().error("boom")
    for h in logging.getLogger().handlers:
        h.flush()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rid = conn.execute(text("SELECT id FROM logs LIMIT 1")).scalar()
    engine.dispose()
    return db, int(rid)


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


def test_stack_panel_renders_when_stack_captured(tmp_path):
    db, rid = _seed_with_stack(tmp_path)
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert 'data-stack-panel="true"' in body
    assert "Call stack" in body
    assert "frames" in body


def test_stack_panel_hidden_without_capture(tmp_path):
    db = tmp_path / "no.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("hi")
    for h in logging.getLogger().handlers:
        h.flush()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rid = conn.execute(text("SELECT id FROM logs LIMIT 1")).scalar()
    engine.dispose()
    body = _client(db).get(f"/r/{int(rid)}/").content.decode("utf-8")
    assert 'data-stack-panel="true"' not in body
