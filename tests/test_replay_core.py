"""Tests for `ulog.replay` — Story 4.1 (core + MappingProxyType)."""

from __future__ import annotations

import contextlib
import datetime
import logging
from pathlib import Path
from types import MappingProxyType

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


def _seed_chain(tmp_path: Path, n: int = 5) -> Path:
    """Emit `n` chain-mode records of varying level/logger/msg."""
    db = tmp_path / "replay.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=url, sql_batch_size=1)
    levels = ["INFO", "WARNING", "ERROR", "INFO", "ERROR"]
    for i in range(n):
        log = ulog.get_logger(f"svc.{i % 2}")
        level = levels[i % len(levels)]
        getattr(log, level.lower())("rec %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


# ---- iteration + ordering ------------------------------------------------


def test_replay_iterates_all_records_in_chain_order(tmp_path):
    db = _seed_chain(tmp_path, n=5)
    seen = []
    n = ulog.replay(db, on=lambda r: seen.append(r["chain_pos"]))
    assert n == 5
    assert seen == [1, 2, 3, 4, 5]


def test_replay_order_ts_works(tmp_path):
    db = _seed_chain(tmp_path, n=3)
    seen = []
    n = ulog.replay(db, on=lambda r: seen.append(r["chain_pos"]), order="ts")
    assert n == 3
    # ts order on chain mode = same as chain order for sequential emits.
    assert seen == [1, 2, 3]


def test_replay_order_invalid_raises(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    with pytest.raises(ValueError, match="unknown order"):
        ulog.replay(db, on=lambda r: None, order="random")


def test_replay_returns_count_of_records_replayed(tmp_path):
    db = _seed_chain(tmp_path, n=5)
    count = ulog.replay(db, on=lambda r: None)
    assert count == 5


def test_replay_on_empty_db_returns_zero(tmp_path):
    from sqlalchemy import create_engine, text

    # Build a v0.5 schema without emitting any record.
    db = tmp_path / "empty.sqlite"
    from ulog.handlers.sql import SQLHandler

    h = SQLHandler(url=f"sqlite:///{db}", batch_size=1, chain_mode=True)
    h._ensure_schema()
    h.close()
    # Sanity check — no rows.
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM logs")).scalar_one() == 0
    engine.dispose()

    count = ulog.replay(db, on=lambda r: None)
    assert count == 0


# ---- filter dispatch -----------------------------------------------------


def test_replay_with_sql_where_filters_correctly(tmp_path):
    db = _seed_chain(tmp_path, n=5)
    msgs = []
    n = ulog.replay(db, where="level = 'ERROR'", on=lambda r: msgs.append(r["msg"]))
    # Levels seeded: INFO, WARNING, ERROR, INFO, ERROR → 2 ERRORs.
    assert n == 2
    assert all("rec" in m for m in msgs)


def test_replay_with_where_fn_filters_correctly(tmp_path):
    db = _seed_chain(tmp_path, n=5)
    seen = []
    n = ulog.replay(
        db,
        where_fn=lambda r: r["logger"] == "svc.1",
        on=lambda r: seen.append(r["chain_pos"]),
    )
    # svc.1 is index 1 and 3 in the seed.
    assert n == 2
    assert seen == [2, 4]


def test_replay_passes_both_where_and_where_fn_raises(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    with pytest.raises(ValueError, match="at most one"):
        ulog.replay(
            db,
            where="level='ERROR'",
            where_fn=lambda r: True,
            on=lambda r: None,
        )


# ---- frozen view ---------------------------------------------------------


def test_replay_callback_receives_mappingproxytype(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    captured = []
    ulog.replay(db, on=lambda r: captured.append(r))
    assert len(captured) == 1
    assert isinstance(captured[0], MappingProxyType)


def test_replay_callback_mutation_raises_typeerror(tmp_path):
    db = _seed_chain(tmp_path, n=1)

    def cb(record):
        record["msg"] = "tampered"  # ← should raise

    with pytest.raises(TypeError, match="mappingproxy"):
        ulog.replay(db, on=cb)


def test_replay_record_keys_complete(tmp_path):
    """The frozen-view record exposes the full schema."""
    db = _seed_chain(tmp_path, n=1)
    captured = []
    ulog.replay(db, on=lambda r: captured.append(dict(r)))
    record = captured[0]
    expected_keys = {
        "id",
        "chain_pos",
        "ts",
        "level",
        "logger",
        "msg",
        "file",
        "line",
        "exc",
        "context",
        "immutable",
        "record_hash",
        "prev_hash",
    }
    assert set(record.keys()) == expected_keys
    # ts must be a datetime (round-trip from SQLite text).
    assert isinstance(record["ts"], datetime.datetime)
    # record_hash + prev_hash are bytes.
    assert isinstance(record["record_hash"], bytes)
    assert isinstance(record["prev_hash"], bytes)


# ---- path resolution -----------------------------------------------------


def test_replay_db_path_as_pathlib_and_str_work(tmp_path):
    db = _seed_chain(tmp_path, n=2)

    n_str = ulog.replay(str(db), on=lambda r: None)
    n_path = ulog.replay(db, on=lambda r: None)
    n_url = ulog.replay(f"sqlite:///{db}", on=lambda r: None)
    assert n_str == n_path == n_url == 2


def test_replay_db_path_nonexistent_raises_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError, match="DB not found"):
        ulog.replay(tmp_path / "missing.sqlite", on=lambda r: None)
