"""Tests for ulog.testing.pytest_plugin (Story 1.1).

Covers FR51-53 (auto-discovery + gating) and FR67-69 (CLI flag registration).
Uses pytest's built-in ``pytester`` fixture (ships with pytest 7.0+, no new
dep) to run pytest-in-pytest scenarios.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

# pytester relies on pytest collecting `pytester` as a plugin.
# Activating it for this module is the canonical pattern.
pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def _isolate_logging():
    """Strip _ulog_managed handlers between tests (mirrors tests/test_setup.py)."""
    yield
    for name in (None, "test", "test.sub", "myapp", "qlnes"):
        logger = logging.getLogger(name)
        for h in list(logger.handlers):
            if getattr(h, "_ulog_managed", False):
                logger.removeHandler(h)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def test_plugin_is_registered(pytester: pytest.Pytester) -> None:
    """AC1 — pytest --trace-config lists the ulog plugin."""
    pytester.makepyfile("def test_x(): pass")
    result = pytester.runpytest("--trace-config")
    # Match the actual plugin module path (more specific than "*ulog*", which
    # could spuriously match unrelated mentions of the string "ulog").
    result.stdout.fnmatch_lines(["*ulog.testing.pytest_plugin*"])


def test_gate_off_by_default(pytester: pytest.Pytester) -> None:
    """AC2 — gate is False with no host setup and no --ulog-db."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert getattr(pytestconfig, '_ulog_enabled', None) is False
        """
    )
    result = pytester.runpytest()
    assert result.ret == 0


def test_gate_on_with_ulog_db(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC2 inverse — --ulog-db sets gate True."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is True
        """
    )
    db = tmp_path / "x.sqlite"
    result = pytester.runpytest("--ulog-db", str(db))
    assert result.ret == 0


def test_gate_on_with_host_setup(pytester: pytest.Pytester) -> None:
    """AC2 inverse — host conftest setup() sets gate True.

    Verifies that ``@pytest.hookimpl(trylast=True)`` correctly schedules
    our pytest_configure AFTER the user's conftest pytest_configure.
    """
    pytester.makeconftest(
        """
        import ulog
        def pytest_configure(config):
            ulog.setup()  # idempotent — installs _ulog_managed handler
        """
    )
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is True
        """
    )
    result = pytester.runpytest()
    assert result.ret == 0


def test_ulog_disable_overrides(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC3 — --ulog-disable short-circuits even when other gating triggers fire."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is False
        """
    )
    db = tmp_path / "x.sqlite"
    result = pytester.runpytest("--ulog-db", str(db), "--ulog-disable")
    assert result.ret == 0


def test_three_flags_in_help(pytester: pytest.Pytester) -> None:
    """AC4 — the three flags appear in pytest --help."""
    result = pytester.runpytest("--help")
    output = result.stdout.str() + result.stderr.str()
    assert "--ulog-db" in output
    assert "--ulog-disable" in output
    assert "--ulog-summary" in output
