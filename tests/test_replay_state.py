"""Tests for `_REPLAY_ACTIVE` contextvar + `is_replaying()` + the
`is_replay` schema column — Story 4.2."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog
from ulog._chain import canonical_record_json


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


def _seed_chain(tmp_path: Path, n: int = 3) -> Path:
    db = tmp_path / "replay.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=url, sql_batch_size=1)
    for i in range(n):
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


# ---- contextvar plumbing -------------------------------------------------


def test_is_replaying_false_outside_context():
    assert ulog.is_replaying() is False


def test_is_replaying_true_inside_replay_callback(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    seen = []
    ulog.replay(db, on=lambda r: seen.append(ulog.is_replaying()))
    assert seen == [True]


def test_is_replaying_returns_false_after_replay_completes(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    ulog.replay(db, on=lambda r: None)
    assert ulog.is_replaying() is False


def test_nested_replays_preserve_outer_state(tmp_path):
    """Outer replay sets True; inner replay also sets True + resets;
    outer should STILL see True after inner returns."""
    db = _seed_chain(tmp_path, n=2)
    nested_observations: list[bool] = []

    def outer_cb(r):
        # Inside outer replay: should be True.
        nested_observations.append(ulog.is_replaying())

        def inner_cb(_r):
            nested_observations.append(ulog.is_replaying())

        ulog.replay(db, on=inner_cb)
        # After inner returns: outer's True must persist.
        nested_observations.append(ulog.is_replaying())

    ulog.replay(db, where="chain_pos = 1", on=outer_cb)
    assert all(nested_observations), nested_observations
    # And outside everything: False.
    assert ulog.is_replaying() is False


def test_replay_raised_exception_resets_contextvar(tmp_path):
    """If the callback raises, the contextvar must still reset."""
    db = _seed_chain(tmp_path, n=1)

    def boom(_r):
        raise RuntimeError("callback bomb")

    with pytest.raises(RuntimeError, match="callback bomb"):
        ulog.replay(db, on=boom)
    assert ulog.is_replaying() is False


# ---- is_replay column stamping ------------------------------------------


def test_record_emitted_outside_replay_marked_is_replay_0(tmp_path):
    from sqlalchemy import create_engine, text

    db = tmp_path / "plain.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    ulog.get_logger().info("regular")
    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        flag = conn.execute(text("SELECT is_replay FROM logs WHERE msg='regular'")).scalar_one()
    engine.dispose()
    assert flag == 0


def test_record_emitted_inside_replay_marked_is_replay_1(tmp_path):
    """Outer replay's callback emits a NEW record; that new record
    must land with is_replay=1."""
    from sqlalchemy import create_engine, text

    db = _seed_chain(tmp_path, n=1)

    # Re-setup an emit-capable handler on the same DB.
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)

    def cb(_r):
        ulog.get_logger().info("emitted-during-replay")

    ulog.replay(db, on=cb)
    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        flag = conn.execute(
            text("SELECT is_replay FROM logs WHERE msg='emitted-during-replay'")
        ).scalar_one()
    engine.dispose()
    assert flag == 1


def test_record_inside_replay_chain_mode_persists_is_replay_1(tmp_path):
    """Same as above, but with chain mode active — the record_hash
    must also include is_replay=1 in its canonical form."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "chain.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=url, sql_batch_size=1)
    ulog.get_logger().info("seed")
    for h in logging.getLogger().handlers:
        h.flush()

    def cb(_r):
        ulog.get_logger().info("during-replay")

    ulog.replay(db, on=cb)
    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT msg, is_replay, chain_pos FROM logs ORDER BY chain_pos")
        ).all()
    engine.dispose()
    assert rows == [("seed", 0, 1), ("during-replay", 1, 2)]


# ---- chain hash includes is_replay --------------------------------------


def test_chain_hash_canonical_includes_is_replay():
    """canonical_record_json must include `is_replay` in the sorted
    key set so that tampering with the flag invalidates the chain."""
    rec = {
        "ts": "2026-05-12T00:00:00",
        "level": "INFO",
        "logger": "t",
        "msg": "x",
        "file": "f.py",
        "line": 1,
        "exc": None,
        "context": None,
        "immutable": 0,
        "is_replay": 1,
    }
    payload = canonical_record_json(rec)
    assert b'"is_replay":1' in payload


# ---- upgrade message regression (Story 3.3) ------------------------------


def test_v04_upgrade_message_now_includes_is_replay(tmp_path):
    """The v0.4 → v0.5 SchemaError must now also list is_replay's
    ALTER + CREATE INDEX (Story 4.2 extends Story 3.3's literal-SQL
    block via the _CHAIN_COLUMN_ALTER_DDL registry)."""
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

    h = SQLHandler(url=url, batch_size=1)
    with pytest.raises(SchemaError) as excinfo:
        h._ensure_schema()
    h.close()
    msg = str(excinfo.value)
    assert "ALTER TABLE logs ADD COLUMN is_replay INTEGER NOT NULL DEFAULT 0;" in msg
    assert "CREATE INDEX ix_logs_is_replay ON logs(is_replay);" in msg
