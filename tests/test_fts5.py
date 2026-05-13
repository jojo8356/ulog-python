"""Tests for v0.4.4 — FTS5 opt-in search."""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from pathlib import Path

import pytest

import ulog
from ulog._cli import main as cli_main


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
    log = ulog.get_logger()
    log.info("checkout success for user_42")
    log.error("database connection timeout")
    log.warning("stripe rate limit")
    log.info("login success")
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_enable_fts5_creates_table(tmp_path, capsys):
    db = _seed(tmp_path)
    rc = cli_main(["enable-fts5", str(db)])
    assert rc == 0
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='logs_fts'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_enable_fts5_idempotent(tmp_path, capsys):
    db = _seed(tmp_path)
    cli_main(["enable-fts5", str(db)])
    rc = cli_main(["enable-fts5", str(db)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "already exists" in err or "No-op" in err


def test_enable_fts5_missing_db_returns_2(tmp_path, capsys):
    rc = cli_main(["enable-fts5", str(tmp_path / "missing.sqlite")])
    assert rc == 2


def test_search_after_enable_uses_fts5(tmp_path):
    db = _seed(tmp_path)
    cli_main(["enable-fts5", str(db)])
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    adapter = SQLiteAdapter(db)
    assert adapter._has_fts5 is True
    result = adapter.query(Filters(search="timeout"))
    msgs = [r.msg for r in result.records]
    assert any("timeout" in m for m in msgs)
    assert len(msgs) == 1


def test_search_without_fts5_falls_back_to_like(tmp_path):
    db = _seed(tmp_path)
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    adapter = SQLiteAdapter(db)
    assert adapter._has_fts5 is False
    # LIKE %timeout% still works.
    result = adapter.query(Filters(search="timeout"))
    msgs = [r.msg for r in result.records]
    assert any("timeout" in m for m in msgs)


def test_fts5_keeps_in_sync_on_new_insert(tmp_path):
    db = _seed(tmp_path)
    cli_main(["enable-fts5", str(db)])
    # Append a record via raw SQL (triggers should fire).
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO logs (ts, level, logger, msg, file, line, chain_pos) "
        "VALUES ('2026-05-13', 'INFO', 'svc', 'fresh insert keyword', 'x.py', 1, 0)"
    )
    conn.commit()
    n = conn.execute(
        "SELECT count(*) FROM logs_fts WHERE msg MATCH 'fresh'"
    ).fetchone()[0]
    conn.close()
    assert n == 1
