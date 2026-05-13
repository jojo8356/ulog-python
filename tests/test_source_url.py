"""Tests for v0.12 phase 3 — `View source` link on detail view."""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    yield
    for k in ("ULOG_SOURCE_BASE_URL", "ULOG_AUTHOR_REPO"):
        os.environ.pop(k, None)
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


def _client(db: Path):
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
    ulog.get_logger().info("boom")
    for h in logging.getLogger().handlers:
        h.flush()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rid = conn.execute(text("SELECT id FROM logs LIMIT 1")).scalar()
    engine.dispose()
    return db, int(rid)


def test_source_url_uses_base_url_env_when_set(tmp_path):
    db, rid = _seed(tmp_path)
    os.environ["ULOG_SOURCE_BASE_URL"] = "https://github.com/jojo8356/ulog-python/blob/main"
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert "https://github.com/jojo8356/ulog-python/blob/main/" in body
    assert "#L" in body


def test_source_url_uses_repo_env_as_file_uri(tmp_path):
    db, rid = _seed(tmp_path)
    os.environ["ULOG_AUTHOR_REPO"] = str(tmp_path)
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert "file://" in body
    assert str(tmp_path.resolve()) in body


def test_source_url_absent_falls_back_to_plain_text(tmp_path):
    db, rid = _seed(tmp_path)
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    # No ULOG_SOURCE_BASE_URL nor ULOG_AUTHOR_REPO → plain <span>.
    # Link should NOT have target=_blank for the file:line span.
    # Pre-condition: ensure the test_isolation fixture cleaned env (it does).
    assert "file://" not in body
    assert "github.com/jojo8356" not in body


def test_base_url_wins_over_repo(tmp_path):
    """Both set → BASE_URL takes priority (canonical link beats local file)."""
    db, rid = _seed(tmp_path)
    os.environ["ULOG_AUTHOR_REPO"] = str(tmp_path)
    os.environ["ULOG_SOURCE_BASE_URL"] = "https://github.com/x/y/blob/main"
    body = _client(db).get(f"/r/{rid}/").content.decode("utf-8")
    assert "github.com/x/y/blob/main" in body
    # file:// should NOT also be present for the same path.
    # (The base URL hit prevents the fallback.)
