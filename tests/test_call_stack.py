"""Tests for PRD-v0.12 — per-record call-stack capture."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    # Reset stack capture between tests.
    from ulog import _stack
    _stack.configure(capture_stack=False, with_locals=False)
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    _stack.configure(capture_stack=False, with_locals=False)
    ulog.clear()


def _fetch_context(db: Path) -> list[dict]:
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT context FROM logs ORDER BY id")).all()
    engine.dispose()
    return [json.loads(r[0]) if r[0] else {} for r in rows]


def test_stack_capture_opt_in(tmp_path):
    """Without capture_stack=True, no `stack` key in context."""
    db = tmp_path / "off.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("hi")
    for h in logging.getLogger().handlers:
        h.flush()
    contexts = [c or {} for c in _fetch_context(db)]
    assert all("stack" not in c for c in contexts)


def test_stack_capture_enabled_attaches_frames(tmp_path):
    db = tmp_path / "on.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1, capture_stack=True)
    ulog.get_logger().info("hi")
    for h in logging.getLogger().handlers:
        h.flush()
    contexts = _fetch_context(db)
    assert "stack" in contexts[0]
    frames = contexts[0]["stack"]
    assert isinstance(frames, list)
    assert len(frames) > 0
    # Each frame has the expected keys.
    for frame in frames:
        assert "function" in frame
        assert "file" in frame
        assert "line" in frame


def test_stack_omits_logging_internals(tmp_path):
    db = tmp_path / "clean.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1, capture_stack=True)
    ulog.get_logger().info("hi")
    for h in logging.getLogger().handlers:
        h.flush()
    contexts = _fetch_context(db)
    frames = contexts[0]["stack"]
    # No frames from logging/ or ulog/handlers/ should leak through.
    for frame in frames:
        assert "logging/" not in frame["file"]
        assert "ulog/handlers/" not in frame["file"]


def test_stack_locals_capture_opt_in(tmp_path):
    """capture_stack_locals=True adds `locals` field to each frame."""

    def _trigger():
        my_var = "hello world"
        order_id = 42
        ulog.get_logger().info("emit")
        # Reference vars so they're alive at emit time.
        _ = (my_var, order_id)

    db = tmp_path / "locals.sqlite"
    ulog.setup(
        handlers=["sql"],
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
        capture_stack=True,
        capture_stack_locals=True,
    )
    _trigger()
    for h in logging.getLogger().handlers:
        h.flush()
    contexts = _fetch_context(db)
    frames = contexts[0]["stack"]
    has_locals = any("locals" in f for f in frames)
    assert has_locals, f"expected locals on at least one frame: {frames}"


def test_stack_excluded_when_user_bound(tmp_path):
    """User-bound `stack=...` wins (capture is a default)."""
    db = tmp_path / "userbind.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1, capture_stack=True)
    with ulog.context(stack="custom"):
        ulog.get_logger().info("hi")
    for h in logging.getLogger().handlers:
        h.flush()
    contexts = _fetch_context(db)
    assert contexts[0]["stack"] == "custom"
