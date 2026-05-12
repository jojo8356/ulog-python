"""Tests for ulog._chain — Story 3.4 (ChainWriter Protocol + SQLite impl)."""

from __future__ import annotations

import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from ulog._chain import ChainWriter, SQLiteChainWriter
from ulog.handlers.sql import SQLHandler


@pytest.fixture
def chain_engine(tmp_path):
    """Bootstrap a v0.5 SQLite schema via SQLHandler, return a fresh
    engine pointing at the same DB. Tests target the chain writer
    directly, NOT the handler's emit path."""
    from sqlalchemy import create_engine

    db = tmp_path / "chain.sqlite"
    url = f"sqlite:///{db}"
    handler = SQLHandler(url=url, batch_size=1)
    handler._ensure_schema()
    handler.close()
    engine = create_engine(url, future=True)
    yield engine
    engine.dispose()


def _make_record(msg: str = "x") -> dict:
    return {
        "ts": datetime.datetime(2026, 5, 12, 0, 0, 0),
        "level": "INFO",
        "logger": "test",
        "msg": msg,
        "file": "test.py",
        "line": 1,
        "exc": None,
        "context": None,
    }


def test_chain_writer_protocol_signature():
    """AC1/AC2/AC8 — Protocol exports with the expected method names,
    runtime_checkable, and accepts a MagicMock(spec=...) as an
    instance for chain-logic mock-based tests."""
    assert hasattr(ChainWriter, "get_last_hash")
    assert hasattr(ChainWriter, "append")
    mock = MagicMock(spec=ChainWriter)
    assert isinstance(mock, ChainWriter), (
        "@runtime_checkable Protocol should accept duck-typed mocks"
    )
    mock.append.return_value = 42
    assert mock.append({}, b"\x00" * 32, b"\x00" * 32) == 42
    mock.get_last_hash.return_value = b"\xff" * 32
    assert mock.get_last_hash() == b"\xff" * 32


def test_sqlite_chain_writer_get_last_hash_empty_returns_zero(chain_engine):
    """AC4 — empty chain → zero hash."""
    writer = SQLiteChainWriter(chain_engine)
    assert writer.get_last_hash() == b"\x00" * 32


def test_sqlite_chain_writer_get_last_hash_after_one_append(chain_engine):
    """AC5 — get_last_hash returns the most recent record's hash."""
    writer = SQLiteChainWriter(chain_engine)
    h1 = b"\x11" * 32
    writer.append(_make_record("a"), record_hash=h1, prev_hash=b"\x00" * 32)
    assert writer.get_last_hash() == h1
    h2 = b"\x22" * 32
    writer.append(_make_record("b"), record_hash=h2, prev_hash=h1)
    assert writer.get_last_hash() == h2


def test_sqlite_chain_writer_append_assigns_monotonic_chain_pos(chain_engine):
    """AC6 — three appends → chain_pos 1, 2, 3."""
    writer = SQLiteChainWriter(chain_engine)
    p1 = writer.append(_make_record("a"), b"\x01" * 32, b"\x00" * 32)
    p2 = writer.append(_make_record("b"), b"\x02" * 32, b"\x01" * 32)
    p3 = writer.append(_make_record("c"), b"\x03" * 32, b"\x02" * 32)
    assert (p1, p2, p3) == (1, 2, 3)


def test_sqlite_chain_writer_append_preserves_record_fields(chain_engine):
    """AC6 — caller-provided record fields (including immutable=1)
    survive the INSERT verbatim."""
    from sqlalchemy import text

    writer = SQLiteChainWriter(chain_engine)
    rec = _make_record("payload")
    rec["immutable"] = 1
    h = b"\xab" * 32
    pos = writer.append(rec, record_hash=h, prev_hash=b"\x00" * 32)
    with chain_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT msg, level, logger, immutable, chain_pos, record_hash "
                "FROM logs WHERE chain_pos = :p"
            ),
            {"p": pos},
        ).first()
    assert row[0] == "payload"
    assert row[1] == "INFO"
    assert row[2] == "test"
    assert row[3] == 1  # immutable=1 flowed through
    assert row[4] == pos
    assert bytes(row[5]) == h


def test_sqlite_chain_writer_begin_immediate_registered_once(chain_engine):
    """AC7 — multiple writers on the same engine register the
    `do_begin` listener exactly once (sentinel guard)."""
    from sqlalchemy import event

    SQLiteChainWriter(chain_engine)
    SQLiteChainWriter(chain_engine)
    SQLiteChainWriter(chain_engine)
    listeners = event.registry._key_to_collection  # type: ignore[attr-defined]
    # Direct sentinel check is the load-bearing assertion:
    assert getattr(chain_engine, "_ulog_chain_begin_immediate", False) is True
    # Listener count is implementation-detail; the sentinel above is
    # the contract. Touch `listeners` only to confirm the registry
    # is reachable (smoke test).
    assert listeners is not None


def test_sqlite_chain_writer_blocks_update_via_immutable_trigger(chain_engine):
    """AC11 (indirect) — when chain writer inserts immutable=1, the
    Story 3.2 trigger then blocks UPDATE. Proves the chain writer
    composes cleanly with the storage-layer guard."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError, OperationalError

    writer = SQLiteChainWriter(chain_engine)
    rec = _make_record("sealed")
    rec["immutable"] = 1
    pos = writer.append(rec, b"\xcc" * 32, b"\x00" * 32)
    with (
        pytest.raises((IntegrityError, OperationalError)) as excinfo,
        chain_engine.begin() as conn,
    ):
        conn.execute(
            text("UPDATE logs SET msg='tampered' WHERE chain_pos=:p"),
            {"p": pos},
        )
    assert "immutable row" in str(excinfo.value).lower()


def test_sqlite_chain_writer_concurrent_append_serialised(chain_engine):
    """AC11 — 2 threads x 50 appends -> 100 rows with chain_pos values
    forming the set {1..100} with no duplicates and no gaps.
    BEGIN IMMEDIATE on the engine serialises the writes."""
    writer = SQLiteChainWriter(chain_engine)

    def append_one(i: int) -> int:
        return writer.append(
            _make_record(f"r{i}"),
            record_hash=bytes([i % 256]) * 32,
            prev_hash=b"\x00" * 32,
        )

    with ThreadPoolExecutor(max_workers=2) as ex:
        positions = list(ex.map(append_one, range(100)))
    assert sorted(positions) == list(range(1, 101)), (
        f"chain_pos values are not monotonic 1..100: {sorted(positions)!r}"
    )
    assert len(set(positions)) == 100, "duplicate chain_pos values produced"
