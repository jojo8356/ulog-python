"""Tests for Story 6.7 — Detail Resolves / Resolved-by cross-links (FR114)."""

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


def _seed_and_resolve(tmp_path: Path) -> tuple[Path, int, int, str]:
    """Emit one ERROR, resolve it. Return (db, incident_id, resolve_id, hash_hex)."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "rxl.sqlite"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
    )
    ulog.get_logger().error("boom")
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, hex(record_hash) FROM logs WHERE level='ERROR' ORDER BY id")
        ).all()
    engine.dispose()
    incident_id = rows[0][0]
    incident_hash = rows[0][1]
    ulog.resolve(incident_hash, by="Johan", note="rolled back deploy")
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        resolve_id = conn.execute(text("SELECT id FROM logs WHERE msg='RESOLVED' LIMIT 1")).scalar()
    engine.dispose()
    return db, incident_id, int(resolve_id), incident_hash


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


def test_detail_of_incident_shows_resolved_by(tmp_path):
    db, incident_id, _, _ = _seed_and_resolve(tmp_path)
    client = _make_client(db)
    resp = client.get(f"/r/{incident_id}/")
    body = resp.content.decode("utf-8")
    assert "Resolved by" in body
    assert "Johan" in body
    assert "rolled back deploy" in body


def test_detail_of_resolve_record_shows_resolves(tmp_path):
    db, incident_id, resolve_id, _ = _seed_and_resolve(tmp_path)
    client = _make_client(db)
    resp = client.get(f"/r/{resolve_id}/")
    body = resp.content.decode("utf-8")
    assert "Resolves:" in body
    # Cross-link to the incident's detail.
    assert f"/r/{incident_id}/" in body


def test_detail_of_normal_record_no_incident_panel(tmp_path):
    """A record never resolved and not a resolve record → no Incident panel."""
    db = tmp_path / "norm.sqlite"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
    )
    ulog.get_logger().info("just info")
    for h in logging.getLogger().handlers:
        h.flush()
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rec_id = conn.execute(text("SELECT id FROM logs LIMIT 1")).scalar()
    engine.dispose()
    client = _make_client(db)
    resp = client.get(f"/r/{rec_id}/")
    body = resp.content.decode("utf-8")
    assert 'data-incident-panel="true"' not in body
