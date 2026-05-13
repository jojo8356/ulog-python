"""I5 / SC5 — qlnes byte-stable contract (Story 7.8).

This test pins the v0.1 baseline output of every built-in formatter
for stdlib `logging.getLogger(__name__).<level>(msg)` calls. Any
future change that breaks invariant I5 (`logging` compat forever)
fails CI immediately.

The byte sequences asserted below are the v0.1.0 baseline. Any
change to them is a public-API break.
"""

from __future__ import annotations

import contextlib
import io
import logging

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


def _emit(level: str, msg: str, *, name: str, **setup_kwargs: object) -> str:
    """Setup ulog with `setup_kwargs`, emit `msg` at `level`, return captured output."""
    buf = io.StringIO()
    setup_kwargs.setdefault("level", level.upper())
    ulog.setup(color="never", stream=buf, name=name, **setup_kwargs)  # type: ignore[arg-type]
    getattr(logging.getLogger(name), level.lower())(msg)
    return buf.getvalue()


# ---- qlnes (default formatter — the I5 / SC5 contract) -------------------


def test_qlnes_info_no_prefix_byte_stable():
    """Bare logger.info() through qlnes formatter without prefix kwarg
    emits just the message + newline. v0.1 baseline."""
    out = _emit("info", "hello", name="t_qlnes_info_no_prefix", format="qlnes")
    assert out == "hello\n"


def test_qlnes_error_with_prefix_byte_stable():
    """qlnes with prefix=<name> emits `<prefix>: <level>: <msg>\\n`."""
    out = _emit(
        "error",
        "boom",
        name="t_qlnes_err_prefix",
        format="qlnes",
        prefix="myapp",
    )
    assert out == "myapp: error: boom\n"


def test_qlnes_warning_with_prefix_byte_stable():
    out = _emit(
        "warning",
        "slow query",
        name="t_qlnes_warn_prefix",
        format="qlnes",
        prefix="api",
    )
    assert out == "api: warning: slow query\n"


def test_qlnes_critical_with_prefix_byte_stable():
    out = _emit(
        "critical",
        "DB down",
        name="t_qlnes_crit_prefix",
        format="qlnes",
        prefix="store",
    )
    assert out == "store: critical: DB down\n"


def test_qlnes_debug_bare_msg_byte_stable():
    """qlnes formatter omits the prefix for INFO + DEBUG (silent
    happy-path levels). v0.1 contract — see formatters.py:51."""
    out = _emit(
        "debug",
        "cache miss",
        name="t_qlnes_dbg_prefix",
        format="qlnes",
        prefix="cache",
    )
    assert out == "cache miss\n"


def test_qlnes_info_with_prefix_still_bare():
    """Even with a prefix kwarg, INFO is bare (silent happy-path)."""
    out = _emit(
        "info",
        "ok",
        name="t_qlnes_info_with_prefix",
        format="qlnes",
        prefix="api",
    )
    assert out == "ok\n"


# ---- simple formatter ----------------------------------------------------


def test_simple_info_byte_stable():
    out = _emit("info", "hi", name="t_simple_info", format="simple")
    assert out == "[INFO] hi\n"


def test_simple_warning_byte_stable():
    out = _emit("warning", "warn", name="t_simple_warn", format="simple")
    assert out == "[WARNING] warn\n"


# ---- I5 contract ---------------------------------------------------------


def test_stdlib_logger_works_after_setup_byte_identical():
    """The I5 invariant: `logging.getLogger(__name__).info("x")` continues
    to work byte-identical to the v0.1 baseline after ulog.setup()."""
    out = _emit("info", "x", name="t_stdlib_info_compat", format="qlnes")
    assert out == "x\n"
