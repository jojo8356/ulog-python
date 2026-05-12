"""Tests for `ulog trace <trace_id>` CLI (Story 6.2)."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog
from ulog._cli import main
from ulog._otel import clear_trace_context, set_trace_context


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    clear_trace_context()
    yield
    clear_trace_context()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


def _seed_traced_db(tmp_path: Path) -> tuple[Path, str]:
    db = tmp_path / "trace.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    set_trace_context("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "1111111111111111")
    log = ulog.get_logger("svc.auth")
    log.info("step 1")
    log.error("step 2 fail")
    clear_trace_context()
    set_trace_context("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "2222222222222222")
    ulog.get_logger("svc.other").info("unrelated")
    for h in logging.getLogger().handlers:
        h.flush()
    return db, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_trace_cli_lists_matching_records(tmp_path, capsys):
    db, tid = _seed_traced_db(tmp_path)
    rc = main(["trace", tid, "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "2 record(s)" in out
    assert "step 1" in out
    assert "step 2 fail" in out
    assert "unrelated" not in out


def test_trace_cli_no_match(tmp_path, capsys):
    db, _ = _seed_traced_db(tmp_path)
    rc = main(["trace", "ffffffffffffffffffffffffffffffff", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No records for trace_id" in out


def test_trace_cli_missing_db_exit_2(tmp_path):
    rc = main(["trace", "abc", "--db", str(tmp_path / "nope.sqlite")])
    assert rc == 2
