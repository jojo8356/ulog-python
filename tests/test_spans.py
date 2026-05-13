"""Tests for PRD-v0.7 — span-based execution timeline."""

from __future__ import annotations

import contextlib
import json
import logging
import time
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


def _setup(tmp_path: Path) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    return db


def _span_records(db: Path) -> list[dict]:
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT msg, context FROM logs WHERE logger='ulog.span' ORDER BY id")
        ).all()
    engine.dispose()
    return [{"msg": r[0], "context": json.loads(r[1])} for r in rows]


def test_single_span_emits_record(tmp_path):
    db = _setup(tmp_path)
    with ulog.span("setup_db"):
        time.sleep(0.005)
    for h in logging.getLogger().handlers:
        h.flush()
    records = _span_records(db)
    assert len(records) == 1
    ctx = records[0]["context"]
    assert ctx["span_name"] == "setup_db"
    assert ctx["parent_span_id"] is None
    assert ctx["span_ms"] >= 5  # at least 5ms from sleep


def test_nested_spans_link_parent(tmp_path):
    db = _setup(tmp_path)
    with ulog.span("outer") as outer_id:
        with ulog.span("inner"):
            pass
    for h in logging.getLogger().handlers:
        h.flush()
    records = _span_records(db)
    # Inner emits first (finished first), outer emits second.
    assert len(records) == 2
    inner = records[0]["context"]
    outer = records[1]["context"]
    assert inner["span_name"] == "inner"
    assert outer["span_name"] == "outer"
    # Inner's parent is outer's id.
    assert inner["parent_span_id"] == outer["span_id"] == outer_id


def test_span_status_fail_on_exception(tmp_path):
    db = _setup(tmp_path)
    with pytest.raises(ValueError), ulog.span("boom"):
        raise ValueError("bad")
    for h in logging.getLogger().handlers:
        h.flush()
    records = _span_records(db)
    assert records[0]["context"]["span_status"] == "fail"


def test_current_span_id_outside_is_none():
    assert ulog.current_span_id() is None


def test_current_span_id_inside_matches_yielded(tmp_path):
    _setup(tmp_path)
    with ulog.span("x") as sid:
        assert ulog.current_span_id() == sid
    assert ulog.current_span_id() is None


def test_three_level_nesting(tmp_path):
    db = _setup(tmp_path)
    with ulog.span("a") as a_id:
        with ulog.span("b") as b_id:
            with ulog.span("c"):
                pass
    for h in logging.getLogger().handlers:
        h.flush()
    records = _span_records(db)
    # Emit order: c, b, a (innermost finishes first).
    names = [r["context"]["span_name"] for r in records]
    assert names == ["c", "b", "a"]
    assert records[0]["context"]["parent_span_id"] == b_id
    assert records[1]["context"]["parent_span_id"] == a_id
    assert records[2]["context"]["parent_span_id"] is None
