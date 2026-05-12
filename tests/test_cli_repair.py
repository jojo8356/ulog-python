"""Tests for `ulog repair --confirm` CLI subcommand — Story 3.8."""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import sys
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


def _seed_chain(tmp_path: Path, n: int = 5, immutable_when=None) -> Path:
    db = tmp_path / "chain.sqlite"
    url = f"sqlite:///{db}"
    kwargs = {
        "integrity": "hash-chain",
        "handlers": ["sql"],
        "sql_url": url,
        "sql_batch_size": 1,
    }
    if immutable_when is not None:
        kwargs["immutable_when"] = immutable_when
    ulog.setup(**kwargs)
    log = ulog.get_logger()
    for i in range(n):
        log.info("rec%d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


def _corrupt_row(db: Path, chain_pos: int) -> None:
    """Set msg='tampered' on the given chain_pos (assumes immutable=0)."""
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE logs SET msg='tampered' WHERE chain_pos=:p"),
            {"p": chain_pos},
        )
    engine.dispose()


def _count_rows(db: Path) -> int:
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM logs")).scalar_one()
    engine.dispose()
    return int(n)


# ---- argparse + confirm gating -------------------------------------------


def test_repair_without_confirm_refuses(tmp_path, capsys):
    """AC1 — repair without --confirm → exit 2 + warning to stderr."""
    db = _seed_chain(tmp_path, n=3)
    rc = main(["repair", str(db)])
    out = capsys.readouterr()
    assert rc == 2, out.out + out.err
    assert "--confirm" in out.err


def test_repair_missing_db_exit_2(capsys):
    rc = main(["repair", "--confirm"])
    assert rc == 2


def test_repair_nonexistent_db_exit_2(tmp_path):
    rc = main(["repair", "--confirm", str(tmp_path / "nope.sqlite")])
    assert rc == 2


# ---- happy / no-op paths -------------------------------------------------


def test_repair_healthy_chain_is_noop(tmp_path, capsys):
    """AC2 — healthy chain → no sidecar, no deletes, exit 0."""
    db = _seed_chain(tmp_path, n=5)
    before = _count_rows(db)
    rc = main(["repair", "--confirm", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "healthy" in out.lower()
    assert _count_rows(db) == before
    # No sidecar created.
    sidecars = list(tmp_path.glob("*chain_break*.log"))
    assert sidecars == []


def test_repair_idempotent_after_success(tmp_path, capsys):
    """AC5 — running repair twice on a now-healed DB is a no-op."""
    db = _seed_chain(tmp_path, n=5)
    _corrupt_row(db, chain_pos=3)
    rc1 = main(["repair", "--confirm", str(db)])
    capsys.readouterr()  # discard first-run output
    assert rc1 == 0
    rc2 = main(["repair", "--confirm", str(db)])
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert "healthy" in out2.lower()


# ---- broken chain → archive + delete -------------------------------------


def test_repair_broken_chain_archives_and_deletes(tmp_path, capsys):
    """AC3 — orphans (rows from break onwards) land in sidecar JSONL
    AND get deleted from live DB."""
    db = _seed_chain(tmp_path, n=5)
    _corrupt_row(db, chain_pos=3)
    rc = main(["repair", "--confirm", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "archived 3 orphans" in out  # rows 3, 4, 5

    sidecars = list(tmp_path.glob("*chain_break*.log"))
    assert len(sidecars) == 1
    lines = sidecars[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    # Live DB keeps only rows 1-2.
    assert _count_rows(db) == 2


def test_repair_sidecar_jsonl_format(tmp_path, capsys):
    """AC6 — each sidecar line parses as JSON and contains the
    expected keys + hex hashes."""
    db = _seed_chain(tmp_path, n=5)
    _corrupt_row(db, chain_pos=3)
    main(["repair", "--confirm", str(db)])
    capsys.readouterr()
    sidecar = next(tmp_path.glob("*chain_break*.log"))
    lines = sidecar.read_text(encoding="utf-8").strip().splitlines()
    for line in lines:
        rec = json.loads(line)
        for key in (
            "chain_pos",
            "ts",
            "level",
            "logger",
            "msg",
            "file",
            "line",
            "immutable",
            "record_hash",
            "prev_hash",
        ):
            assert key in rec, f"missing {key!r} in sidecar line: {rec!r}"
        assert isinstance(rec["record_hash"], str)
        assert len(rec["record_hash"]) == 64  # sha256 hex


# ---- immutable-orphan refusal --------------------------------------------


def test_repair_refuses_immutable_orphan(tmp_path, capsys):
    """AC4 — an orphan with immutable=1 → exit 1, message mentions I4,
    no sidecar, no deletes."""
    # Mark ERROR records immutable; corrupt one INFO; the broken
    # range includes the immutable ERROR → repair refuses.
    db_path = tmp_path / "chain.sqlite"
    url = f"sqlite:///{db_path}"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
        immutable_when=lambda r: r.levelno >= logging.ERROR,
    )
    log = ulog.get_logger()
    log.info("rec1")
    log.info("rec2")
    log.error("seal3")  # immutable=1
    log.info("rec4")
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)

    # Corrupt rec2 — break starts at chain_pos=2; the orphan range
    # includes the immutable ERROR at chain_pos=3.
    _corrupt_row(db_path, chain_pos=2)

    before = _count_rows(db_path)
    rc = main(["repair", "--confirm", str(db_path)])
    out = capsys.readouterr()
    assert rc == 1, out.out + out.err
    assert "immutable orphan" in out.err.lower()
    assert "I4" in out.err
    # No sidecar, no deletes.
    assert _count_rows(db_path) == before
    assert list(tmp_path.glob("*chain_break*.log")) == []


# ---- subprocess invocation -----------------------------------------------


def test_repair_python_m_invocation(tmp_path):
    """AC8 — python -m ulog._cli repair --confirm works."""
    db = _seed_chain(tmp_path, n=3)
    result = subprocess.run(
        [sys.executable, "-m", "ulog._cli", "repair", "--confirm", str(db)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "healthy" in result.stdout.lower()
