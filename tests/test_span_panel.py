"""Tests for v0.7 phase 2 — span panel."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

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


def test_span_panel_renders_for_span_record(tmp_path):
    db = tmp_path / "spans.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    with ulog.span("setup_db"):
        pass
    for h in logging.getLogger().handlers:
        h.flush()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rid = conn.execute(text("SELECT id FROM logs LIMIT 1")).scalar()
    engine.dispose()
    body = _client(db).get(f"/r/{int(rid)}/").content.decode("utf-8")
    assert 'data-span-panel="true"' in body
    assert "setup_db" in body
    assert "(root span)" in body


def test_span_panel_hidden_for_non_span(tmp_path):
    db = tmp_path / "regular.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("regular")
    for h in logging.getLogger().handlers:
        h.flush()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rid = conn.execute(text("SELECT id FROM logs LIMIT 1")).scalar()
    engine.dispose()
    body = _client(db).get(f"/r/{int(rid)}/").content.decode("utf-8")
    assert 'data-span-panel="true"' not in body


def test_span_panel_shows_parent_link(tmp_path):
    db = tmp_path / "nested.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    with ulog.span("outer"), ulog.span("inner"):
        pass
    for h in logging.getLogger().handlers:
        h.flush()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        # First emitted span = inner (innermost finishes first).
        rid = conn.execute(text("SELECT id FROM logs WHERE logger='ulog.span' ORDER BY id LIMIT 1")).scalar()
    engine.dispose()
    body = _client(db).get(f"/r/{int(rid)}/").content.decode("utf-8")
    assert 'data-span-panel="true"' in body
    assert "inner" in body
    assert "parent:" in body
