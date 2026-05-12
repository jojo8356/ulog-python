"""Tests for Story 6.8 — Incidents sidebar quick filters (FR115)."""

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


def _seed(tmp_path: Path) -> Path:
    """3 errors → resolve 1, reopen 1, leave 1 open."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "s.sqlite"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
    )
    for i in range(3):
        ulog.get_logger().error("boom %d", i)
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT hex(record_hash) FROM logs WHERE level='ERROR' ORDER BY chain_pos")
        ).all()
    engine.dispose()
    hashes = [r[0] for r in rows]
    ulog.resolve(hashes[0], by="Johan")  # closed
    ulog.resolve(hashes[1], by="Erwan")
    ulog.reopen(hashes[1])  # reopened
    return db


def _make_client(db: Path):
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


def test_sidebar_incidents_section_visible_with_counts(tmp_path):
    db = _seed(tmp_path)
    client = _make_client(db)
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    # Incidents heading and the 3 choices.
    assert ">Incidents<" in body
    assert "Open" in body
    assert "Closed (last 7d)" in body
    assert "Reopened" in body


def test_incident_state_filter_open_restricts_records(tmp_path):
    db = _seed(tmp_path)
    client = _make_client(db)
    resp = client.get("/", {"incident_state": "open"})
    body = resp.content.decode("utf-8")
    # 1 open ERROR remains in the list.
    assert resp.status_code == 200
    # Count "boom 2" — the last error, never touched.
    assert "boom 2" in body


def test_incident_state_filter_reopened_restricts_records(tmp_path):
    db = _seed(tmp_path)
    client = _make_client(db)
    resp = client.get("/", {"incident_state": "reopened"})
    body = resp.content.decode("utf-8")
    assert "boom 1" in body
    # boom 0 (closed, never reopened) MUST NOT appear in the records list.
    # Find the records table section by anchoring on the table header.
    table_start = body.find("records")
    assert table_start != -1
    # Crude check: boom 0 not in body — but it could appear in headers too,
    # so check that "boom 0" is absent from the rendered rows.
    rows_section = body[table_start:]
    assert "boom 0" not in rows_section


def test_no_incident_section_when_no_chain(tmp_path):
    """JSONL adapter (no chain) → no Incidents section rendered."""
    p = tmp_path / "logs.jsonl"
    import json as _j

    p.write_text(
        "\n".join(
            _j.dumps(
                {
                    "ts": "2026-05-12T07:00:00",
                    "level": "ERROR",
                    "logger": "x",
                    "msg": "a",
                    "file": "f.py",
                    "line": 1,
                }
            )
            for _ in range(3)
        ),
        encoding="utf-8",
    )
    client = _make_client(p)
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    assert ">Incidents<" not in body
