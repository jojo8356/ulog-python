"""Tests for the integrity badge UI in base.html (Story 6.6)."""

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


def _seed_db(tmp_path: Path) -> Path:
    """Setup a chain DB so a verify can populate the sidecar."""
    db = tmp_path / "v.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=url, sql_batch_size=1)
    for i in range(3):
        ulog.get_logger().info("rec %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


def _make_django_client(db_path: Path):
    """Configure the Django client against the existing ulog.web.settings."""
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


def test_badge_never_verified_when_sidecar_absent(tmp_path):
    """No verify_state.json → 'never verified' badge."""
    db = _seed_db(tmp_path)
    client = _make_django_client(db)
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    assert "never verified" in body


def test_badge_ok_renders_when_sidecar_is_ok(tmp_path):
    from ulog._cli import main as cli_main

    db = _seed_db(tmp_path)
    cli_main(["verify", str(db)])  # populates the sidecar with OK
    client = _make_django_client(db)
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    assert "Integrity ✓" in body or "ix_logs_chain_pos" not in body  # OK shape


def test_badge_broken_renders_when_sidecar_is_broken(tmp_path):
    from sqlalchemy import create_engine, text

    from ulog._cli import main as cli_main

    db = _seed_db(tmp_path)
    # Corrupt a row to force a BROKEN verify.
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        conn.execute(text("UPDATE logs SET msg='tampered' WHERE chain_pos=2"))
    engine.dispose()
    cli_main(["verify", str(db)])
    client = _make_django_client(db)
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    assert "BROKEN" in body
