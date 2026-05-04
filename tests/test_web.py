"""Tests for the v0.2 Django inspection UI.

Covers the adapter layer (storage-agnostic shape) + the Django views
(list, detail, docs) via the test client. Each test creates a tiny
SQLite fixture in tmp_path so tests are hermetic.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            try:
                h.close()
            except Exception:
                pass
            logging.getLogger().removeHandler(h)
    ulog.clear()


@pytest.fixture
def sqlite_fixture(tmp_path) -> Path:
    """Build a small SQLite fixture covering the filter axes."""
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger("myapp.web").info("user on /home")
    ulog.get_logger("myapp.audio.renderer").info("rendering")
    ulog.get_logger("myapp.audio.renderer").warning("lameenc drift")
    ulog.get_logger("myapp.audio.engine").error("ROM not found")
    ulog.bind(rom_sha="abc123", engine="famitracker")
    ulog.get_logger("myapp.audio.renderer").info("rendered", extra={"frames": 600})
    for h in logging.getLogger().handlers:
        h.flush()
    return db


# ---- Adapter unit tests --------------------------------------------------


def test_sqlite_adapter_total_and_filters(sqlite_fixture):
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    res = ad.query(Filters())
    assert res.total == 5
    # Level filter
    res = ad.query(Filters(levels=["ERROR"]))
    assert res.total == 1
    assert res.records[0].msg == "ROM not found"
    # Sector filter (logger prefix)
    res = ad.query(Filters(loggers=["myapp.audio"]))
    assert res.total == 4
    # File filter
    res = ad.query(Filters(files=[res.records[0].file]))
    assert res.total >= 1
    # Search
    res = ad.query(Filters(search="rendering"))
    assert res.total == 1
    # Bound
    res = ad.query(Filters(bound={"rom_sha": "abc123"}))
    assert res.total == 1


def test_sqlite_adapter_sector_counts(sqlite_fixture):
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    res = ad.query(Filters())
    assert res.sector_counts["myapp"] == 5
    assert res.sector_counts["myapp.audio"] == 4
    assert res.sector_counts["myapp.audio.renderer"] == 3
    assert res.sector_counts["myapp.audio.engine"] == 1
    assert res.sector_counts["myapp.web"] == 1


def test_sqlite_adapter_get_returns_record(sqlite_fixture):
    from ulog.web.viewer.adapters import SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    rec = ad.get(1)
    assert rec is not None
    assert rec.id == 1
    assert ad.get(99999) is None


def test_jsonl_adapter_round_trip(tmp_path):
    """Build a JSONL via JSONLineHandler then read it back."""
    from ulog.web.viewer.adapters import Filters, JSONLAdapter

    path = tmp_path / "logs.jsonl"
    ulog.setup(handlers=["json"], json_path=str(path))
    ulog.get_logger("svc").info("hi")
    ulog.get_logger("svc").error("bye")
    for h in logging.getLogger().handlers:
        h.flush()

    ad = JSONLAdapter(path)
    res = ad.query(Filters())
    assert res.total == 2
    assert res.records[0].level in {"INFO", "ERROR"}
    res = ad.query(Filters(levels=["ERROR"]))
    assert res.total == 1
    assert res.records[0].msg == "bye"


def test_csv_adapter_round_trip(tmp_path):
    from ulog.web.viewer.adapters import CSVAdapter, Filters

    path = tmp_path / "logs.csv"
    ulog.setup(handlers=["csv"], csv_path=str(path))
    ulog.get_logger("svc").info("hi")
    ulog.get_logger("svc").error("bye")
    for h in logging.getLogger().handlers:
        h.flush()

    ad = CSVAdapter(path)
    res = ad.query(Filters())
    assert res.total == 2
    res = ad.query(Filters(levels=["ERROR"]))
    assert res.total == 1


def test_detect_kind():
    from ulog.web.viewer.adapters import detect_kind

    assert detect_kind(Path("foo.sqlite")) == "sqlite"
    assert detect_kind(Path("foo.db")) == "sqlite"
    assert detect_kind(Path("foo.jsonl")) == "jsonl"
    assert detect_kind(Path("foo.ndjson")) == "jsonl"
    assert detect_kind(Path("foo.csv")) == "csv"
    with pytest.raises(ValueError, match="unknown"):
        detect_kind(Path("foo.log"))


# ---- Django view tests ---------------------------------------------------


def _make_django_client(db_path: Path):
    """Configure Django settings + return a test client pointing at db_path."""
    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db_path)
    os.environ["ULOG_LOGS_KIND"] = "sqlite"
    os.environ["ULOG_DEBUG"] = "0"

    import django
    from django.apps import apps as django_apps
    if not django_apps.ready:
        django.setup()
    # Reset module-level adapter cache (tests reuse fixtures)
    from ulog.web.viewer import views as _views
    _views._adapter = None

    from django.test import Client
    return Client()


def test_list_view_returns_200_and_includes_records(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "ULog" in body
    assert "ROM not found" in body
    assert "myapp.audio.renderer" in body


def test_list_view_filter_by_level(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/?level=ERROR")
    body = resp.content.decode()
    assert "ROM not found" in body
    # The "user on /home" INFO record should NOT appear in ERROR-only filter
    assert "user on /home" not in body


def test_list_view_filter_by_sector(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/?logger=myapp.audio.engine")
    body = resp.content.decode()
    assert "ROM not found" in body
    assert "user on /home" not in body
    assert "rendering" not in body


def test_list_view_search(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/?q=rendering")
    body = resp.content.decode()
    assert "rendering" in body
    assert "user on /home" not in body


def test_detail_view(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/r/1/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "user on /home" in body or "rendering" in body


def test_detail_404(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/r/99999/")
    assert resp.status_code == 404


def test_api_records_returns_json(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/api/records/")
    assert resp.status_code == 200
    payload = json.loads(resp.content.decode())
    assert "records" in payload
    assert "total" in payload
    assert payload["total"] == 5
    assert "level_counts" in payload


def test_docs_index(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Quickstart" in body
    assert "Storage" in body or "storage" in body


def test_docs_page_renders_markdown(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/quickstart/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "<h1" in body  # rendered heading
    assert "ulog-web" in body
    # Code-block class from our minimal markdown renderer
    assert "<pre" in body and "<code" in body


def test_docs_unknown_page_404(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/no-such-page/")
    assert resp.status_code == 404
