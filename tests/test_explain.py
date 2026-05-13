"""Tests for v0.7 phase 3 — `ulog explain` span waterfall CLI."""

from __future__ import annotations

import contextlib
import logging
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
    with ulog.span("outer"):
        with ulog.span("setup_db"):
            pass
        with ulog.span("body"):
            with ulog.span("query"):
                pass
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_explain_renders_tree(tmp_path, capsys):
    db = _seed(tmp_path)
    rc = cli_main(["explain", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "outer" in out
    assert "setup_db" in out
    assert "body" in out
    assert "query" in out


def test_explain_indentation_reflects_nesting(tmp_path, capsys):
    db = _seed(tmp_path)
    cli_main(["explain", "--db", str(db)])
    out = capsys.readouterr().out
    # outer is at depth 0 → no leading `│ `
    outer_line = next(line for line in out.splitlines() if "outer " in line or "outer  " in line)
    # query is at depth 2 → 2 leading `│ ` prefixes
    query_line = next(line for line in out.splitlines() if "query " in line or "query  " in line)
    assert outer_line.count("│ ") < query_line.count("│ ")


def test_explain_missing_db_returns_2(tmp_path, capsys):
    rc = cli_main(["explain", "--db", str(tmp_path / "missing.sqlite")])
    assert rc == 2


def test_explain_no_spans_returns_1(tmp_path, capsys):
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("no span")
    for h in logging.getLogger().handlers:
        h.flush()
    rc = cli_main(["explain", "--db", str(db)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "no span" in err


def test_explain_root_filter(tmp_path, capsys):
    """--root <prefix> restricts to one tree."""
    db = _seed(tmp_path)
    # Read the outer span_id to use as prefix.
    from sqlalchemy import create_engine, text
    import json as _j

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        ctx = conn.execute(
            text("SELECT context FROM logs WHERE logger='ulog.span' ORDER BY id DESC LIMIT 1")
        ).scalar()
    engine.dispose()
    outer_sid = _j.loads(ctx)["span_id"]
    rc = cli_main(["explain", "--db", str(db), "--root", outer_sid[:4]])
    assert rc == 0
    out = capsys.readouterr().out
    assert "outer" in out
