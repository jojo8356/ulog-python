"""Tests for ulog.setup + idempotency + name-scoping."""
from __future__ import annotations

import io
import logging

import pytest

import ulog


@pytest.fixture(autouse=True)
def _isolate_logging():
    """Each test starts from a clean slate. Removes ULog handlers from
    every logger we touched."""
    yield
    for name in (None, "test", "test.sub", "myapp", "qlnes"):
        logger = logging.getLogger(name)
        for h in list(logger.handlers):
            if getattr(h, "_ulog_managed", False):
                logger.removeHandler(h)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def test_setup_returns_logger():
    log = ulog.setup(stream=io.StringIO())
    assert isinstance(log, logging.Logger)


def test_setup_default_format_is_qlnes():
    """Default format is 'qlnes' (the project that ULog was carved out of)."""
    sink = io.StringIO()
    ulog.setup(stream=sink)
    log = ulog.get_logger()
    log.error("boom")
    out = sink.getvalue().strip()
    assert "qlnes: error: boom" == out


def test_setup_emits_to_provided_stream():
    sink = io.StringIO()
    ulog.setup(stream=sink, color="never")
    ulog.get_logger().info("hello")
    assert "hello" in sink.getvalue()


def test_setup_idempotent_does_not_double_log():
    """Calling setup twice replaces (not appends) the handler."""
    sink = io.StringIO()
    ulog.setup(stream=sink, color="never")
    ulog.setup(stream=sink, color="never")  # second call
    ulog.get_logger().info("once")
    lines = [ln for ln in sink.getvalue().splitlines() if ln]
    assert lines == ["once"]


def test_setup_preserves_user_handlers():
    """ULog only manages its own handler; pre-existing user handlers stay."""
    user_sink = io.StringIO()
    user_handler = logging.StreamHandler(user_sink)
    logging.getLogger().addHandler(user_handler)
    try:
        sink = io.StringIO()
        ulog.setup(stream=sink, color="never")
        # The user handler should still be on root
        assert user_handler in logging.getLogger().handlers
        # Setup again — user handler still there
        ulog.setup(stream=sink, color="never")
        assert user_handler in logging.getLogger().handlers
    finally:
        logging.getLogger().removeHandler(user_handler)


def test_setup_with_named_logger_does_not_propagate_by_default():
    sink = io.StringIO()
    ulog.setup(stream=sink, color="never", name="myapp")
    log = ulog.get_logger("myapp")
    assert log.propagate is False


def test_setup_named_with_propagate_true():
    ulog.setup(stream=io.StringIO(), color="never", name="myapp", propagate=True)
    log = ulog.get_logger("myapp")
    assert log.propagate is True


def test_setup_rejects_unknown_level():
    with pytest.raises(ValueError, match="log level"):
        ulog.setup(level="VERBOSE", stream=io.StringIO())


def test_setup_rejects_unknown_color_mode():
    with pytest.raises(ValueError, match="color mode"):
        ulog.setup(color="rainbow", stream=io.StringIO())  # type: ignore[arg-type]


def test_setup_rejects_unknown_format():
    with pytest.raises(ValueError, match="formatter"):
        ulog.setup(format="bogus", stream=io.StringIO())


def test_setup_accepts_int_level():
    """Stdlib int levels (logging.DEBUG, etc.) accepted."""
    sink = io.StringIO()
    ulog.setup(level=logging.DEBUG, stream=sink, color="never")
    ulog.get_logger().debug("dbg")
    assert "dbg" in sink.getvalue()


def test_get_logger_works_without_setup():
    """Library use case: get_logger() works even when setup() never ran."""
    log = ulog.get_logger("untouched.module")
    assert isinstance(log, logging.Logger)
    # Won't raise even if no handlers — Python falls through to default
    log.info("does not crash")


def test_set_level_changes_existing_logger():
    sink = io.StringIO()
    ulog.setup(level="WARNING", stream=sink, color="never")
    ulog.get_logger().info("hidden")
    assert sink.getvalue() == ""
    ulog.set_level("INFO")
    ulog.get_logger().info("visible")
    assert "visible" in sink.getvalue()


def test_is_configured_reports_correctly():
    assert ulog.is_configured("test") is False
    ulog.setup(stream=io.StringIO(), name="test")
    assert ulog.is_configured("test") is True


def test_log_levels_constant():
    assert ulog.LOG_LEVELS == ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
