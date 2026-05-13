"""Tests for PRD-v0.13 — local fix database."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog
from ulog._cli import main as cli_main
from ulog._fixes import canonical_msg, fixes_db_path, lookup_fix, signature


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


# ---- signature + canonical_msg ------------------------------------------


def test_canonical_msg_strips_numbers_and_hex():
    # Hex (6+ chars) → H, digits → N. Order: hex first.
    assert canonical_msg("req_abc123 failed in 250ms") == "req_H failed in Nms"
    # Two hex-shaped IDs collapse to the same canonical form.
    assert canonical_msg("req_a1b2c3 in 100ms") == canonical_msg("req_abcdef in 200ms")


def test_signature_stable_for_same_canonical_msg():
    # 'abc123' / 'def456' both hex-shaped → both reduce to 'H'.
    assert signature("req_abc123 failed") == signature("req_def456 failed")


def test_signature_changes_with_stack():
    s1 = signature("boom", stack=[{"file": "a.py", "function": "f"}])
    s2 = signature("boom", stack=[{"file": "b.py", "function": "g"}])
    assert s1 != s2


def test_signature_falls_back_to_msg_only_without_stack():
    assert signature("boom") == signature("boom", stack=None)


# ---- resolve / lookup / list / unresolve --------------------------------


def _seed(tmp_path: Path, msg: str = "boom") -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().error(msg)
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_resolve_creates_sidecar(tmp_path):
    db = _seed(tmp_path)
    rc = cli_main(
        [
            "fix",
            "resolve",
            "--db",
            str(db),
            "--record-id",
            "1",
            "--writeup",
            "restarted db pool",
            "--by",
            "Johan",
        ]
    )
    assert rc == 0
    assert fixes_db_path(db).exists()


def test_lookup_after_resolve(tmp_path):
    db = _seed(tmp_path, "checkout timeout 4523ms")
    cli_main(
        [
            "fix",
            "resolve",
            "--db",
            str(db),
            "--record-id",
            "1",
            "--writeup",
            "increased timeout to 10s",
            "--by",
            "Johan",
        ]
    )
    sig = signature("checkout timeout 4523ms")
    entry = lookup_fix(db, sig)
    assert entry is not None
    assert entry["by"] == "Johan"


def test_list_command(tmp_path, capsys):
    db = _seed(tmp_path)
    cli_main(
        [
            "fix",
            "resolve",
            "--db",
            str(db),
            "--record-id",
            "1",
            "--writeup",
            "wp",
            "--by",
            "x",
        ]
    )
    rc = cli_main(["fix", "list", "--db", str(db)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wp" in out


def test_show_command(tmp_path, capsys):
    db = _seed(tmp_path)
    cli_main(
        [
            "fix",
            "resolve",
            "--db",
            str(db),
            "--record-id",
            "1",
            "--writeup",
            "detailed writeup",
            "--by",
            "x",
        ]
    )
    sig = signature("boom")
    rc = cli_main(["fix", "show", "--db", str(db), sig])
    assert rc == 0
    out = capsys.readouterr().out
    assert "detailed writeup" in out
    assert "by: x" in out


def test_show_missing_signature_returns_1(tmp_path, capsys):
    db = _seed(tmp_path)
    rc = cli_main(["fix", "show", "--db", str(db), "0" * 64])
    assert rc == 1


def test_unresolve_drops_entry(tmp_path):
    db = _seed(tmp_path)
    cli_main(
        [
            "fix",
            "resolve",
            "--db",
            str(db),
            "--record-id",
            "1",
            "--writeup",
            "wp",
            "--by",
            "x",
        ]
    )
    sig = signature("boom")
    assert lookup_fix(db, sig) is not None
    rc = cli_main(["fix", "unresolve", "--db", str(db), sig])
    assert rc == 0
    assert lookup_fix(db, sig) is None


def test_unresolve_missing_returns_1(tmp_path):
    db = _seed(tmp_path)
    rc = cli_main(["fix", "unresolve", "--db", str(db), "0" * 64])
    assert rc == 1


def test_resolve_without_record_or_signature_returns_2(tmp_path):
    db = _seed(tmp_path)
    rc = cli_main(
        ["fix", "resolve", "--db", str(db), "--writeup", "x", "--by", "y"]
    )
    assert rc == 2


def test_resolve_with_explicit_signature(tmp_path):
    db = _seed(tmp_path)
    custom_sig = "f" * 64
    cli_main(
        [
            "fix",
            "resolve",
            "--db",
            str(db),
            "--signature",
            custom_sig,
            "--writeup",
            "wp",
            "--by",
            "y",
        ]
    )
    assert lookup_fix(db, custom_sig) is not None
