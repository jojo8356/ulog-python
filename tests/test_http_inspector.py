"""Tests for PRD-v0.11 — HTTP request inspector panel."""

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
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


def _seed(tmp_path: Path, ctx: dict) -> tuple[Path, int]:
    db = tmp_path / "h.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    with ulog.context(**ctx):
        ulog.get_logger().info("http call")
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


def test_http_panel_renders_when_method_and_url_present(tmp_path):
    db, rid = _seed(tmp_path, {"method": "POST", "url": "https://api.example.com/v1/foo"})
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert 'data-http-panel="true"' in body
    assert "POST" in body
    assert "https://api.example.com/v1/foo" in body


def test_http_panel_hidden_when_missing_method_or_url(tmp_path):
    db, rid = _seed(tmp_path, {"some": "field"})
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert 'data-http-panel="true"' not in body


def test_sensitive_headers_masked(tmp_path):
    db, rid = _seed(
        tmp_path,
        {
            "method": "GET",
            "url": "https://a/b",
            "headers": {"Authorization": "Bearer abc", "X-Trace": "ok"},
        },
    )
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    # Within the HTTP panel: Authorization masked, X-Trace untouched.
    panel = body.split('data-http-panel="true"', 1)[1]
    assert "Authorization: ***" in panel
    assert "X-Trace: ok" in panel
    # The masked form (***) appears in the curl-button data-ctx too.
    assert "&quot;Authorization&quot;: &quot;***&quot;" in body
    # The bound-context dump above the panel may still show the raw header
    # (v0.2 behaviour); that's a separate audit surface from the HTTP panel.


def test_curl_button_carries_method_url_in_data_attr(tmp_path):
    db, rid = _seed(tmp_path, {"method": "DELETE", "url": "https://a/users/42"})
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert "Copy as curl" in body
    assert "DELETE" in body
    assert "users/42" in body


def test_status_code_styling(tmp_path):
    db, rid = _seed(tmp_path, {"method": "GET", "url": "https://a/b", "status_code": 503})
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert "503" in body
    # 5xx → red.
    assert "bg-red-600" in body


def test_body_renders_when_present(tmp_path):
    db, rid = _seed(
        tmp_path,
        {
            "method": "POST",
            "url": "https://a/b",
            "body": '{"user_id": 42, "action": "checkout"}',
        },
    )
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert "user_id" in body
    assert "checkout" in body
