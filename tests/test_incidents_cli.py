"""Tests for `ulog incidents` CLI (Stories 5.4 + 5.5 / FR107, FR108)."""

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


def _setup_seed(tmp_path: Path) -> tuple[Path, list[str]]:
    """3 errors, resolve the first two — leaves 1 open."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "i.sqlite"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
    )
    for i in range(3):
        ulog.get_logger().error("boom %d", i)
    # Grab hashes.
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT hex(record_hash) FROM logs WHERE level='ERROR' ORDER BY chain_pos")
        ).all()
    engine.dispose()
    hashes = [r[0] for r in rows]
    ulog.resolve(hashes[0], by="Johan")
    ulog.resolve(hashes[1], by="Erwan")
    return db, hashes


def test_incidents_status_open_exit_code_equals_open_count(tmp_path, capsys):
    db, _ = _setup_seed(tmp_path)
    rc = cli_main(["incidents", "--db", str(db), "--status", "open"])
    out = capsys.readouterr().out
    assert rc == 1  # exactly 1 still open
    # Each row of `--status open` carries `[open]`.
    assert out.count("[open]") == 1


def test_incidents_status_closed_lists_two(tmp_path, capsys):
    db, _ = _setup_seed(tmp_path)
    rc = cli_main(["incidents", "--db", str(db), "--status", "closed"])
    out = capsys.readouterr().out
    # Exit code is open count (still 1).
    assert rc == 1
    assert out.count("[closed]") == 2


def test_incidents_status_all_lists_three(tmp_path, capsys):
    db, _ = _setup_seed(tmp_path)
    cli_main(["incidents", "--db", str(db), "--status", "all"])
    out = capsys.readouterr().out
    # 3 incidents total.
    assert sum(line.count("[") for line in out.splitlines()) == 3


def test_incidents_default_summary_returns_open_count(tmp_path, capsys):
    db, _ = _setup_seed(tmp_path)
    rc = cli_main(["incidents", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "1 open" in out
    assert "2 closed" in out


def test_incidents_report_markdown_has_required_rows(tmp_path, capsys):
    db, _ = _setup_seed(tmp_path)
    rc = cli_main(["incidents", "--db", str(db), "--report", "--since", "1y"])
    out = capsys.readouterr().out
    assert rc == 0
    for marker in (
        "# Incidents report",
        "| Opened |",
        "| Closed |",
        "| MTTR |",
        "| P95 time-to-close |",
        "| Reopens |",
        "| Top closers |",
    ):
        assert marker in out


def test_incidents_report_requires_since(tmp_path, capsys):
    db, _ = _setup_seed(tmp_path)
    rc = cli_main(["incidents", "--db", str(db), "--report"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--since" in err


def test_incidents_missing_db_returns_2(tmp_path, capsys):
    rc = cli_main(["incidents", "--db", str(tmp_path / "nope.sqlite"), "--status", "all"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err
