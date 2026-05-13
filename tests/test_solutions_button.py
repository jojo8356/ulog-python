"""Tests for v0.16 finition — Search solutions button + ?solutions=1 endpoint."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import ulog
from ulog._fixes import resolve_fix, signature


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


def _seed(tmp_path: Path) -> tuple[Path, int]:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().error("boom")
    for h in logging.getLogger().handlers:
        h.flush()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rid = conn.execute(text("SELECT id FROM logs LIMIT 1")).scalar()
    engine.dispose()
    return db, int(rid)


def test_search_button_visible_on_detail(tmp_path):
    db, rid = _seed(tmp_path)
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert 'data-solution-search="true"' in body
    assert "Search solutions" in body


def test_solutions_endpoint_returns_no_results_msg(tmp_path):
    db, rid = _seed(tmp_path)
    resp = _client(db).get(f"/r/{rid}/?solutions=1")
    body = resp.content.decode("utf-8")
    assert "No solutions yet" in body


def test_solutions_endpoint_returns_local_match(tmp_path):
    db, rid = _seed(tmp_path)
    resolve_fix(db, signature("boom"), "restarted db pool", "Johan")
    resp = _client(db).get(f"/r/{rid}/?solutions=1")
    body = resp.content.decode("utf-8")
    assert "local" in body
    assert "restarted db pool" in body
    assert "Johan" in body


def test_consent_param_passed_to_unified_search(tmp_path):
    from unittest.mock import patch
    db, rid = _seed(tmp_path)
    with patch("ulog._solutions.unified_search", return_value=[]) as m:
        _client(db).get(f"/r/{rid}/?solutions=1&consent=1")
        assert m.call_args.kwargs["consent_community"] is True
    with patch("ulog._solutions.unified_search", return_value=[]) as m:
        _client(db).get(f"/r/{rid}/?solutions=1")
        assert m.call_args.kwargs["consent_community"] is False
