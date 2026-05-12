"""Tests for `ulog.replay_to_pytest` — Story 4.3."""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
from pathlib import Path

import pytest

import ulog


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


def _seed_chain(tmp_path: Path, n: int = 3) -> Path:
    db = tmp_path / "src.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=url, sql_batch_size=1)
    log = ulog.get_logger("svc.checkout")
    levels = ["INFO", "WARNING", "ERROR"]
    for i in range(n):
        getattr(log, levels[i % 3].lower())("rec %d", i, extra={"db_timeout": i == 2})
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


# ---- file structure -----------------------------------------------------


def test_generated_file_is_valid_python(tmp_path):
    db = _seed_chain(tmp_path, n=3)
    out = tmp_path / "test_inc.py"
    ulog.replay_to_pytest(db, output_path=out, incident_hash="abc123def456")
    content = out.read_text(encoding="utf-8")
    # Compile must succeed.
    compile(content, str(out), "exec")


def test_generated_file_contains_required_imports(tmp_path):
    db = _seed_chain(tmp_path, n=2)
    out = tmp_path / "test_inc.py"
    ulog.replay_to_pytest(db, output_path=out, incident_hash="abc")
    content = out.read_text(encoding="utf-8")
    assert "import pytest" in content
    assert "from ulog.testing import replay_records" in content


def test_generated_file_contains_incident_records_list(tmp_path):
    db = _seed_chain(tmp_path, n=2)
    out = tmp_path / "test_inc.py"
    n = ulog.replay_to_pytest(db, output_path=out, incident_hash="abc")
    content = out.read_text(encoding="utf-8")
    assert "INCIDENT_RECORDS = [" in content
    assert n == 2


def test_generated_file_has_test_function_with_replay_records_block(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    out = tmp_path / "test_inc.py"
    ulog.replay_to_pytest(db, output_path=out, incident_hash="aaaa", topic="dbtimeout")
    content = out.read_text(encoding="utf-8")
    assert "def test_incident_aaaa_dbtimeout():" in content
    assert "with replay_records(INCIDENT_RECORDS) as session:" in content


def test_returns_count_of_records_snapshotted(tmp_path):
    db = _seed_chain(tmp_path, n=5)
    out = tmp_path / "test_inc.py"
    n = ulog.replay_to_pytest(db, output_path=out, incident_hash="x")
    assert n == 5


# ---- record serialisation ------------------------------------------------


def test_records_are_slim_form_no_bytes_no_chain_pos(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    out = tmp_path / "test_inc.py"
    ulog.replay_to_pytest(db, output_path=out, incident_hash="x")
    content = out.read_text(encoding="utf-8")
    # No raw bytes (b'\x...') and no chain_pos / record_hash / prev_hash keys.
    assert "record_hash" not in content
    assert "prev_hash" not in content
    assert "chain_pos" not in content
    assert "is_replay" not in content


def test_ts_serialized_as_iso_string(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    out = tmp_path / "test_inc.py"
    ulog.replay_to_pytest(db, output_path=out, incident_hash="x")
    content = out.read_text(encoding="utf-8")
    # ISO format has a `T` separator + 4-digit year.
    import re

    assert re.search(r"'ts': '20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", content)


# ---- overwrite semantics -------------------------------------------------


def test_existing_file_without_force_raises_fileexistserror(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    out = tmp_path / "test_inc.py"
    out.write_text("# pre-existing\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="force=True"):
        ulog.replay_to_pytest(db, output_path=out, incident_hash="x")


def test_existing_file_with_force_overwrites(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    out = tmp_path / "test_inc.py"
    out.write_text("# pre-existing\n", encoding="utf-8")
    ulog.replay_to_pytest(db, output_path=out, incident_hash="x", force=True)
    content = out.read_text(encoding="utf-8")
    assert "# pre-existing" not in content
    assert "from ulog.testing import replay_records" in content


# ---- slug normalisation --------------------------------------------------


def test_filename_slug_normalises_hash(tmp_path):
    """incident_hash='A3F7-C12@' → only 'a3f7c12' kept (hex chars only,
    lowercase, max 12 chars)."""
    db = _seed_chain(tmp_path, n=1)
    out = tmp_path / "test_inc.py"
    ulog.replay_to_pytest(db, output_path=out, incident_hash="A3F7-C12@")
    content = out.read_text(encoding="utf-8")
    assert "test_incident_a3f7c12_incident" in content


def test_topic_appended_to_test_function_name(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    out = tmp_path / "test_inc.py"
    ulog.replay_to_pytest(db, output_path=out, incident_hash="deadbeef", topic="payment-timeout")
    content = out.read_text(encoding="utf-8")
    # Non-alphanum chars in topic become underscores.
    assert "def test_incident_deadbeef_payment_timeout():" in content


def test_auto_hash_when_empty(tmp_path):
    """incident_hash='' → sha256 of (db_path, where, where_fn) used."""
    db = _seed_chain(tmp_path, n=1)
    out = tmp_path / "test_inc.py"
    ulog.replay_to_pytest(db, output_path=out)
    content = out.read_text(encoding="utf-8")
    # Some 12-char hex string in the function name.
    import re

    assert re.search(r"def test_incident_[0-9a-f]{12}_incident\(\):", content)


# ---- end-to-end: generated file runs cleanly ----------------------------


def test_generated_file_runs_pytest_clean(tmp_path):
    """The stubbed test passes by default (placeholder assertion)."""
    db = _seed_chain(tmp_path, n=2)
    out = tmp_path / "test_generated_inc.py"
    ulog.replay_to_pytest(db, output_path=out, incident_hash="abc")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(out), "-q", "--no-header"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "1 passed" in result.stdout
