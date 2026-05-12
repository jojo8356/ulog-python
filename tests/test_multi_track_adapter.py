"""Tests for the multi-track adapter method (Story 6.4 / FR112, D1)."""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path

import pytest

import ulog
from ulog.web.viewer.adapters import (
    CSVAdapter,
    Filters,
    JSONLAdapter,
    SQLiteAdapter,
)
from ulog.web.viewer.multi_track import (
    SUPPORTED_TRACKS,
    BucketCount,
    MultiTrackResult,
)


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


def test_dataclasses_basic_shape():
    bc = BucketCount(bucket="2026-05-12T07:00", value="ERROR", count=3)
    res = MultiTrackResult(
        tracks={"level": [bc]},
        window=(datetime(2026, 5, 12, 7, 0), datetime(2026, 5, 12, 8, 0)),
        bucket_size_s=60,
    )
    assert res.tracks["level"][0] == bc
    assert res.bucket_size_s == 60


def test_supported_tracks_exposed():
    assert "level" in SUPPORTED_TRACKS
    assert "service" in SUPPORTED_TRACKS
    assert "file" in SUPPORTED_TRACKS
    assert "author" in SUPPORTED_TRACKS


# ---- SQLite ----


def _seed_sqlite(db: Path) -> SQLiteAdapter:
    """Insert known records (no chain) for multi_track tests."""
    from sqlalchemy import create_engine, text

    from ulog.handlers.sql import SQLHandler

    h = SQLHandler(url=f"sqlite:///{db}", batch_size=1)
    h._ensure_schema()
    h.close()
    engine = create_engine(f"sqlite:///{db}", future=True)
    rows = [
        ("2026-05-12T07:00:01", "ERROR", "svc", "boom", "a.py", 10, {"service": "api"}),
        ("2026-05-12T07:00:30", "ERROR", "svc", "boom2", "a.py", 10, {"service": "api"}),
        ("2026-05-12T07:01:00", "INFO", "svc", "ok", "b.py", 20, {"service": "worker"}),
        ("2026-05-12T07:01:30", "WARNING", "svc", "warn", "b.py", 20, {"service": "worker"}),
        ("2026-05-12T08:00:01", "ERROR", "svc", "out-of-window", "c.py", 30, {"service": "api"}),
    ]
    with engine.begin() as conn:
        for ts, lvl, logger, msg, file, line, ctx in rows:
            conn.execute(
                text(
                    "INSERT INTO logs (ts, level, logger, msg, file, line, context) "
                    "VALUES (:ts, :lvl, :lg, :msg, :f, :ln, :ctx)"
                ),
                {
                    "ts": ts,
                    "lvl": lvl,
                    "lg": logger,
                    "msg": msg,
                    "f": file,
                    "ln": line,
                    "ctx": json.dumps(ctx),
                },
            )
    engine.dispose()
    return SQLiteAdapter(db)


def test_sqlite_multi_track_groups_by_minute_and_level(tmp_path):
    a = _seed_sqlite(tmp_path / "m.sqlite")
    res = a.multi_track(
        filters=Filters(),
        tracks=["level"],
        window_start=datetime(2026, 5, 12, 7, 0),
        window_end=datetime(2026, 5, 12, 8, 0),
    )
    # 07:00 → 2 ERROR; 07:01 → 1 INFO + 1 WARNING.
    level_cells = {(c.bucket, c.value): c.count for c in res.tracks["level"]}
    assert level_cells == {
        ("2026-05-12T07:00", "ERROR"): 2,
        ("2026-05-12T07:01", "INFO"): 1,
        ("2026-05-12T07:01", "WARNING"): 1,
    }
    assert res.bucket_size_s == 60


def test_sqlite_multi_track_service_via_json_extract(tmp_path):
    a = _seed_sqlite(tmp_path / "m2.sqlite")
    res = a.multi_track(
        filters=Filters(),
        tracks=["service"],
        window_start=datetime(2026, 5, 12, 7, 0),
        window_end=datetime(2026, 5, 12, 8, 0),
    )
    cells = {(c.bucket, c.value): c.count for c in res.tracks["service"]}
    assert cells[("2026-05-12T07:00", "api")] == 2
    assert cells[("2026-05-12T07:01", "worker")] == 2


def test_sqlite_multi_track_window_filter_excludes_outside(tmp_path):
    a = _seed_sqlite(tmp_path / "m3.sqlite")
    res = a.multi_track(
        filters=Filters(),
        tracks=["file"],
        window_start=datetime(2026, 5, 12, 7, 0),
        window_end=datetime(2026, 5, 12, 8, 0),
    )
    files = {c.value for c in res.tracks["file"]}
    assert "c.py" not in files  # 08:00:01 is outside the [07:00, 08:00) window
    assert files == {"a.py", "b.py"}


def test_sqlite_multi_track_author_returns_empty(tmp_path):
    """Author resolution is in Story 6.5 (view layer) — adapter returns []."""
    a = _seed_sqlite(tmp_path / "m4.sqlite")
    res = a.multi_track(
        filters=Filters(),
        tracks=["author"],
        window_start=datetime(2026, 5, 12, 7, 0),
        window_end=datetime(2026, 5, 12, 8, 0),
    )
    assert res.tracks["author"] == []


def test_unknown_track_raises_keyerror(tmp_path):
    a = _seed_sqlite(tmp_path / "m5.sqlite")
    with pytest.raises(KeyError):
        a.multi_track(
            filters=Filters(),
            tracks=["nonexistent"],
            window_start=datetime(2026, 5, 12, 7, 0),
            window_end=datetime(2026, 5, 12, 8, 0),
        )


# ---- JSONL / CSV ----


def test_jsonl_multi_track_in_memory(tmp_path):
    p = tmp_path / "logs.jsonl"
    # JSONL flat format: extra keys become context (per _payload_to_record).
    lines = [
        {
            "ts": "2026-05-12T07:00:00",
            "level": "ERROR",
            "logger": "x",
            "msg": "a",
            "file": "f.py",
            "line": 1,
            "service": "api",
        },
        {
            "ts": "2026-05-12T07:00:30",
            "level": "INFO",
            "logger": "x",
            "msg": "b",
            "file": "f.py",
            "line": 1,
            "service": "api",
        },
        {
            "ts": "2026-05-12T07:01:00",
            "level": "ERROR",
            "logger": "x",
            "msg": "c",
            "file": "g.py",
            "line": 2,
            "service": "worker",
        },
    ]
    p.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    a = JSONLAdapter(p)
    res = a.multi_track(
        filters=Filters(),
        tracks=["level", "service"],
        window_start=datetime(2026, 5, 12, 7, 0),
        window_end=datetime(2026, 5, 12, 8, 0),
    )
    lvl = {(c.bucket, c.value): c.count for c in res.tracks["level"]}
    assert lvl == {
        ("2026-05-12T07:00", "ERROR"): 1,
        ("2026-05-12T07:00", "INFO"): 1,
        ("2026-05-12T07:01", "ERROR"): 1,
    }
    svc = {(c.bucket, c.value): c.count for c in res.tracks["service"]}
    assert svc[("2026-05-12T07:00", "api")] == 2
    assert svc[("2026-05-12T07:01", "worker")] == 1


def test_csv_multi_track_in_memory(tmp_path):
    p = tmp_path / "logs.csv"
    p.write_text(
        "ts,level,logger,msg,file,line,context_json\n"
        '2026-05-12T07:00:00,ERROR,x,a,f.py,1,"{""service"":""api""}"\n'
        '2026-05-12T07:01:00,INFO,x,b,g.py,2,"{""service"":""worker""}"\n',
        encoding="utf-8",
    )
    a = CSVAdapter(p)
    res = a.multi_track(
        filters=Filters(),
        tracks=["level"],
        window_start=datetime(2026, 5, 12, 7, 0),
        window_end=datetime(2026, 5, 12, 8, 0),
    )
    cells = {(c.bucket, c.value): c.count for c in res.tracks["level"]}
    assert cells == {
        ("2026-05-12T07:00", "ERROR"): 1,
        ("2026-05-12T07:01", "INFO"): 1,
    }


def test_empty_result_when_window_has_no_records(tmp_path):
    a = _seed_sqlite(tmp_path / "m6.sqlite")
    res = a.multi_track(
        filters=Filters(),
        tracks=["level", "service", "file"],
        window_start=datetime(2030, 1, 1),
        window_end=datetime(2030, 1, 2),
    )
    assert res.tracks["level"] == []
    assert res.tracks["service"] == []
    assert res.tracks["file"] == []
