"""Tests for `ulog snapshot` (PRD-v0.6.1)."""

from __future__ import annotations

import contextlib
import csv as _csv
import json
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
    db = tmp_path / "in.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("svc")
    log.info("a")
    log.error("b")
    log.warning("c")
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_snapshot_log_format(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "today.log"
    rc = cli_main(["snapshot", str(db), "--format", "log", "--out", str(out), "--since", "1y"])
    assert rc == 0
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    # INFO line bare, others prefixed.
    assert "svc  a" in lines[0]
    assert "error:" in lines[1] or "error:" in lines[2]


def test_snapshot_jsonl_format(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "today.jsonl"
    rc = cli_main(["snapshot", str(db), "--format", "jsonl", "--out", str(out), "--since", "1y"])
    assert rc == 0
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert "ts" in obj
        assert "level" in obj
        assert "msg" in obj


def test_snapshot_csv_format(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "today.csv"
    rc = cli_main(["snapshot", str(db), "--format", "csv", "--out", str(out), "--since", "1y"])
    assert rc == 0
    with out.open(encoding="utf-8") as fh:
        rows = list(_csv.reader(fh))
    assert rows[0] == ["ts", "level", "logger", "msg", "file", "line", "context_json"]
    assert len(rows) == 4  # header + 3 records


def test_snapshot_html_format(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "html"
    rc = cli_main(["snapshot", str(db), "--format", "html", "--out", str(out), "--since", "1y"])
    assert rc == 0
    assert (out / "index.html").exists()
    assert (out / "README.html").exists()


def test_snapshot_filter_keeps_only_errors(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "errors.jsonl"
    rc = cli_main(
        ["snapshot", str(db), "--format", "jsonl", "--out", str(out), "--since", "1y", "--filter", "level=ERROR"]
    )
    assert rc == 0
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0])["level"] == "ERROR"


def test_snapshot_refuses_overwrite_without_force(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "today.log"
    out.write_text("stale\n", encoding="utf-8")
    rc = cli_main(["snapshot", str(db), "--format", "log", "--out", str(out), "--since", "1y"])
    assert rc == 2


def test_snapshot_force_overwrites(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "today.log"
    out.write_text("stale\n", encoding="utf-8")
    rc = cli_main(["snapshot", str(db), "--format", "log", "--out", str(out), "--since", "1y", "--force"])
    assert rc == 0
    assert "stale" not in out.read_text(encoding="utf-8")


def test_snapshot_missing_db_exits_2(tmp_path):
    rc = cli_main(["snapshot", str(tmp_path / "missing.sqlite"), "--format", "log", "--out", str(tmp_path / "o.log")])
    assert rc == 2


def test_snapshot_since_today_default(tmp_path):
    """Default --since=today should pick today's records."""
    db = _seed(tmp_path)
    out = tmp_path / "today.log"
    rc = cli_main(["snapshot", str(db), "--format", "log", "--out", str(out)])
    assert rc == 0
    # All 3 records emitted today.
    assert len(out.read_text(encoding="utf-8").strip().split("\n")) == 3
