"""Story 3.11 — concurrency stress: 8 procs x 10K records.

Marked `slow` so the fast suite skips it. Run with `pytest -m slow`
(or `pytest tests/test_chain_concurrency.py`) before tagging v0.5.0.

NFR-REL-50 — chain integrity must hold under real multi-process
contention serialised by SQLite WAL + BEGIN IMMEDIATE (wired by
Stories 3.4 + 3.5).
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import textwrap
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


_WORKER_SCRIPT = textwrap.dedent(
    """
    import logging, sys
    import ulog

    worker_id = int(sys.argv[1])
    db_url = sys.argv[2]
    ulog.setup(
        integrity='hash-chain',
        handlers=['sql'],
        sql_url=db_url,
        sql_batch_size=1,
    )
    log = ulog.get_logger()
    for i in range(10000):
        log.info("w%d-%d", worker_id, i)
    for h in logging.getLogger().handlers:
        h.flush()
    """
)


@pytest.mark.slow
def test_8_writers_10k_records_chain_unbroken(tmp_path: Path, capsys):
    """AC1+AC2 — 8 subprocesses x 10K records -> 80K rows + chain OK."""
    db = tmp_path / "stress.sqlite"
    url = f"sqlite:///{db}"

    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _WORKER_SCRIPT, str(i), url],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
        for i in range(8)
    ]
    for p in procs:
        _stdout, stderr = p.communicate(timeout=180)
        # No 'database is locked' noise should escape.
        if stderr:
            stderr_s = stderr.decode("utf-8", errors="replace")
            assert "database is locked" not in stderr_s.lower(), stderr_s
        assert p.returncode == 0, f"worker exited {p.returncode}; stderr={stderr!r}"

    # End-to-end chain verify must report OK with records=80000.
    rc = main(["verify", str(db)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "records: 80000" in out, out
