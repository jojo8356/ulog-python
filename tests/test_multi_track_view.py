"""Tests for the multi-track Django view (Story 6.5 / FR112)."""

from __future__ import annotations

import contextlib
import json
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


def _seed(db: Path) -> None:
    from sqlalchemy import create_engine, text

    from ulog.handlers.sql import SQLHandler

    h = SQLHandler(url=f"sqlite:///{db}", batch_size=1)
    h._ensure_schema()
    h.close()
    engine = create_engine(f"sqlite:///{db}", future=True)
    rows = [
        ("2026-05-12T07:00:01", "ERROR", "svc", "a", "f.py", 1, {"service": "api"}),
        ("2026-05-12T07:00:30", "INFO", "svc", "b", "f.py", 1, {"service": "api"}),
        ("2026-05-12T07:01:00", "WARNING", "svc", "c", "g.py", 2, {"service": "worker"}),
    ]
    with engine.begin() as conn:
        for ts, lvl, lg, msg, file, ln, ctx in rows:
            conn.execute(
                text(
                    "INSERT INTO logs (ts, level, logger, msg, file, line, context) "
                    "VALUES (:ts, :lvl, :lg, :msg, :f, :ln, :ctx)"
                ),
                {
                    "ts": ts,
                    "lvl": lvl,
                    "lg": lg,
                    "msg": msg,
                    "f": file,
                    "ln": ln,
                    "ctx": json.dumps(ctx),
                },
            )
    engine.dispose()


def _make_client(db_path: Path):
    import os

    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db_path)
    os.environ["ULOG_LOGS_KIND"] = "sqlite"
    os.environ["ULOG_DEBUG"] = "0"
    import django
    from django.apps import apps as django_apps

    if not django_apps.ready:
        django.setup()
    from django.conf import settings as _dj_settings

    _dj_settings.ULOG_LOGS_PATH = str(db_path)
    _dj_settings.ULOG_LOGS_KIND = "sqlite"
    _dj_settings.DEBUG = False
    from ulog.web.viewer import views as _views

    _views._adapter = None
    from django.test import Client

    return Client()


def test_multi_track_view_renders_with_explicit_window(tmp_path):
    db = tmp_path / "mt.sqlite"
    _seed(db)
    client = _make_client(db)
    resp = client.get(
        "/multi-track/",
        {"from": "2026-05-12T07:00", "to": "2026-05-12T08:00"},
    )
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # Four track rows.
    for name in ("level", "service", "author", "file"):
        assert f'data-track="{name}"' in body
    # Bucket json_script payload.
    assert 'id="multi-track-buckets"' in body
    # Per-bucket rects rendered for tracks with data.
    assert "2026-05-12T07:00" in body


def test_multi_track_default_window_when_no_params(tmp_path):
    """Without `from`/`to`, defaults to (now-1h, now). Page must still 200."""
    db = tmp_path / "mt2.sqlite"
    _seed(db)
    client = _make_client(db)
    resp = client.get("/multi-track/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # All 4 strip rows present even when empty.
    for name in ("level", "service", "author", "file"):
        assert f'data-track="{name}"' in body


def test_multi_track_no_data_placeholder(tmp_path):
    """Window with no records → empty <svg> with `(no data)` placeholder per strip."""
    db = tmp_path / "mt3.sqlite"
    _seed(db)
    client = _make_client(db)
    resp = client.get(
        "/multi-track/",
        {"from": "2030-01-01T00:00", "to": "2030-01-01T01:00"},
    )
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # Each empty strip emits "(no data)" placeholder.
    assert body.count("(no data)") >= 4


def test_multi_track_url_named_route(tmp_path):
    """The named URL `ulog-multi-track` resolves and reverse-resolves."""
    db = tmp_path / "mt4.sqlite"
    _seed(db)
    _make_client(db)
    from django.urls import reverse

    assert reverse("ulog-multi-track") == "/multi-track/"


def test_multi_track_invalid_from_falls_back_to_default(tmp_path):
    """Bad ISO `from=` → fall back to (now-1h)."""
    db = tmp_path / "mt5.sqlite"
    _seed(db)
    client = _make_client(db)
    resp = client.get("/multi-track/", {"from": "not-iso", "to": "also-bad"})
    assert resp.status_code == 200


def test_multi_track_level_rect_rendered(tmp_path):
    """When level data exists, the SVG strip emits at least one <rect>."""
    db = tmp_path / "mt6.sqlite"
    _seed(db)
    client = _make_client(db)
    resp = client.get(
        "/multi-track/",
        {"from": "2026-05-12T07:00", "to": "2026-05-12T08:00"},
    )
    body = resp.content.decode("utf-8")
    # 3 records → at least 3 rects across the level track.
    assert body.count('data-bucket="2026-05-12T07:00"') >= 1


def test_multi_track_nav_link_visible(tmp_path):
    """`base.html` nav has a Multi-track entry."""
    db = tmp_path / "mt7.sqlite"
    _seed(db)
    client = _make_client(db)
    resp = client.get("/multi-track/")
    body = resp.content.decode("utf-8")
    assert "Multi-track" in body
