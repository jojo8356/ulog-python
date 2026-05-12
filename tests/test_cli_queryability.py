"""Tests for `ulog correlate / bisect / replay` CLI subcommands — Story 4.8."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog
from ulog._cli import main


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


def _seed_chain(tmp_path: Path, n: int = 5) -> Path:
    db = tmp_path / "q.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=url, sql_batch_size=1)
    log = ulog.get_logger("svc")
    for i in range(n):
        level = "error" if i % 2 == 0 else "info"
        getattr(log, level)("msg %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


# ---- correlate ----------------------------------------------------------


def test_correlate_cli_prints_report(tmp_path, capsys):
    db = _seed_chain(tmp_path, n=10)
    rc = main(["correlate", "level=ERROR", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "filter:" in out
    assert "baseline:" in out
    assert "wall:" in out


def test_correlate_cli_invalid_filter_exit_2(tmp_path, capsys):
    db = _seed_chain(tmp_path, n=1)
    rc = main(["correlate", "level=", "--db", str(db)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "invalid filter" in err


def test_correlate_cli_nonexistent_db_exit_2(tmp_path):
    rc = main(["correlate", "level=ERROR", "--db", str(tmp_path / "no.sqlite")])
    assert rc == 2


# ---- bisect -------------------------------------------------------------


def test_bisect_cli_prints_first_match(tmp_path, capsys):
    db = _seed_chain(tmp_path, n=5)
    rc = main(["bisect", "msg 2", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Found at chain_pos=" in out
    assert "msg 2" in out


def test_bisect_cli_no_match_exit_0(tmp_path, capsys):
    db = _seed_chain(tmp_path, n=3)
    rc = main(["bisect", "nothing-here", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No record matched pattern" in out


def test_bisect_cli_invalid_regex_exit_2(tmp_path, capsys):
    db = _seed_chain(tmp_path, n=1)
    rc = main(["bisect", "(unclosed", "--db", str(db)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "invalid regex" in err


# ---- replay -------------------------------------------------------------


def test_replay_cli_prints_records(tmp_path, capsys):
    db = _seed_chain(tmp_path, n=5)
    rc = main(["replay", "level=ERROR", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    # n=5 records, alternating error/info: positions 1,3,5 are ERROR.
    assert "records replayed" in out
    assert "chain_pos=1" in out


def test_replay_cli_to_pytest_generates_file(tmp_path, capsys):
    db = _seed_chain(tmp_path, n=3)
    out_path = tmp_path / "test_generated.py"
    rc = main(
        [
            "replay",
            "level=ERROR",
            "--db",
            str(db),
            "--to-pytest",
            str(out_path),
            "--incident-hash",
            "abc",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert out_path.exists()
    assert "records snapshotted" in out
    content = out_path.read_text(encoding="utf-8")
    assert "from ulog.testing import replay_records" in content


# ---- dispatcher smoke ---------------------------------------------------


def test_subcommands_registered_in_dispatcher(capsys):
    # `--help` invokes argparse.print_help() which raises SystemExit.
    # Use the no-subcommand path which prints help + returns 2.
    rc = main([])
    out = capsys.readouterr().out
    assert rc == 2
    for sub in ("correlate", "bisect", "replay"):
        assert sub in out
