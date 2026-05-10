"""End-to-end tests automating section §0 (Setup) of the QA checklist.

Replaces the manual checks:
- Script seed_demo_db.py runs without error
- DB has substantive size
- Stderr shows author-indexer progress lines
- No stack trace at startup
- Forgetting `--repo` from a non-git cwd produces the documented warning

Spawns real subprocesses (seed + viewer) so the assertions match the
exact user experience. Each viewer subprocess is bounded in wall-time
and torn down even on failure.
"""
from __future__ import annotations

import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


# ---- helpers --------------------------------------------------------------


def _free_port() -> int:
    """Grab a free localhost port from the OS (race window between bind and use is acceptable for tests)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn_viewer(args: list[str], *, cwd: Path | None = None) -> subprocess.Popen:
    """Launch `python -m ulog.web.cli ...` with stderr captured."""
    return subprocess.Popen(
        [sys.executable, "-m", "ulog.web.cli", *args],
        cwd=str(cwd) if cwd else None,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )


def _wait_then_capture_stderr(proc: subprocess.Popen, *, settle_s: float = 6.0) -> str:
    """Let the viewer settle, then terminate it and read all stderr."""
    try:
        time.sleep(settle_s)
        proc.terminate()
        try:
            _, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate()
        return stderr
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


# ---- fixtures -------------------------------------------------------------


@pytest.fixture(scope="module")
def seeded_demo(tmp_path_factory) -> Path:
    """Run the seed script once per test module. Smaller params for speed."""
    demo_dir = tmp_path_factory.mktemp("ulog-qa-demo")
    seed_script = REPO_ROOT / "scripts" / "seed_demo_db.py"
    proc = subprocess.run(
        [sys.executable, str(seed_script), str(demo_dir),
         "--records", "5000", "--test-files", "3", "--tests-per-file", "10"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, (
        f"seed script failed (exit {proc.returncode}):\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    return demo_dir


# ---- §0.1 + §0.2 — seed script + DB size ---------------------------------


def test_seed_script_creates_repo_and_db(seeded_demo):
    """§0 AC1: script runs without error and produces both artifacts."""
    assert (seeded_demo / "logs.sqlite").exists(), "logs.sqlite missing"
    assert (seeded_demo / ".git").is_dir(), "git repo not initialized"


def test_seed_script_db_size_substantive(seeded_demo):
    """§0 AC2: DB is non-trivial. Note: 5 MB is the QA spec for the
    default 50K-record run; with 5K records here we expect > 200 KB."""
    size = (seeded_demo / "logs.sqlite").stat().st_size
    assert size > 200_000, f"DB suspiciously small: {size} bytes (expected > 200 KB)"


def test_seed_script_records_in_db(seeded_demo):
    """§0 AC2 corollary: the DB actually contains records."""
    conn = sqlite3.connect(str(seeded_demo / "logs.sqlite"))
    try:
        n = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        n_authors = conn.execute(
            "SELECT COUNT(DISTINCT json_extract(context, '$.tenant_id')) FROM logs "
            "WHERE json_extract(context, '$.tenant_id') IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n > 1000, f"only {n} records — seed script may have regressed"
    assert n_authors > 1, f"only {n_authors} tenants — context bug in seed?"


# ---- §0.3 + §0.4 — viewer startup messages -------------------------------


def test_viewer_startup_indexer_progress_and_no_stacktrace(seeded_demo):
    """§0 AC3 + AC4 combined (one subprocess covers both)."""
    proc = _spawn_viewer([
        "--no-open", "--port", str(_free_port()),
        "--repo", str(seeded_demo),
        str(seeded_demo / "logs.sqlite"),
    ])
    stderr = _wait_then_capture_stderr(proc, settle_s=7.0)

    # AC3 — author indexer ran and printed its summary line.
    # First-launch path emits "indexed N records across M files in X.XXs".
    # If a cache exists from a prior test run, path is "indexed ... from cache".
    assert "ulog: indexed " in stderr, (
        f"author-indexer summary line missing from stderr:\n{stderr}"
    )
    assert ("files in" in stderr) or ("from cache" in stderr), (
        f"indexer summary malformed:\n{stderr}"
    )

    # AC4 — no Python traceback or unhandled exception.
    assert "Traceback (most recent call last)" not in stderr, (
        f"stack trace at startup:\n{stderr}"
    )
    assert "OperationalError" not in stderr
    assert "Logging error" not in stderr


# ---- §0 trap — forgetting --repo from a non-git cwd ----------------------


def test_viewer_without_repo_from_non_git_cwd_warns(tmp_path):
    """§0 ⚠ trap: cwd has no .git/ ancestor → stderr warning, no crash."""
    # Build a minimal sqlite DB matching the ULog schema.
    db = tmp_path / "logs.sqlite"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript("""
            CREATE TABLE logs (
                id INTEGER PRIMARY KEY, ts DATETIME NOT NULL,
                level VARCHAR(10) NOT NULL, logger VARCHAR(255) NOT NULL,
                msg TEXT NOT NULL, file VARCHAR(255) NOT NULL,
                line INTEGER NOT NULL, exc JSON, context JSON
            );
            INSERT INTO logs (ts, level, logger, msg, file, line)
            VALUES ('2026-01-01T00:00:00Z', 'INFO', 'svc', 'hi', 'x.py', 1);
        """)
        conn.commit()
    finally:
        conn.close()

    # cwd = tmp_path (typically /tmp/pytest-...) → no .git/ ancestor.
    proc = _spawn_viewer(
        ["--no-open", "--port", str(_free_port()), str(db)],
        cwd=tmp_path,
    )
    stderr = _wait_then_capture_stderr(proc, settle_s=4.0)

    assert "no git repo detected" in stderr, (
        f"expected the documented `no git repo detected` warning:\n{stderr}"
    )
    assert "Traceback (most recent call last)" not in stderr
