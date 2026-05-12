"""Tests for the `<db>.verify_state.json` sidecar — Story 3.10."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path

import pytest

import ulog
from ulog._cli import main
from ulog._verify_state import read_verify_state, sidecar_path


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


def _corrupt_row(db: Path, chain_pos: int) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE logs SET msg='tampered' WHERE chain_pos=:p"),
            {"p": chain_pos},
        )
    engine.dispose()


# ---- read helper -------------------------------------------------


def test_read_verify_state_returns_none_when_missing(tmp_path):
    """AC3 — missing sidecar → None (no crash)."""
    db = tmp_path / "no_such.sqlite"
    db.touch()  # exists but no sidecar
    assert read_verify_state(db) is None


# ---- OK / BROKEN sidecars ---------------------------------------


def test_verify_writes_ok_sidecar_on_healthy_chain(tmp_path, capsys):
    """AC1 — OK walk → sidecar with status=OK + verified_up_to=N."""
    db = _seed_chain(tmp_path, n=5)
    rc = main(["verify", str(db)])
    capsys.readouterr()
    assert rc == 0
    state = read_verify_state(db)
    assert state is not None
    assert state["status"] == "OK"
    assert state["broken_at"] is None
    assert state["verified_up_to_chain_pos"] == 5
    assert "last_check_ts" in state
    assert isinstance(state["walk_time_s"], float)


def test_verify_writes_broken_sidecar_on_break(tmp_path, capsys):
    """AC2 — BROKEN → sidecar with status=BROKEN + broken_at +
    verified_up_to=last_good_pos."""
    db = _seed_chain(tmp_path, n=5)
    _corrupt_row(db, chain_pos=3)
    rc = main(["verify", str(db)])
    capsys.readouterr()
    assert rc == 1
    state = read_verify_state(db)
    assert state is not None
    assert state["status"] == "BROKEN"
    assert state["broken_at"] == 3
    # rows 1+2 verified before break; verified_up_to = 2
    assert state["verified_up_to_chain_pos"] == 2


def test_verify_state_keys_present(tmp_path, capsys):
    """AC1 — payload includes the documented schema fields."""
    db = _seed_chain(tmp_path, n=3)
    main(["verify", str(db)])
    capsys.readouterr()
    state = read_verify_state(db)
    assert state is not None
    for key in (
        "version",
        "status",
        "broken_at",
        "verified_up_to_chain_pos",
        "last_check_ts",
        "walk_time_s",
    ):
        assert key in state, f"missing {key!r} in verify_state: {state!r}"
    assert state["version"] == 1


def test_verify_range_does_NOT_write_sidecar(tmp_path, capsys):
    """AC5 — --range partial walks must NOT write the sidecar."""
    db = _seed_chain(tmp_path, n=5)
    rc = main(["verify", str(db), "--range", "2-3"])
    capsys.readouterr()
    assert rc == 0
    assert not sidecar_path(db).exists()


def test_verify_state_sidecar_atomic_write(tmp_path, capsys):
    """AC6 — after a successful verify, the tmp file is gone."""
    db = _seed_chain(tmp_path, n=3)
    main(["verify", str(db)])
    capsys.readouterr()
    # The .verify_state.json.tmp leftover would mean a torn write.
    tmp = sidecar_path(db).with_suffix(sidecar_path(db).suffix + ".tmp")
    assert not tmp.exists()
    assert sidecar_path(db).exists()


def test_verify_state_overwrites_on_re_run(tmp_path, capsys):
    """The sidecar reflects the LATEST walk — re-run on a broken DB
    overwrites the OK state with BROKEN."""
    db = _seed_chain(tmp_path, n=5)
    main(["verify", str(db)])
    capsys.readouterr()
    assert read_verify_state(db)["status"] == "OK"

    _corrupt_row(db, chain_pos=2)
    main(["verify", str(db)])
    capsys.readouterr()
    state = read_verify_state(db)
    assert state["status"] == "BROKEN"
    assert state["broken_at"] == 2


def test_sidecar_path_helper(tmp_path):
    """`sidecar_path(<db>.sqlite)` -> `<db>.verify_state.json`."""
    db = tmp_path / "logs.sqlite"
    p = sidecar_path(db)
    assert p.name == "logs.verify_state.json"
    assert p.parent == tmp_path


def test_verify_state_json_is_valid_json(tmp_path, capsys):
    """The file written is parsable as JSON (sanity)."""
    db = _seed_chain(tmp_path, n=2)
    main(["verify", str(db)])
    capsys.readouterr()
    raw = sidecar_path(db).read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert isinstance(payload, dict)
