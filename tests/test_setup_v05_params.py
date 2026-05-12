"""Tests for setup() v0.5 params — Story 3.6.

Covers `integrity='none'` alias, `immutable_when` callable, and
`min_retention_days` configuration surface (Story 3.9 reads it later).
"""

from __future__ import annotations

import contextlib
import logging

import pytest

import ulog
from ulog import _retention


@pytest.fixture(autouse=True)
def _isolate():
    """Clear bound state + handlers + reset retention config between tests."""
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


def _flush_all() -> None:
    for h in logging.getLogger().handlers:
        h.flush()


# ---- integrity='none' alias ----------------------------------------------


def test_integrity_none_string_alias_accepted():
    """AC1 — integrity='none' is a valid alias for None (non-chain)."""
    ulog.setup(integrity="none", handlers=["stream"])


def test_integrity_unknown_value_still_raises():
    """AC1 — non-recognised string still rejected."""
    with pytest.raises(ValueError, match="integrity"):
        ulog.setup(integrity="hashes")


def test_integrity_none_string_runs_v04_compatible_path(tmp_path):
    """AC6 — integrity='none' persists records with chain columns NULL
    (same as integrity=None / no chain mode)."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "none.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        integrity="none",
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
    )
    ulog.get_logger().info("plain")
    _flush_all()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT chain_pos, immutable, record_hash, prev_hash FROM logs WHERE msg='plain'")
        ).first()
    engine.dispose()
    assert row == (0, 0, None, None)


# ---- immutable_when ------------------------------------------------------


def test_immutable_when_marks_error_records_immutable(tmp_path):
    """AC2 — lambda r: r.levelno >= ERROR → ERROR rows persist with
    immutable=1, INFO rows with immutable=0."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "immut.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
        immutable_when=lambda r: r.levelno >= logging.ERROR,
    )
    log = ulog.get_logger()
    log.info("rotable")
    log.error("sealed")
    _flush_all()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT msg, immutable FROM logs ORDER BY id")).all()
    engine.dispose()
    assert rows == [("rotable", 0), ("sealed", 1)]


def test_immutable_when_works_in_chain_mode(tmp_path):
    """AC5 — chain mode + immutable_when → marked row has immutable=1
    AND chain link is still valid."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "chain_immut.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
        immutable_when=lambda r: r.levelno >= logging.ERROR,
    )
    log = ulog.get_logger()
    log.info("a")
    log.error("b")
    log.info("c")
    _flush_all()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT msg, immutable, record_hash, prev_hash, chain_pos "
                "FROM logs ORDER BY chain_pos"
            )
        ).all()
    engine.dispose()
    assert [r[0] for r in rows] == ["a", "b", "c"]
    assert [r[1] for r in rows] == [0, 1, 0]
    # Chain link integrity:
    assert bytes(rows[0][3]) == b"\x00" * 32
    assert bytes(rows[1][3]) == bytes(rows[0][2])
    assert bytes(rows[2][3]) == bytes(rows[1][2])


def test_immutable_when_callable_raising_falls_back_safe(tmp_path, capsys):
    """AC4 (Story 3.12 correction) — callable raises → row persists
    with immutable=1 (fail-safe per Decision B5; preserves forensic
    evidence). Stderr message fires ONCE per handler."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "raise.sqlite"
    url = f"sqlite:///{db}"

    def boom(_record):
        raise RuntimeError("callable bug")

    ulog.setup(
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
        immutable_when=boom,
    )
    log = ulog.get_logger()
    log.info("one")
    log.info("two")
    log.info("three")
    _flush_all()

    captured = capsys.readouterr()
    # Exactly one stderr line about immutable_when:
    err_lines = [ln for ln in captured.err.splitlines() if "immutable_when" in ln]
    assert len(err_lines) == 1, (
        f"expected exactly one stderr line, got {len(err_lines)}: {err_lines!r}"
    )
    assert "Decision B5" in err_lines[0]

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT immutable FROM logs ORDER BY id")).all()
    engine.dispose()
    # Fail-safe — all rows marked immutable.
    assert [r[0] for r in rows] == [1, 1, 1]


def test_immutable_trigger_blocks_update_on_immutable_when_marked_row(tmp_path):
    """AC5 (end-to-end) — immutable_when sets immutable=1; the Story
    3.2 trigger then blocks UPDATE attempts on that row."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError, OperationalError

    db = tmp_path / "block.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
        immutable_when=lambda r: r.levelno >= logging.ERROR,
    )
    log = ulog.get_logger()
    log.error("sealed")
    _flush_all()

    engine = create_engine(url, future=True)
    with (
        pytest.raises((IntegrityError, OperationalError)) as excinfo,
        engine.begin() as conn,
    ):
        conn.execute(text("UPDATE logs SET msg='tampered' WHERE msg='sealed'"))
    engine.dispose()
    assert "immutable row" in str(excinfo.value).lower()


# ---- min_retention_days --------------------------------------------------


def test_min_retention_days_stored_globally():
    """AC3 — setup() with min_retention_days writes the module attr."""
    assert _retention.MIN_RETENTION_DAYS == 0
    ulog.setup(min_retention_days=730, handlers=["stream"])
    assert _retention.MIN_RETENTION_DAYS == 730


def test_min_retention_days_negative_raises():
    """AC3 — negative value → ValueError."""
    with pytest.raises(ValueError, match="min_retention_days"):
        ulog.setup(min_retention_days=-1, handlers=["stream"])


def test_min_retention_days_string_raises():
    """AC3 — non-int (str) → TypeError."""
    with pytest.raises(TypeError, match="min_retention_days"):
        ulog.setup(min_retention_days="730", handlers=["stream"])  # type: ignore[arg-type]


def test_min_retention_days_bool_rejected():
    """AC3 — bool subclass of int → TypeError (avoid accidental True
    being interpreted as 1 day)."""
    with pytest.raises(TypeError, match="min_retention_days"):
        ulog.setup(min_retention_days=True, handlers=["stream"])  # type: ignore[arg-type]


def test_min_retention_days_none_or_omitted_keeps_existing():
    """AC3 — omitted (or None) does NOT overwrite an existing value."""
    _retention.MIN_RETENTION_DAYS = 365
    ulog.setup(handlers=["stream"])
    assert _retention.MIN_RETENTION_DAYS == 365
    ulog.setup(min_retention_days=None, handlers=["stream"])
    assert _retention.MIN_RETENTION_DAYS == 365
