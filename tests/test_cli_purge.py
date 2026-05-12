"""Tests for `ulog purge --before <date>` — Story 3.9."""

from __future__ import annotations

import contextlib
import datetime
import logging
import subprocess
import sys
from pathlib import Path

import pytest

import ulog
from ulog import _retention
from ulog._cli import main


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    _retention.MIN_RETENTION_DAYS = 0
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()
    _retention.MIN_RETENTION_DAYS = 0


def _seed_db(tmp_path: Path) -> Path:
    """Schema-only — tests insert rows directly via SQL so they can
    control ts + immutable + record_hash explicitly."""
    db = tmp_path / "purge.sqlite"
    url = f"sqlite:///{db}"
    from ulog.handlers.sql import SQLHandler

    h = SQLHandler(url=url, batch_size=1)
    h._ensure_schema()
    h.close()
    return db


def _insert_row(
    db: Path,
    *,
    ts: datetime.datetime,
    immutable: int = 0,
    record_hash: bytes | None = None,
    msg: str = "x",
) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO logs (ts, level, logger, msg, file, line, "
                "immutable, chain_pos, record_hash) "
                "VALUES (:ts, 'INFO', 'test', :msg, 'f.py', 1, "
                ":immut, 0, :rh)"
            ),
            {
                "ts": ts,
                "msg": msg,
                "immut": immutable,
                "rh": record_hash,
            },
        )
    engine.dispose()


def _count(db: Path) -> int:
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM logs")).scalar_one()
    engine.dispose()
    return int(n)


# ---- argparse -------------------------------------------------------------


def test_purge_invalid_date_format_exits_2(tmp_path):
    db = _seed_db(tmp_path)
    with pytest.raises(SystemExit):
        main(["purge", "--before", "2024/06/01", str(db)])


def test_purge_missing_db_exit_2():
    rc = main(["purge", "--before", "2024-06-01"])
    assert rc == 2


def test_purge_nonexistent_db_exit_2(tmp_path):
    rc = main(["purge", "--before", "2024-06-01", str(tmp_path / "nope.sqlite")])
    assert rc == 2


# ---- happy paths ---------------------------------------------------------


def test_purge_before_drops_old_rotable_rows(tmp_path, capsys):
    """AC1 — rotable rows with ts < --before are deleted."""
    db = _seed_db(tmp_path)
    _insert_row(db, ts=datetime.datetime(2024, 1, 1), msg="old")
    _insert_row(db, ts=datetime.datetime(2024, 1, 2), msg="old2")
    assert _count(db) == 2

    rc = main(["purge", "--before", "2024-06-01", "--confirm", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "2 rotable rows" in out
    assert _count(db) == 0


def test_purge_keeps_recent_rotable_rows(tmp_path, capsys):
    """AC1 — rotable rows with ts >= --before are kept."""
    db = _seed_db(tmp_path)
    _insert_row(db, ts=datetime.datetime(2024, 1, 1), msg="old")
    _insert_row(db, ts=datetime.datetime(2025, 1, 1), msg="new")
    rc = main(["purge", "--before", "2024-06-01", "--confirm", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert _count(db) == 1


def test_purge_keeps_immutable_rows_even_if_old(tmp_path, capsys):
    """AC2 / I4 — immutable rows are excluded from the DELETE."""
    db = _seed_db(tmp_path)
    _insert_row(db, ts=datetime.datetime(2024, 1, 1), immutable=1, msg="sealed")
    _insert_row(db, ts=datetime.datetime(2024, 1, 2), immutable=0, msg="rotable")
    rc = main(["purge", "--before", "2024-06-01", "--confirm", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "1 rotable rows" in out
    assert _count(db) == 1  # sealed survived


def test_purge_pre_chain_null_hash_rows_treated_as_rotable(tmp_path, capsys):
    """AC5 / Gap G8 — record_hash IS NULL rows count as rotable (and
    are dropped when old)."""
    db = _seed_db(tmp_path)
    _insert_row(db, ts=datetime.datetime(2024, 1, 1), record_hash=None, msg="pre-chain")
    rc = main(["purge", "--before", "2024-06-01", "--confirm", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "1 rotable rows" in out
    assert _count(db) == 0


# ---- dry-run / no-confirm ------------------------------------------------


def test_purge_dry_run_does_not_delete(tmp_path, capsys):
    """AC6 — --dry-run counts but does not delete."""
    db = _seed_db(tmp_path)
    _insert_row(db, ts=datetime.datetime(2024, 1, 1))
    _insert_row(db, ts=datetime.datetime(2024, 1, 2))
    rc = main(["purge", "--before", "2024-06-01", "--dry-run", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "(dry-run)" in out
    assert "2 rotable rows would be deleted" in out
    assert _count(db) == 2


def test_purge_without_confirm_is_dry_run(tmp_path, capsys):
    """AC7 — without --confirm, behaves like --dry-run."""
    db = _seed_db(tmp_path)
    _insert_row(db, ts=datetime.datetime(2024, 1, 1))
    rc = main(["purge", "--before", "2024-06-01", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "(dry-run)" in out
    assert _count(db) == 1


# ---- min_retention_days floor --------------------------------------------


def test_purge_min_retention_floor_refuses_when_too_recent(tmp_path, capsys):
    """AC3 / FR92 — purging within the retention floor → exit 1."""
    db = _seed_db(tmp_path)
    _retention.MIN_RETENTION_DAYS = 365
    # --before is today (well within 365 days from now).
    today = datetime.date.today().isoformat()
    rc = main(["purge", "--before", today, "--confirm", str(db)])
    out = capsys.readouterr()
    assert rc == 1
    assert "retention floor" in out.err.lower()


def test_purge_min_retention_floor_allows_when_safe(tmp_path, capsys):
    """AC3 — purge with --before older than today - floor is fine."""
    db = _seed_db(tmp_path)
    _retention.MIN_RETENTION_DAYS = 30
    far_before = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
    rc = main(["purge", "--before", far_before, "--confirm", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out


# ---- idempotency + subprocess --------------------------------------------


def test_purge_is_idempotent_after_clean(tmp_path, capsys):
    """AC8 — re-purge on already-clean DB → 0 rows."""
    db = _seed_db(tmp_path)
    _insert_row(db, ts=datetime.datetime(2024, 1, 1))
    main(["purge", "--before", "2024-06-01", "--confirm", str(db)])
    capsys.readouterr()
    rc = main(["purge", "--before", "2024-06-01", "--confirm", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "0 rotable rows" in out


def test_purge_python_m_invocation(tmp_path):
    db = _seed_db(tmp_path)
    _insert_row(db, ts=datetime.datetime(2024, 1, 1))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ulog._cli",
            "purge",
            "--before",
            "2024-06-01",
            "--confirm",
            str(db),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "1 rotable rows" in result.stdout
