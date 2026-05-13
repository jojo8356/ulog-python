"""Tests for v0.4.4 phase 2 — startup pre-warm."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from unittest.mock import patch

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


def _seed(tmp_path: Path) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("seed")
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_prewarm_calls_adapter_query(tmp_path):
    """ulog web main() issues a Filters() query at startup."""
    db = _seed(tmp_path)
    from ulog.web import cli as web_cli

    # Patch the runner that serves requests so main() returns early
    # after the pre-warm step but before opening a socket.
    with patch("django.core.servers.basehttp.run", side_effect=KeyboardInterrupt) as _run, patch(
        "ulog.web.viewer.adapters.SQLiteAdapter.query"
    ) as mock_query, patch.object(web_cli, "_open_browser_when_ready"):
        web_cli.main([str(db), "--no-open", "--port", "0", "--no-author-index"])
    # The adapter's query() was called at least once during pre-warm.
    assert mock_query.called


def test_prewarm_failure_is_non_fatal(tmp_path, capsys):
    """A broken pre-warm doesn't abort the CLI."""
    db = _seed(tmp_path)
    from ulog.web import cli as web_cli

    with patch("django.core.servers.basehttp.run", side_effect=KeyboardInterrupt), patch(
        "ulog.web.viewer.adapters.SQLiteAdapter.query",
        side_effect=RuntimeError("boom"),
    ), patch.object(web_cli, "_open_browser_when_ready"):
        rc = web_cli.main([str(db), "--no-open", "--port", "0", "--no-author-index"])
    # 0 even when prewarm raised.
    assert rc == 0
    err = capsys.readouterr().err
    assert "prewarm failed" in err
