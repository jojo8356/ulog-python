"""Tests for PRD-v0.10 — fleet probes."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import ulog
from ulog.fleet import probe


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


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    return db


def _fetch_probe_records(db: Path) -> list[dict]:
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT msg, context FROM logs WHERE logger='ulog.fleet'")
        ).all()
    engine.dispose()
    return [{"msg": r[0], "context": json.loads(r[1]) if r[1] else {}} for r in rows]


def test_probe_emits_record_on_success(tmp_path):
    db = _setup_db(tmp_path)

    @probe(target="https://api.example.com/health")
    def check_api():
        return True

    check_api()
    for h in logging.getLogger().handlers:
        h.flush()
    records = _fetch_probe_records(db)
    assert len(records) == 1
    ctx = records[0]["context"]
    assert ctx["target"] == "https://api.example.com/health"
    assert ctx["fleet"] == "1"
    assert ctx["probe_status"] == "ok"
    assert "latency_ms" in ctx


def test_probe_emits_record_on_failure(tmp_path):
    db = _setup_db(tmp_path)

    @probe(target="https://broken")
    def check_broken():
        raise ConnectionError("nope")

    with pytest.raises(ConnectionError):
        check_broken()
    for h in logging.getLogger().handlers:
        h.flush()
    records = _fetch_probe_records(db)
    assert len(records) == 1
    assert records[0]["context"]["probe_status"] == "fail"


def test_probe_parents_propagated(tmp_path):
    db = _setup_db(tmp_path)

    @probe(target="payments", parents=["auth", "db"])
    def check_payments():
        return True

    check_payments()
    for h in logging.getLogger().handlers:
        h.flush()
    records = _fetch_probe_records(db)
    assert records[0]["context"]["parents"] == ["auth", "db"]


def test_probe_metadata_on_function(tmp_path):
    """Attributes for the optional `ulog fleet run` CLI to discover."""

    @probe(target="x", parents=["y"])
    def check_x():
        pass

    assert check_x._ulog_fleet_target == "x"
    assert check_x._ulog_fleet_parents == ["y"]
