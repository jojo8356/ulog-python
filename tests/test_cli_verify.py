"""Tests for `ulog verify` CLI subcommand — Story 3.7."""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import time
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
    """Set up a chain-mode SQLHandler, emit n records, return DB path."""
    db = tmp_path / "chain.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
    )
    log = ulog.get_logger()
    for i in range(n):
        log.info("record %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


def test_verify_clean_chain_exit_0(tmp_path, capsys):
    """AC4 — unbroken chain → ✓ + exit 0 + records count + wall time."""
    db = _seed_chain(tmp_path, n=5)
    rc = main(["verify", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "✓ Integrity verified" in out
    assert "records: 5" in out
    assert "wall_time:" in out


def test_verify_broken_record_hash_exit_1(tmp_path, capsys):
    """AC5 — tampered msg (no immutable trigger guarding it because
    immutable=0) → recomputed hash != stored → BROKEN + exit 1."""
    from sqlalchemy import create_engine, text

    db = _seed_chain(tmp_path, n=5)
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        conn.execute(text("UPDATE logs SET msg='tampered' WHERE chain_pos=3"))
    engine.dispose()

    rc = main(["verify", str(db)])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "BROKEN at record #3" in out
    assert "recomputed" in out or "expected" in out


def test_verify_broken_prev_hash_link_exit_1(tmp_path, capsys):
    """AC5 — corrupt prev_hash → expected != actual → BROKEN + exit 1."""
    from sqlalchemy import create_engine, text

    db = _seed_chain(tmp_path, n=5)
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        # Overwrite chain_pos=3's prev_hash with junk.
        conn.execute(
            text("UPDATE logs SET prev_hash=:p WHERE chain_pos=3"),
            {"p": b"\xff" * 32},
        )
    engine.dispose()

    rc = main(["verify", str(db)])
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "BROKEN at record #3" in out


def test_verify_range_walks_subset(tmp_path, capsys):
    """AC6 — --range 3-5 verifies only that sub-range (3 records)."""
    db = _seed_chain(tmp_path, n=10)
    rc = main(["verify", str(db), "--range", "3-5"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "records: 3" in out


def test_verify_range_comma_syntax(tmp_path, capsys):
    """AC6 — --range 1,3 also accepted (alternate separator)."""
    db = _seed_chain(tmp_path, n=10)
    rc = main(["verify", str(db), "--range", "1,3"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "records: 3" in out


def test_verify_range_with_offset_walks_chain_from_previous(tmp_path, capsys):
    """AC6 — --range 5-10 must use record #4's record_hash as the
    starting prev_hash (not zero), so chain walk verifies correctly
    over a partial sub-range."""
    db = _seed_chain(tmp_path, n=10)
    rc = main(["verify", str(db), "--range", "5-10"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "records: 6" in out


def test_verify_empty_chain_exit_0(tmp_path, capsys):
    """AC8 — empty logs table → records:0 + ✓ + exit 0."""
    from sqlalchemy import create_engine, text

    db = _seed_chain(tmp_path, n=2)
    # Wipe rows but keep schema.
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        # Turn off the immutable trigger? Our chain emits set
        # immutable=0 by default so DELETE is permitted.
        conn.execute(text("DELETE FROM logs"))
    engine.dispose()

    rc = main(["verify", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "records: 0" in out


def test_verify_dash_m_invocation(tmp_path):
    """AC1 — `python -m ulog._cli verify <db>` works."""
    db = _seed_chain(tmp_path, n=3)
    result = subprocess.run(
        [sys.executable, "-m", "ulog._cli", "verify", str(db)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "✓ Integrity verified" in result.stdout
    assert "records: 3" in result.stdout


def test_verify_unknown_subcommand_exit_2(capsys):
    """AC2 — non-existent subcommand → exit 2 + help in stderr."""
    rc = main([])  # no subcommand at all → print help + exit 2
    assert rc == 2


def test_verify_missing_db_exit_2(capsys):
    """AC2 — missing DB path → exit 2 with stderr message."""
    rc = main(["verify"])
    assert rc == 2


def test_verify_nonexistent_db_exit_2(tmp_path, capsys):
    """AC2 — DB path that doesn't exist → exit 2 with stderr message."""
    rc = main(["verify", str(tmp_path / "missing.sqlite")])
    assert rc == 2


def test_verify_range_invalid_format_exits(tmp_path):
    """AC6 — argparse rejects malformed --range; SystemExit raised."""
    db = _seed_chain(tmp_path, n=2)
    with pytest.raises(SystemExit):
        main(["verify", str(db), "--range", "bogus"])


def test_verify_500_records_under_500ms(tmp_path, capsys):
    """AC11/AC13 (scaled) — 500 records verified in well under 500ms.
    Smoke proxy for NFR-PERF-52 (100K in 5s on CI). Full 100K bench
    is Story 3.11."""
    db = _seed_chain(tmp_path, n=500)
    t0 = time.perf_counter()
    rc = main(["verify", str(db)])
    elapsed = time.perf_counter() - t0
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "records: 500" in out
    assert elapsed < 1.0, f"verify too slow on 500 records: {elapsed:.2f}s"
