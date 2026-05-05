"""ulog pytest plugin — auto-discovered via ``[project.entry-points.pytest11]``.

Story 1.1 owns: option registration + gating decision (``config._ulog_enabled``).
Stories 1.2-1.5 own: lifecycle hooks, test_id propagation, summary output.

The plugin is OFF by default unless either:
  (a) a host ``conftest.py`` has called ``ulog.setup(...)`` (i.e.
      ``ulog.is_configured()`` returns True), OR
  (b) the user passes ``--ulog-db PATH`` on the pytest CLI.

``--ulog-disable`` short-circuits the plugin even when (a) or (b) hold.
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --ulog-db, --ulog-disable, --ulog-summary."""
    group = parser.getgroup("ulog", "ulog test integration")
    group.addoption(
        "--ulog-db",
        action="store",
        dest="ulog_db",
        default=None,
        metavar="PATH",
        help=(
            "Override the destination DB for ulog test records. "
            "Setup is auto-configured if no host setup() exists."
        ),
    )
    group.addoption(
        "--ulog-disable",
        action="store_true",
        dest="ulog_disable",
        default=False,
        help=(
            "Short-circuit the ulog pytest plugin even when host "
            "setup() exists or --ulog-db is set."
        ),
    )
    group.addoption(
        "--ulog-summary",
        action="store_true",
        dest="ulog_summary",
        default=True,
        help=(
            "Print one-line stderr summary after the session "
            "(default ON; -q suppresses)."
        ),
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    """Compute the gating decision and store it on ``config._ulog_enabled``.

    ``trylast=True`` is critical: pytest schedules entry-point plugins'
    ``pytest_configure`` BEFORE the user's ``conftest.py`` ``pytest_configure``.
    Without it, a host that calls ``ulog.setup(...)`` in their conftest
    sees their own configure run AFTER ours, and our gate (which reads
    ``ulog.is_configured()``) would always be False — disabling the plugin
    even though the user intended to enable it.
    """
    import ulog  # lazy: only on pytest config
    enabled = (
        not config.getoption("ulog_disable")
        and (
            ulog.is_configured()
            or bool(config.getoption("ulog_db"))
        )
    )
    config._ulog_enabled = enabled  # type: ignore[attr-defined]


def _get_enabled(config: pytest.Config) -> bool:
    """Helper consumed by Story 1.2+ hooks. Defaults False if attr missing."""
    return bool(getattr(config, "_ulog_enabled", False))
