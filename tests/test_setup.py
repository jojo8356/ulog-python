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


# ---- v0.2.2 profile (prod / test / auto) --------------------------------


def test_default_db_path_for_known_profiles(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    p_prod = ulog.default_db_path("prod")
    p_test = ulog.default_db_path("test")
    assert p_prod == tmp_path / "ulog" / "prod.sqlite"
    assert p_test == tmp_path / "ulog" / "test.sqlite"
    assert p_prod != p_test


def test_default_db_path_rejects_unknown_profile():
    with pytest.raises(ValueError, match="unknown profile"):
        ulog.default_db_path("staging")


def test_setup_profile_prod_creates_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    ulog.setup(profile="prod", color="never")
    log = ulog.get_logger()
    log.info("from prod")
    for h in logging.getLogger().handlers:
        h.flush()
    assert (tmp_path / "ulog" / "prod.sqlite").exists()


def test_setup_profile_test_creates_separate_db(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    ulog.setup(profile="test", color="never")
    ulog.get_logger().info("from test")
    for h in logging.getLogger().handlers:
        h.flush()
    assert (tmp_path / "ulog" / "test.sqlite").exists()
    # prod path should NOT have been touched
    assert not (tmp_path / "ulog" / "prod.sqlite").exists()


def test_setup_profile_auto_picks_test_under_pytest(monkeypatch, tmp_path):
    """`profile='auto'` should resolve to 'test' when pytest is running.

    We're literally inside pytest right now, so the test MUST land in
    the test DB."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    ulog.setup(profile="auto", color="never")
    ulog.get_logger().info("auto-detected")
    for h in logging.getLogger().handlers:
        h.flush()
    assert (tmp_path / "ulog" / "test.sqlite").exists()
    assert not (tmp_path / "ulog" / "prod.sqlite").exists()


def test_setup_profile_none_keeps_v01_stream_only_behavior(monkeypatch, tmp_path):
    """No `profile=` arg → no SQL handler installed; backward compat."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    ulog.setup(stream=io.StringIO(), color="never")
    # Default should NOT touch ~/.cache/ulog/ at all
    assert not (tmp_path / "ulog").exists()


def test_setup_explicit_sql_url_overrides_profile(tmp_path):
    """If both profile= and sql_url= are passed, sql_url wins."""
    custom = tmp_path / "custom.sqlite"
    ulog.setup(
        profile="prod", sql_url=f"sqlite:///{custom}", color="never"
    )
    ulog.get_logger().info("custom")
    for h in logging.getLogger().handlers:
        h.flush()
    assert custom.exists()


def test_setup_rejects_unknown_profile():
    with pytest.raises(ValueError, match="unknown profile"):
        ulog.setup(profile="staging")  # type: ignore[arg-type]


def test_profiles_constant():
    assert ulog.PROFILES == ("prod", "test")
