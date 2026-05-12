"""Tests for PRD-v0.5 §2.3 storage/chain edge cases — Story 3.12.

Covers:
- AC1: BROKEN verify_state blocks subsequent chain-mode SQLHandler init.
- AC2: immutable_when raise → immutable=1 fail-safe + stderr message
       (regression of Story 3.6 implementation).
- AC3: tampered record_hash detected as BROKEN by `ulog verify`.
- AC4: min_retention_days violation → purge exit 1 (regression).
- AC5: `ulog repair --confirm` removes the BROKEN sidecar.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
from pathlib import Path

import pytest

import ulog
from ulog import _retention
from ulog._cli import main
from ulog._verify_state import read_verify_state, sidecar_path


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


def _seed_chain(tmp_path: Path, n: int = 5) -> Path:
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


def _corrupt_row(db: Path, chain_pos: int, *, target: str = "msg") -> None:
    """Tamper with `msg` (default) or `record_hash` to simulate corruption."""
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        if target == "msg":
            conn.execute(
                text("UPDATE logs SET msg='tampered' WHERE chain_pos=:p"),
                {"p": chain_pos},
            )
        elif target == "record_hash":
            conn.execute(
                text("UPDATE logs SET record_hash=:rh WHERE chain_pos=:p"),
                {"p": chain_pos, "rh": b"\x00" * 32},
            )
        else:
            raise ValueError(target)
    engine.dispose()


# ---- AC1: BROKEN blocks subsequent writes ---------------------------------


def test_broken_verify_state_blocks_chain_mode_setup(tmp_path, capsys):
    """AC1 — after verify writes BROKEN to the sidecar, attempting to
    re-open the SQLHandler in chain mode raises SchemaError."""
    from ulog.handlers.sql import SchemaError

    db = _seed_chain(tmp_path, n=5)
    _corrupt_row(db, chain_pos=3)
    main(["verify", str(db)])
    capsys.readouterr()
    assert read_verify_state(db)["status"] == "BROKEN"

    with pytest.raises(SchemaError, match="BROKEN"):
        ulog.setup(
            integrity="hash-chain",
            handlers=["sql"],
            sql_url=f"sqlite:///{db}",
            sql_batch_size=1,
        )


def test_broken_state_does_not_block_non_chain_setup(tmp_path, capsys):
    """AC1 (negative) — the block applies only to chain mode; opening
    the handler WITHOUT integrity='hash-chain' should still work."""
    db = _seed_chain(tmp_path, n=5)
    _corrupt_row(db, chain_pos=3)
    main(["verify", str(db)])
    capsys.readouterr()
    # Non-chain setup must NOT raise.
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)


# ---- AC2: immutable_when raise → fail-safe immutable=1 + stderr -----------


def test_immutable_when_raise_fail_safe_to_immutable_1(tmp_path, capsys):
    """AC2 — failing predicate → row gets immutable=1 (Decision B5)
    + one-shot stderr line tagged with 'Decision B5'."""
    from sqlalchemy import create_engine, text

    def boom(_r):
        raise RuntimeError("predicate crash")

    db = tmp_path / "boom.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(
        handlers=["sql"],
        sql_url=url,
        sql_batch_size=1,
        immutable_when=boom,
    )
    log = ulog.get_logger()
    log.info("a")
    log.info("b")
    for h in logging.getLogger().handlers:
        h.flush()
    captured = capsys.readouterr()
    assert "immutable_when callable raised" in captured.err
    assert "Decision B5" in captured.err
    # Exactly one line — one-shot.
    matched = [ln for ln in captured.err.splitlines() if "immutable_when" in ln]
    assert len(matched) == 1

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT immutable FROM logs ORDER BY id")).all()
    engine.dispose()
    assert [r[0] for r in rows] == [1, 1]


# ---- AC3: tampered record_hash → BROKEN ----------------------------------


def test_tampered_record_hash_reported_broken(tmp_path, capsys):
    """AC3 — write a row, then overwrite its stored record_hash with
    junk. `ulog verify` recomputes from canonical_record_json + prev
    and finds the mismatch. (Stand-in for the unfindable cryptographic
    hash-collision case.)"""
    db = _seed_chain(tmp_path, n=4)
    _corrupt_row(db, chain_pos=2, target="record_hash")
    rc = main(["verify", str(db)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "BROKEN at record #2" in out


# ---- AC4: min_retention violation regression -----------------------------


def test_min_retention_violation_via_purge_returns_exit_1(tmp_path, capsys):
    """AC4 — regression on Story 3.9: purge within retention floor → 1."""
    db = _seed_chain(tmp_path, n=1)
    _retention.MIN_RETENTION_DAYS = 365
    today = datetime.date.today().isoformat()
    rc = main(["purge", "--before", today, "--confirm", str(db)])
    capsys.readouterr()
    assert rc == 1


# ---- AC5: repair clears verify_state sidecar -----------------------------


def test_repair_clears_verify_state_sidecar(tmp_path, capsys):
    """AC5 — after a successful repair, the BROKEN sidecar is gone so
    subsequent chain-mode SQLHandler bootstraps don't refuse."""
    db = _seed_chain(tmp_path, n=5)
    _corrupt_row(db, chain_pos=3)
    main(["verify", str(db)])
    capsys.readouterr()
    assert sidecar_path(db).exists()
    assert read_verify_state(db)["status"] == "BROKEN"

    rc = main(["repair", "--confirm", str(db)])
    capsys.readouterr()
    assert rc == 0
    assert not sidecar_path(db).exists()

    # Re-bootstrap chain mode — must succeed (the block is lifted).
    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
    )
