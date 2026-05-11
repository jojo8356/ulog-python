"""Tests for the v0.2 storage handlers (SQL, JSON Line, CSV)."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import logging

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
            with contextlib.suppress(Exception):
                h.close()
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
    assert e0["msg"] == "first"
    assert e0["level"] == "INFO"
    assert e1["msg"] == "boom"
    assert e1["level"] == "ERROR"


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
    assert rows[0] == ["ts", "level", "logger", "msg", "file", "line", "context_json", "exc_json"]
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
        rows = conn.execute(text("SELECT level, logger, msg FROM logs ORDER BY id")).all()
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
    assert "Logging error" not in combined, f"CREATE TABLE race produced stderr noise:\n{combined}"
    assert "OperationalError" not in combined, f"OperationalError leaked to stderr:\n{combined}"

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
    assert jsonl.exists()
    assert jsonl.stat().st_size > 0
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


# ---- SQL handler v0.5 schema extension (Story 3.1) ----------------------


def test_sql_v05_schema_has_chain_and_immutable_columns(tmp_path):
    """Story 3.1 AC1/AC2/AC3 — fresh DB carries the 4 new columns +
    2 new indexes with correct types/defaults."""
    db = tmp_path / "logs.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    # Force schema creation by emitting one record.
    ulog.get_logger().info("seed")
    for h in logging.getLogger().handlers:
        h.flush()

    from sqlalchemy import create_engine, inspect

    engine = create_engine(url, future=True)
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("logs")}
    expected_new = {"chain_pos", "record_hash", "prev_hash", "immutable"}
    assert expected_new <= cols.keys(), f"missing columns: {expected_new - cols.keys()}"
    # `chain_pos` and `immutable` are NOT NULL with default 0.
    assert cols["chain_pos"]["nullable"] is False
    assert cols["immutable"]["nullable"] is False
    # `record_hash` / `prev_hash` are nullable BLOBs.
    assert cols["record_hash"]["nullable"] is True
    assert cols["prev_hash"]["nullable"] is True

    idx_names = {i["name"] for i in insp.get_indexes("logs")}
    assert "ix_logs_chain_pos" in idx_names
    assert "ix_logs_immutable" in idx_names
    engine.dispose()


def test_sql_v05_default_values(tmp_path):
    """Story 3.1 AC5 — records emitted without chain logic persist with
    chain_pos=0, immutable=0, record_hash=NULL, prev_hash=NULL."""
    db = tmp_path / "logs.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    ulog.get_logger().info("one")
    for h in logging.getLogger().handlers:
        h.flush()

    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT chain_pos, immutable, record_hash, prev_hash FROM logs")
        ).first()
    assert row is not None
    assert row[0] == 0  # chain_pos
    assert row[1] == 0  # immutable
    assert row[2] is None  # record_hash
    assert row[3] is None  # prev_hash
    engine.dispose()


def test_sql_v04_upgrade_path_raises_schema_error(tmp_path):
    """Story 3.1 AC4 — pre-existing v0.4 table (no chain columns) →
    SchemaError listing all 4 missing columns. Story 3.3 will replace
    the diff-set wording with a literal ALTER TABLE hint."""
    from sqlalchemy import (
        JSON,
        Column,
        DateTime,
        Integer,
        MetaData,
        String,
        Table,
        Text,
        create_engine,
    )

    from ulog.handlers.sql import SchemaError, SQLHandler

    db = tmp_path / "v04.sqlite"
    url = f"sqlite:///{db}"
    # Pre-create the v0.4 shape (9 cols, no chain/immutable).
    engine = create_engine(url, future=True)
    md = MetaData()
    Table(
        "logs",
        md,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("ts", DateTime(timezone=False), nullable=False),
        Column("level", String(10), nullable=False),
        Column("logger", String(255), nullable=False),
        Column("msg", Text, nullable=False),
        Column("file", String(255), nullable=False),
        Column("line", Integer, nullable=False),
        Column("exc", JSON, nullable=True),
        Column("context", JSON, nullable=True),
    )
    md.create_all(engine)
    engine.dispose()

    # Now bootstrap the v0.5 handler against it. SchemaError fires
    # at schema verification time, NOT inside emit's swallow path.
    handler = SQLHandler(url=url, batch_size=1)
    with pytest.raises(SchemaError) as excinfo:
        handler._ensure_schema()
    msg = str(excinfo.value)
    for col in ("chain_pos", "record_hash", "prev_hash", "immutable"):
        assert col in msg, f"missing column {col!r} not surfaced in SchemaError: {msg!r}"
    handler.close()
