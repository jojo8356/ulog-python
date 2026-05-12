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
    expected_new = {"chain_pos", "record_hash", "prev_hash", "immutable", "is_replay"}
    assert expected_new <= cols.keys(), f"missing columns: {expected_new - cols.keys()}"
    # `chain_pos`, `immutable` and `is_replay` are NOT NULL with default 0.
    assert cols["chain_pos"]["nullable"] is False
    assert cols["immutable"]["nullable"] is False
    assert cols["is_replay"]["nullable"] is False
    # `record_hash` / `prev_hash` are nullable BLOBs.
    assert cols["record_hash"]["nullable"] is True
    assert cols["prev_hash"]["nullable"] is True

    idx_names = {i["name"] for i in insp.get_indexes("logs")}
    assert "ix_logs_chain_pos" in idx_names
    assert "ix_logs_immutable" in idx_names
    assert "ix_logs_is_replay" in idx_names
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
            text("SELECT chain_pos, immutable, record_hash, prev_hash, is_replay FROM logs")
        ).first()
    assert row is not None
    assert row[0] == 0  # chain_pos
    assert row[1] == 0  # immutable
    assert row[2] is None  # record_hash
    assert row[3] is None  # prev_hash
    assert row[4] == 0  # is_replay (Story 4.2)
    engine.dispose()


def test_sql_v04_upgrade_path_raises_schema_error(tmp_path):
    """Story 3.3 — pre-existing v0.4 table (no chain columns) →
    SchemaError containing the LITERAL ALTER TABLE + CREATE INDEX SQL
    (deterministic, copy-paste) plus the Gap G1 discontinuity note."""
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
    for stmt in (
        "ALTER TABLE logs ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE logs ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE logs ADD COLUMN is_replay INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE logs ADD COLUMN prev_hash BLOB;",
        "ALTER TABLE logs ADD COLUMN record_hash BLOB;",
        "CREATE INDEX ix_logs_chain_pos ON logs(chain_pos);",
        "CREATE INDEX ix_logs_immutable ON logs(immutable);",
        "CREATE INDEX ix_logs_is_replay ON logs(is_replay);",
    ):
        assert stmt in msg, f"missing statement {stmt!r} in SchemaError: {msg!r}"
    assert "pre-chain" in msg.lower(), f"Gap G1 phrasing missing: {msg!r}"
    assert "fresh chain" in msg.lower(), f"Gap G1 phrasing missing: {msg!r}"
    handler.close()


# ---- SQLHandler — v0.5 immutable triggers (Story 3.2) --------------------


def _bootstrap_v05_db(tmp_path):
    """Helper — create a v0.5 SQLite DB with one emit so the schema +
    triggers are installed. Returns the engine."""
    from sqlalchemy import create_engine

    db = tmp_path / "logs.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    ulog.get_logger().info("seed")
    for h in logging.getLogger().handlers:
        h.flush()
    return create_engine(url, future=True)


def test_sql_v05_triggers_created_on_fresh_db(tmp_path):
    """Story 3.2 AC1 — fresh DB has both immutable-blocking triggers
    after schema bootstrap. Inspect sqlite_master directly."""
    from sqlalchemy import text

    engine = _bootstrap_v05_db(tmp_path)
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='logs'")
        ).all()
    names = {r[0] for r in rows}
    assert "trg_logs_block_update_immutable" in names
    assert "trg_logs_block_delete_immutable" in names
    bodies = {r[0]: r[1] for r in rows}
    assert "BEFORE UPDATE" in bodies["trg_logs_block_update_immutable"]
    assert "BEFORE DELETE" in bodies["trg_logs_block_delete_immutable"]
    assert "OLD.immutable = 1" in bodies["trg_logs_block_update_immutable"]
    assert "OLD.immutable = 1" in bodies["trg_logs_block_delete_immutable"]
    engine.dispose()


def test_sql_v05_trigger_blocks_update_on_immutable_row(tmp_path):
    """Story 3.2 AC3/AC7 — UPDATE on a row with immutable=1 is rolled
    back by the trigger; original msg is preserved."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError, OperationalError

    engine = _bootstrap_v05_db(tmp_path)
    # Insert one immutable=1 row via raw SQL (SQLHandler.emit always
    # sets immutable=0 until Story 3.5).
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO logs "
                "(ts, level, logger, msg, file, line, immutable, chain_pos) "
                "VALUES ('2026-05-12 00:00:00', 'INFO', 'test', 'sealed', "
                "'x.py', 1, 1, 0)"
            )
        )
        rid = conn.execute(text("SELECT id FROM logs WHERE msg='sealed'")).scalar_one()

    with pytest.raises((IntegrityError, OperationalError)) as excinfo, engine.begin() as conn:
        conn.execute(text(f"UPDATE logs SET msg='tampered' WHERE id={rid}"))
    assert "immutable row" in str(excinfo.value).lower(), str(excinfo.value)

    with engine.begin() as conn:
        msg = conn.execute(text(f"SELECT msg FROM logs WHERE id={rid}")).scalar_one()
    assert msg == "sealed", "UPDATE was not rolled back by the trigger"
    engine.dispose()


def test_sql_v05_trigger_blocks_delete_on_immutable_row(tmp_path):
    """Story 3.2 AC4/AC7 — DELETE on a row with immutable=1 is blocked;
    row remains in the table."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError, OperationalError

    engine = _bootstrap_v05_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO logs "
                "(ts, level, logger, msg, file, line, immutable, chain_pos) "
                "VALUES ('2026-05-12 00:00:00', 'INFO', 'test', 'sealed', "
                "'x.py', 1, 1, 0)"
            )
        )
        rid = conn.execute(text("SELECT id FROM logs WHERE msg='sealed'")).scalar_one()

    with pytest.raises((IntegrityError, OperationalError)) as excinfo, engine.begin() as conn:
        conn.execute(text(f"DELETE FROM logs WHERE id={rid}"))
    assert "immutable row" in str(excinfo.value).lower(), str(excinfo.value)

    with engine.begin() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM logs WHERE id={rid}")).scalar_one()
    assert count == 1, "DELETE was not rolled back by the trigger"
    engine.dispose()


def test_sql_v05_trigger_allows_update_on_rotable_row(tmp_path):
    """Story 3.2 AC5 — UPDATE on a row with immutable=0 succeeds.
    Story 3.9 (ulog purge) depends on this path staying open."""
    from sqlalchemy import text

    engine = _bootstrap_v05_db(tmp_path)
    # The seed record from _bootstrap_v05_db has immutable=0 by default.
    with engine.begin() as conn:
        rid = conn.execute(text("SELECT id FROM logs WHERE msg='seed'")).scalar_one()
        conn.execute(text(f"UPDATE logs SET msg='rotated' WHERE id={rid}"))

    with engine.begin() as conn:
        msg = conn.execute(text(f"SELECT msg FROM logs WHERE id={rid}")).scalar_one()
    assert msg == "rotated"
    engine.dispose()


def test_sql_v05_trigger_allows_delete_on_rotable_row(tmp_path):
    """Story 3.2 AC6 — DELETE on a row with immutable=0 succeeds."""
    from sqlalchemy import text

    engine = _bootstrap_v05_db(tmp_path)
    with engine.begin() as conn:
        rid = conn.execute(text("SELECT id FROM logs WHERE msg='seed'")).scalar_one()
        conn.execute(text(f"DELETE FROM logs WHERE id={rid}"))

    with engine.begin() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) FROM logs WHERE id={rid}")).scalar_one()
    assert count == 0
    engine.dispose()


def test_sql_v05_triggers_idempotent_on_double_bootstrap(tmp_path):
    """Story 3.2 AC8 — bootstrapping the schema twice against the same
    DB doesn't raise OperationalError('trigger already exists') —
    CREATE TRIGGER IF NOT EXISTS handles re-entry."""
    from ulog.handlers.sql import SQLHandler

    db = tmp_path / "logs.sqlite"
    url = f"sqlite:///{db}"
    h1 = SQLHandler(url=url, batch_size=1)
    h1._ensure_schema()  # fresh-create path: triggers installed
    h2 = SQLHandler(url=url, batch_size=1)
    h2._ensure_schema()  # existing-v0.5 path: triggers re-install via IF NOT EXISTS
    h1.close()
    h2.close()


# ---- SQLHandler — v0.5 upgrade message (Story 3.3) -----------------------


def _create_v04_table(url: str) -> None:
    """Pre-create the v0.4 `logs` shape (9 cols, no chain columns).
    Helper for Story 3.3 upgrade tests."""
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


def test_sql_v05_upgrade_message_resolved_after_manual_alter(tmp_path):
    """Story 3.3 AC4 — parse the SQL out of the SchemaError, run it
    manually, then v0.5 handler proceeds and emit lands with chain
    defaults (chain_pos=0, immutable=0, hashes NULL)."""
    from sqlalchemy import create_engine, text

    from ulog.handlers.sql import SchemaError, SQLHandler

    db = tmp_path / "upgrade.sqlite"
    url = f"sqlite:///{db}"
    _create_v04_table(url)

    # Capture the SchemaError + extract statements.
    h_pre = SQLHandler(url=url, batch_size=1)
    with pytest.raises(SchemaError) as excinfo:
        h_pre._ensure_schema()
    h_pre.close()
    msg = str(excinfo.value)
    stmts = [
        line.strip().rstrip(";")
        for line in msg.splitlines()
        if line.strip().startswith(("ALTER", "CREATE"))
    ]
    # Post-Story 4.2: 5 ALTERs (chain_pos, immutable, is_replay, prev_hash, record_hash)
    # + 3 CREATE INDEX (chain_pos, immutable, is_replay) = 8 statements.
    assert len(stmts) == 8, f"expected 8 upgrade statements, got {len(stmts)}: {stmts!r}"

    # Apply them manually.
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))
    engine.dispose()

    # Re-bootstrap; schema verification must now pass.
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    ulog.get_logger().info("post-upgrade")
    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT chain_pos, immutable, record_hash, prev_hash "
                "FROM logs WHERE msg='post-upgrade'"
            )
        ).first()
    assert row == (0, 0, None, None)
    engine.dispose()


def test_sql_v05_upgrade_partial_chain_columns(tmp_path):
    """Story 3.3 AC5 — pre-create v0.4 + add chain_pos manually
    (other 3 chain columns still missing). SchemaError lists only
    the 3 remaining ALTERs and only the indexes whose column is in
    chain_missing (so ix_logs_chain_pos must NOT appear since
    chain_pos is already present)."""
    from sqlalchemy import create_engine, text

    from ulog.handlers.sql import SchemaError, SQLHandler

    db = tmp_path / "partial.sqlite"
    url = f"sqlite:///{db}"
    _create_v04_table(url)
    # User has applied ONLY the chain_pos ALTER, not the others.
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE logs ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0"))
    engine.dispose()

    handler = SQLHandler(url=url, batch_size=1)
    with pytest.raises(SchemaError) as excinfo:
        handler._ensure_schema()
    handler.close()
    msg = str(excinfo.value)
    # The 4 remaining ALTERs must appear (post-Story 4.2: is_replay added).
    for stmt in (
        "ALTER TABLE logs ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE logs ADD COLUMN is_replay INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE logs ADD COLUMN prev_hash BLOB;",
        "ALTER TABLE logs ADD COLUMN record_hash BLOB;",
    ):
        assert stmt in msg, f"missing ALTER {stmt!r}: {msg!r}"
    # The already-applied chain_pos ALTER must NOT reappear.
    assert "ADD COLUMN chain_pos" not in msg, (
        f"already-applied chain_pos ALTER leaked into message: {msg!r}"
    )
    # ix_logs_chain_pos: column already present → pragmatic
    # simplification (Task 2.4) omits it from the message.
    assert "ix_logs_chain_pos" not in msg, (
        f"index for already-present chain_pos column leaked: {msg!r}"
    )
    # ix_logs_immutable: its column is in chain_missing → present.
    assert "CREATE INDEX ix_logs_immutable ON logs(immutable);" in msg


def test_sql_v05_non_chain_missing_column_uses_legacy_message(tmp_path):
    """Story 3.3 AC6 — when the missing set contains NO chain columns
    (a pre-v0.2 schema, or any unrelated drift), the legacy v0.2
    `"v0.2 doesn't ship migrations"` phrasing fires instead of the
    literal-SQL v0.5 path. Protects backward-compat."""
    from sqlalchemy import (
        BLOB,
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

    db = tmp_path / "non_chain.sqlite"
    url = f"sqlite:///{db}"
    # Build a v0.5-ish table MISSING `exc` (a non-chain v0.2 column).
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
        # exc omitted on purpose
        Column("context", JSON, nullable=True),
        Column("chain_pos", Integer, nullable=False, server_default="0"),
        Column("record_hash", BLOB, nullable=True),
        Column("prev_hash", BLOB, nullable=True),
        Column("immutable", Integer, nullable=False, server_default="0"),
        Column("is_replay", Integer, nullable=False, server_default="0"),
    )
    md.create_all(engine)
    engine.dispose()

    handler = SQLHandler(url=url, batch_size=1)
    with pytest.raises(SchemaError) as excinfo:
        handler._ensure_schema()
    handler.close()
    msg = str(excinfo.value)
    # Legacy phrasing fires; literal-SQL phrasing must NOT.
    assert "v0.2 doesn't ship migrations" in msg, f"legacy phrasing absent: {msg!r}"
    assert "ALTER TABLE" not in msg, f"literal-SQL path leaked into non-chain case: {msg!r}"
    assert "'exc'" in msg or "exc" in msg
