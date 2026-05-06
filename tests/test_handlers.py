"""Tests for the v0.2 storage handlers (SQL, JSON Line, CSV)."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
from pathlib import Path

import pytest

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    """Clear bound state at SETUP and teardown.

    Setup-side clear prevents the outer pytest plugin's test_id bind
    (active under `--ulog-db`) from leaking into the SQL handler's
    `context` JSON column when these tests assert on its exact shape.
    """
    ulog.clear()
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            try:
                h.close()
            except Exception:
                pass
            logging.getLogger().removeHandler(h)
    ulog.clear()


# ---- JSONLineHandler -----------------------------------------------------


def test_jsonline_writes_one_object_per_record(tmp_path):
    path = tmp_path / "logs.jsonl"
    ulog.setup(handlers=["json"], json_path=str(path))
    log = ulog.get_logger("app")
    log.info("first")
    log.error("boom")
    # Force handler flush by removing
    for h in logging.getLogger().handlers:
        h.flush()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    e0, e1 = json.loads(lines[0]), json.loads(lines[1])
    assert e0["msg"] == "first" and e0["level"] == "INFO"
    assert e1["msg"] == "boom" and e1["level"] == "ERROR"


def test_jsonline_appends_to_existing_file(tmp_path):
    path = tmp_path / "logs.jsonl"
    ulog.setup(handlers=["json"], json_path=str(path))
    ulog.get_logger().info("one")
    # Re-setup → idempotent close + new handler. File should grow.
    ulog.setup(handlers=["json"], json_path=str(path))
    ulog.get_logger().info("two")
    for h in logging.getLogger().handlers:
        h.flush()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


# ---- CSVHandler ----------------------------------------------------------


def test_csv_writes_header_then_rows(tmp_path):
    path = tmp_path / "logs.csv"
    ulog.setup(handlers=["csv"], csv_path=str(path))
    ulog.get_logger("svc").info("rendered", extra={"frames": 600})
    ulog.get_logger("svc").error("boom")
    rows = list(csv.reader(path.open()))
    assert rows[0] == [
        "ts", "level", "logger", "msg", "file", "line", "context_json", "exc_json"
    ]
    assert len(rows) == 3  # header + 2 data
    assert rows[1][1] == "INFO"
    assert rows[1][2] == "svc"
    assert rows[1][3] == "rendered"
    # extra={'frames':600} lands in context_json
    ctx = json.loads(rows[1][6])
    assert ctx["frames"] == 600
    assert rows[2][1] == "ERROR"


def test_csv_serializes_exception(tmp_path):
    path = tmp_path / "logs.csv"
    ulog.setup(handlers=["csv"], csv_path=str(path))
    log = ulog.get_logger()
    try:
        raise ValueError("nope")
    except ValueError:
        log.exception("caught")
    rows = list(csv.reader(path.open()))
    exc = json.loads(rows[1][7])
    assert exc["type"] == "ValueError"
    assert exc["msg"] == "nope"


def test_csv_includes_bound_context(tmp_path):
    path = tmp_path / "logs.csv"
    ulog.setup(handlers=["csv"], csv_path=str(path))
    ulog.bind(rom="alter_ego", song=0)
    ulog.get_logger().info("rendering")
    rows = list(csv.reader(path.open()))
    ctx = json.loads(rows[1][6])
    assert ctx["rom"] == "alter_ego"
    assert ctx["song"] == 0


# ---- SQLHandler ----------------------------------------------------------


def test_sql_records_persist_to_sqlite(tmp_path):
    db = tmp_path / "logs.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    log = ulog.get_logger("svc")
    log.info("one")
    log.error("boom")
    # Force flush via close on handler
    for h in logging.getLogger().handlers:
        h.flush()

    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT level, logger, msg FROM logs ORDER BY id")
        ).all()
    assert rows == [("INFO", "svc", "one"), ("ERROR", "svc", "boom")]
    engine.dispose()


def test_sql_batch_flush_threshold(tmp_path):
    db = tmp_path / "logs.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=3)
    log = ulog.get_logger()
    # Emit 2 (below batch) → not yet persisted
    log.info("one")
    log.info("two")

    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows_before = conn.execute(text("SELECT COUNT(*) FROM logs")).scalar()
    assert rows_before == 0
    # 3rd emit triggers flush
    log.info("three")
    with engine.begin() as conn:
        rows_after = conn.execute(text("SELECT COUNT(*) FROM logs")).scalar()
    assert rows_after == 3
    engine.dispose()


def test_sql_persists_bound_context(tmp_path):
    db = tmp_path / "logs.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    ulog.bind(rom_sha="abc", engine="famitracker")
    ulog.get_logger().info("rendered")
    for h in logging.getLogger().handlers:
        h.flush()

    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        ctx_str = conn.execute(text("SELECT context FROM logs")).scalar()
    # SQLite JSON columns come back as strings on naive query
    ctx = json.loads(ctx_str) if isinstance(ctx_str, str) else ctx_str
    assert ctx == {"rom_sha": "abc", "engine": "famitracker"}
    engine.dispose()


def test_sql_persists_exception(tmp_path):
    db = tmp_path / "logs.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    log = ulog.get_logger()
    try:
        raise ValueError("nope")
    except ValueError:
        log.exception("caught")
    for h in logging.getLogger().handlers:
        h.flush()

    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        exc_str = conn.execute(text("SELECT exc FROM logs")).scalar()
    exc = json.loads(exc_str) if isinstance(exc_str, str) else exc_str
    assert exc["type"] == "ValueError"
    assert exc["msg"] == "nope"
    engine.dispose()


# ---- SQL handler concurrent bootstrap (Story 1.13) -----------------------


def test_sql_handler_no_race_under_concurrent_bootstrap(tmp_path):
    """Story 1.13 regression — when multiple processes bootstrap a SQL
    handler against the same shared DB simultaneously (real-world
    `pytest -n auto --ulog-db <shared>` scenario), the CREATE TABLE
    race must NOT produce 'Logging error' stderr noise. The loser of
    the race catches OperationalError('table already exists') and
    falls through to column-verify."""
    import subprocess
    import sys
    import textwrap

    db = tmp_path / "race.sqlite"

    # Each subprocess bootstraps a SQL handler against the SHARED db
    # and emits one record. With 4 concurrent procs, the CREATE TABLE
    # race fires nearly every time on a fresh DB.
    script = textwrap.dedent(
        f"""
        import logging, ulog
        ulog.setup(handlers=['sql'], sql_url='sqlite:///{db}', sql_batch_size=1)
        logging.getLogger().info('hello from worker')
        for h in logging.getLogger().handlers:
            h.flush()
        """
    )

    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        for _ in range(4)
    ]
    stderrs = []
    for p in procs:
        _out, err = p.communicate(timeout=15)
        assert p.returncode == 0, f"worker subprocess failed: {err.decode()}"
        stderrs.append(err.decode())

    combined = "\n".join(stderrs)
    assert "Logging error" not in combined, (
        f"CREATE TABLE race produced stderr noise:\n{combined}"
    )
    assert "OperationalError" not in combined, (
        f"OperationalError leaked to stderr:\n{combined}"
    )

    # All 4 records should have persisted (no record was lost to the race).
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM logs")).scalar()
    engine.dispose()
    assert n == 4, f"expected 4 records persisted, got {n}"


# ---- Multi-handler setup -------------------------------------------------


def test_multi_handler_emits_to_all_targets(tmp_path):
    db = tmp_path / "logs.sqlite"
    jsonl = tmp_path / "logs.jsonl"
    csv_path = tmp_path / "logs.csv"
    sink = io.StringIO()
    ulog.setup(
        handlers=["stream", "sql", "json", "csv"],
        stream=sink,
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
        json_path=str(jsonl),
        csv_path=str(csv_path),
        color="never",
    )
    ulog.get_logger("svc").info("hello")
    for h in logging.getLogger().handlers:
        h.flush()
    # Stream output
    assert "hello" in sink.getvalue()
    # JSON file
    assert jsonl.exists() and jsonl.stat().st_size > 0
    # CSV
    rows = list(csv.reader(csv_path.open()))
    assert rows[1][3] == "hello"
    # SQLite
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM logs")).scalar()
    assert n == 1
    engine.dispose()


def test_setup_rejects_unknown_handler_kind(tmp_path):
    with pytest.raises(ValueError, match="unknown handler kind"):
        ulog.setup(handlers=["bogus"])


def test_setup_json_without_path_raises(tmp_path):
    with pytest.raises(ValueError, match="json_path"):
        ulog.setup(handlers=["json"])


def test_setup_csv_without_path_raises(tmp_path):
    with pytest.raises(ValueError, match="csv_path"):
        ulog.setup(handlers=["csv"])
