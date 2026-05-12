"""Tests for SQLHandler chain mode + canonical/hash helpers — Story 3.5."""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

import ulog
from ulog._chain import canonical_record_json, sha256_record


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


def _flush_all() -> None:
    for h in logging.getLogger().handlers:
        h.flush()


def _read_chain(url: str):
    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT chain_pos, record_hash, prev_hash, msg, immutable "
                "FROM logs ORDER BY chain_pos"
            )
        ).all()
    engine.dispose()
    return rows


# ---- setup() integrity validation ----------------------------------------


def test_setup_integrity_invalid_value_raises():
    """AC1 — setup(integrity='nope') is rejected with clear message."""
    with pytest.raises(ValueError, match="integrity"):
        ulog.setup(integrity="nope")


def test_setup_integrity_none_is_valid():
    """AC1 — integrity=None is the default and stays valid (no-chain)."""
    ulog.setup(integrity=None, handlers=["stream"])


# ---- canonical / hash helpers --------------------------------------------


def test_canonical_record_json_is_deterministic():
    """AC3 — same record dict produces same canonical bytes regardless
    of key insertion order."""
    a = {"b": 2, "a": 1, "c": 3}
    b = {"a": 1, "b": 2, "c": 3}
    assert canonical_record_json(a) == canonical_record_json(b)
    assert canonical_record_json(a) == b'{"a":1,"b":2,"c":3}'


def test_canonical_record_json_handles_datetime():
    """AC3 — datetime → ISO string; same dt → same bytes."""
    dt = datetime.datetime(2026, 5, 12, 12, 34, 56)
    payload = canonical_record_json({"ts": dt, "level": "INFO"})
    assert b'"ts":"2026-05-12T12:34:56"' in payload


def test_canonical_record_json_handles_bytes_as_hex():
    """AC3 — bytes → hex string (deterministic, JSON-safe)."""
    payload = canonical_record_json({"record_hash": b"\xab\xcd"})
    assert b'"record_hash":"abcd"' in payload


def test_canonical_record_json_raises_on_unknown_type():
    """AC3 — non-canonicalisable types fail fast (no silent str())."""
    with pytest.raises(TypeError, match="non-canonicalisable"):
        canonical_record_json({"oops": object()})


def test_sha256_record_matches_external_recomputation():
    """AC4 — hash output equals sha256(canonical + prev_hash) externally."""
    rec = {"a": 1, "b": "x"}
    prev = b"\x00" * 32
    expected = hashlib.sha256(b'{"a":1,"b":"x"}' + prev).digest()
    assert sha256_record(rec, prev) == expected
    assert len(sha256_record(rec, prev)) == 32


# ---- SQLHandler chain mode integration -----------------------------------


def test_sql_chain_mode_sets_wal_mode(tmp_path):
    """AC2 — WAL pragma is active after chain-mode setup."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "wal.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
    )
    ulog.get_logger().info("seed")
    _flush_all()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar_one()
    engine.dispose()
    assert mode.lower() == "wal", f"expected WAL, got {mode!r}"


def test_chain_emit_produces_linked_records(tmp_path):
    """AC5/AC6 — first record has zero prev_hash; subsequent prev_hash
    chains to the previous record_hash."""
    db = tmp_path / "chain.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
    )
    log = ulog.get_logger("svc")
    log.info("a")
    log.info("b")
    log.info("c")
    _flush_all()

    rows = _read_chain(url)
    assert len(rows) == 3
    chain_pos = [r[0] for r in rows]
    assert chain_pos == [1, 2, 3]
    assert bytes(rows[0][2]) == b"\x00" * 32, "first prev_hash must be zero"
    assert bytes(rows[1][2]) == bytes(rows[0][1]), "row 2 prev_hash != row 1 record_hash"
    assert bytes(rows[2][2]) == bytes(rows[1][1]), "row 3 prev_hash != row 2 record_hash"


def test_chain_concurrent_emit_serialised(tmp_path):
    """AC7 — 4 threads x 25 emits -> 100 monotonic chain_pos; chain
    links verify end-to-end (no torn writes / no cross-chains)."""
    db = tmp_path / "concur.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
    )
    log = ulog.get_logger()

    def emit_burst(thread_id: int) -> None:
        for i in range(25):
            log.info("t%d-%d", thread_id, i)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(emit_burst, range(4)))
    _flush_all()

    rows = _read_chain(url)
    assert [r[0] for r in rows] == list(range(1, 101))
    # End-to-end chain integrity walk.
    for i, row in enumerate(rows):
        if i == 0:
            assert bytes(row[2]) == b"\x00" * 32
        else:
            assert bytes(row[2]) == bytes(rows[i - 1][1]), f"chain broken at chain_pos={row[0]}"


def test_chain_emit_with_exc_and_context(tmp_path):
    """AC: chain works with exc payload + bound context. The row dict
    passed to chain_writer.append must include all fields."""
    db = tmp_path / "exc.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
    )
    ulog.bind(req_id="abc123")
    log = ulog.get_logger()
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("caught")
    _flush_all()

    rows = _read_chain(url)
    assert len(rows) == 1
    assert rows[0][0] == 1  # chain_pos
    assert bytes(rows[0][2]) == b"\x00" * 32  # first prev_hash


def test_non_chain_mode_unchanged(tmp_path):
    """AC8 — setup() without integrity= uses the buffered/batched
    v0.2 path; records persist with chain_pos=0 and NULL hashes."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "nochain.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    ulog.get_logger().info("plain")
    _flush_all()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT chain_pos, immutable, record_hash, prev_hash FROM logs WHERE msg='plain'")
        ).first()
    engine.dispose()
    assert row == (0, 0, None, None)
