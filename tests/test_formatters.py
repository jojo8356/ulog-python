"""Tests for the four built-in formatters: qlnes, simple, verbose, json."""

from __future__ import annotations

import io
import json
import logging

import pytest

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    yield
    for name in (None, "test"):
        logger = logging.getLogger(name)
        for h in list(logger.handlers):
            if getattr(h, "_ulog_managed", False):
                logger.removeHandler(h)
        logger.setLevel(logging.NOTSET)
    ulog.clear()


# ---- qlnes ----------------------------------------------------------------


def test_qlnes_info_is_bare():
    sink = io.StringIO()
    ulog.setup(format="qlnes", stream=sink, color="never")
    ulog.get_logger().info("hello")
    assert sink.getvalue().strip() == "hello"


def test_qlnes_warning_has_prefix():
    sink = io.StringIO()
    ulog.setup(format="qlnes", stream=sink, color="never")
    ulog.get_logger().warning("careful")
    assert sink.getvalue().strip() == "qlnes: warning: careful"


def test_qlnes_error_has_prefix():
    sink = io.StringIO()
    ulog.setup(format="qlnes", stream=sink, color="never")
    ulog.get_logger().error("boom")
    assert sink.getvalue().strip() == "qlnes: error: boom"


def test_qlnes_custom_prefix():
    sink = io.StringIO()
    ulog.setup(format="qlnes", stream=sink, color="never", prefix="myapp")
    ulog.get_logger().error("boom")
    assert sink.getvalue().strip() == "myapp: error: boom"


def test_qlnes_color_on_wraps_prefix_in_ansi():
    """When color is forced on, the level prefix gets ANSI codes."""
    sink = io.StringIO()
    ulog.setup(format="qlnes", stream=sink, color="always")
    ulog.get_logger().error("boom")
    out = sink.getvalue()
    assert "\x1b[" in out  # ANSI escape
    assert "boom" in out


# ---- simple ---------------------------------------------------------------


def test_simple_info_has_bracketed_prefix():
    sink = io.StringIO()
    ulog.setup(format="simple", stream=sink, color="never")
    ulog.get_logger().info("hello")
    assert sink.getvalue().strip() == "[INFO] hello"


def test_simple_error():
    sink = io.StringIO()
    ulog.setup(format="simple", stream=sink, color="never")
    ulog.get_logger().error("boom")
    assert sink.getvalue().strip() == "[ERROR] boom"


# ---- verbose --------------------------------------------------------------


def test_verbose_includes_logger_name_and_file():
    sink = io.StringIO()
    ulog.setup(format="verbose", stream=sink, color="never")
    ulog.get_logger("my.module").info("hello")
    out = sink.getvalue().strip()
    assert "INFO" in out
    assert "[my.module]" in out
    assert "hello" in out
    assert "test_formatters.py" in out  # file:line at end


def test_verbose_includes_bound_context_fields():
    sink = io.StringIO()
    ulog.setup(format="verbose", stream=sink, color="never")
    ulog.bind(rom="alter_ego")
    ulog.get_logger().info("rendering")
    out = sink.getvalue()
    assert "rom='alter_ego'" in out


# ---- json -----------------------------------------------------------------


def test_json_one_object_per_record():
    sink = io.StringIO()
    ulog.setup(format="json", stream=sink, color="never")
    ulog.get_logger("app").info("rendered")
    line = sink.getvalue().strip()
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app"
    assert payload["msg"] == "rendered"
    assert "ts" in payload
    assert payload["ts"].endswith("Z")
    assert payload["file"].endswith(".py")
    assert isinstance(payload["line"], int)


def test_json_includes_bound_fields():
    sink = io.StringIO()
    ulog.setup(format="json", stream=sink, color="never")
    ulog.bind(rom_sha="abc", song=0)
    ulog.get_logger().info("step")
    payload = json.loads(sink.getvalue().strip())
    assert payload["rom_sha"] == "abc"
    assert payload["song"] == 0


def test_json_includes_extra_fields():
    sink = io.StringIO()
    ulog.setup(format="json", stream=sink, color="never")
    ulog.get_logger().info("rendered", extra={"frames": 600, "engine": "famitracker"})
    payload = json.loads(sink.getvalue().strip())
    assert payload["frames"] == 600
    assert payload["engine"] == "famitracker"


def test_json_serializes_exception():
    sink = io.StringIO()
    ulog.setup(format="json", stream=sink, color="never")
    log = ulog.get_logger()
    try:
        raise ValueError("nope")
    except ValueError:
        log.exception("caught")
    payload = json.loads(sink.getvalue().strip())
    assert payload["msg"] == "caught"
    assert payload["exc"]["type"] == "ValueError"
    assert payload["exc"]["msg"] == "nope"
    assert isinstance(payload["exc"]["tb"], list)
    assert any("test_formatters.py" in line for line in payload["exc"]["tb"])


# ---- registration ---------------------------------------------------------


def test_register_custom_formatter():
    class Upper(logging.Formatter):
        def format(self, record):
            return record.getMessage().upper()

    ulog.register_formatter("upper", Upper)
    sink = io.StringIO()
    ulog.setup(format="upper", stream=sink, color="never")
    ulog.get_logger().info("hello")
    assert sink.getvalue().strip() == "HELLO"


def test_register_rejects_non_formatter():
    with pytest.raises(TypeError, match=r"logging\.Formatter"):
        ulog.register_formatter("bad", str)  # type: ignore[arg-type]
