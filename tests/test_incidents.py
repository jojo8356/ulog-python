"""Tests for Epic 5: resolve / reopen / state walk / edge cases.

Covers Stories 5.1 (resolve + FK), 5.2 (reopen + multi-resolve OK),
5.3 (state walk), 5.6 (edge cases per PRD-v0.5 §2.3).
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

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


def _setup_chain(tmp_path: Path) -> Path:
    db = tmp_path / "i.sqlite"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
    )
    return db


def _all_records(db: Path) -> list[dict]:
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, chain_pos, level, msg, ts, hex(record_hash) AS hh, context "
                "FROM logs ORDER BY chain_pos ASC"
            )
        ).all()
    engine.dispose()
    import json as _j

    out = []
    for r in rows:
        ctx = _j.loads(r.context) if r.context else {}
        out.append(
            {
                "id": r.id,
                "chain_pos": r.chain_pos,
                "level": r.level,
                "msg": r.msg,
                "ts": r.ts,
                "record_hash": bytes.fromhex(r.hh),
                "context": ctx,
            }
        )
    return out


# ---- 5.1 resolve ---------------------------------------------------------


def test_resolve_emits_resolved_record_with_resolves_field(tmp_path):
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("boom")
    rows = _all_records(db)
    target_hash = rows[0]["record_hash"].hex()
    ulog.resolve(target_hash, by="Johan", note="rolled back deploy")

    rows2 = _all_records(db)
    assert len(rows2) == 2
    resolved = rows2[1]
    assert resolved["msg"] == "RESOLVED"
    assert resolved["level"] == "INFO"
    assert resolved["context"]["resolves"] == target_hash
    assert resolved["context"]["by"] == "Johan"
    assert resolved["context"]["note"] == "rolled back deploy"
    assert resolved["context"]["incident_action"] == "resolve"


def test_resolve_accepts_hex_prefix(tmp_path):
    """4-char hex prefix is enough — same convention as `ulog verify`."""
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("boom")
    rows = _all_records(db)
    prefix = rows[0]["record_hash"].hex()[:8]
    ulog.resolve(prefix, by="x")
    rows2 = _all_records(db)
    assert rows2[1]["context"]["resolves"] == rows[0]["record_hash"].hex()


def test_resolve_unknown_hash_raises_lookuperror(tmp_path):
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("boom")
    with pytest.raises(LookupError):
        ulog.resolve("00000000deadbeef", by="x")
    # No new record emitted.
    rows = _all_records(db)
    assert len(rows) == 1


def test_resolve_empty_hash_raises_lookuperror(tmp_path):
    _setup_chain(tmp_path)
    with pytest.raises(LookupError):
        ulog.resolve("", by="x")


def test_resolve_too_short_prefix_raises(tmp_path):
    _setup_chain(tmp_path)
    with pytest.raises(LookupError):
        ulog.resolve("abc", by="x")


def test_resolve_without_sql_handler_raises_runtimeerror(tmp_path):
    """Resolve only works after `setup(handlers=['sql'], integrity=...)`."""
    ulog.setup()  # stream-only
    with pytest.raises(RuntimeError, match="SQL handler"):
        ulog.resolve("abcd1234", by="x")


# ---- 5.2 reopen ----------------------------------------------------------


def test_reopen_emits_reopened_record(tmp_path):
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("flaky test")
    rows = _all_records(db)
    target = rows[0]["record_hash"].hex()
    ulog.resolve(target, by="Johan")
    ulog.reopen(target, reason="recurrence at 2026-05-04")
    rows2 = _all_records(db)
    assert rows2[-1]["msg"] == "REOPENED"
    assert rows2[-1]["context"]["resolves"] == target
    assert rows2[-1]["context"]["reason"] == "recurrence at 2026-05-04"


# ---- 5.3 state walk ------------------------------------------------------


def test_compute_states_open_when_only_error(tmp_path):
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("oops")
    rows = _all_records(db)
    states = ulog.compute_states(rows)
    assert len(states) == 1
    st = next(iter(states.values()))
    assert st.state == "open"


def test_compute_states_closed_after_resolve(tmp_path):
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("oops")
    rows = _all_records(db)
    ulog.resolve(rows[0]["record_hash"].hex(), by="Johan")
    rows2 = _all_records(db)
    states = ulog.compute_states(rows2)
    st = states[rows[0]["record_hash"].hex()]
    assert st.state == "closed"
    assert st.last_action["msg"] == "RESOLVED"


def test_compute_states_latest_wins_resolve_reopen_resolve(tmp_path):
    """resolve → reopen → resolve → state = 'closed'."""
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("oops")
    rows = _all_records(db)
    h = rows[0]["record_hash"].hex()
    ulog.resolve(h, by="x")
    ulog.reopen(h)
    ulog.resolve(h, by="x")
    states = ulog.compute_states(_all_records(db))
    assert states[h].state == "closed"


def test_compute_states_reopened_when_latest_is_reopen(tmp_path):
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("oops")
    rows = _all_records(db)
    h = rows[0]["record_hash"].hex()
    ulog.resolve(h, by="x")
    ulog.reopen(h)
    states = ulog.compute_states(_all_records(db))
    assert states[h].state == "reopened"


# ---- 5.6 PRD-v0.5 §2.3 edge cases ----------------------------------------


def test_resolve_unknown_raises_no_record_emitted(tmp_path):
    """Edge case: `resolve(unknown_hash)` → LookupError, chain untouched."""
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("boom")
    rows_before = _all_records(db)
    with pytest.raises(LookupError):
        ulog.resolve("00000000abcdef00", by="x")
    rows_after = _all_records(db)
    assert len(rows_before) == len(rows_after)


def test_resolve_twice_emits_two_records(tmp_path):
    """Edge case: re-resolving an already-resolved incident IS allowed —
    chain shows the sequence and the latest wins."""
    db = _setup_chain(tmp_path)
    ulog.get_logger().error("oops")
    rows = _all_records(db)
    h = rows[0]["record_hash"].hex()
    ulog.resolve(h, by="x", note="first try")
    ulog.resolve(h, by="y", note="second try")
    rows2 = _all_records(db)
    resolved_records = [r for r in rows2 if r["msg"] == "RESOLVED"]
    assert len(resolved_records) == 2
    # Latest wins.
    states = ulog.compute_states(rows2)
    assert states[h].state == "closed"
    assert states[h].last_action["context"]["by"] == "y"
