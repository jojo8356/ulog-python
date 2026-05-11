"""End-to-end stability tests (§5 Watchpoints).

Replaces three manual QA items with deterministic checks against a
live viewer subprocess:

  e5-sta-1: 20-reload memory ceiling (< 200 MB RES).
  e5-sta-2: no `Logging error` / `OperationalError` on stderr during
            navigation.
  e5-sta-3: git blame subprocess does NOT respawn during idle
            navigation (only at startup).

Linux-only on RSS reading (/proc/<pid>/status); skipped on Win/Mac.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from .test_qa_setup_e2e import seeded_demo  # noqa: F401  reuse module-scoped fixture

# ---- helpers --------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_server(port: int, *, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    raise RuntimeError(f"viewer never responded on port {port} within {timeout_s}s: {last_err}")


def _http_get(port: int, path: str) -> int:
    """GET and return the HTTP status, discarding the body."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as resp:
        resp.read()
        return int(resp.status)


def _rss_mb(pid: int) -> float | None:
    """Resident-set size of a process, in MB. Reads /proc/<pid>/status —
    Linux-only. Returns None on non-Linux or if /proc is unavailable."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    # Format: `VmRSS:    12345 kB`
                    return int(line.split()[1]) / 1024.0
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    return None


def _spawn_viewer_to_file(
    args: list[str],
    stderr_path: Path,
    cwd: Path | None = None,
) -> subprocess.Popen:
    """Spawn the viewer with stderr redirected to a file — lets the test
    inspect the FULL stderr after the process is torn down without
    threading or non-blocking reads."""
    stderr_f = stderr_path.open("w")
    return subprocess.Popen(
        [sys.executable, "-m", "ulog.web.cli", *args],
        stderr=stderr_f,
        stdout=subprocess.DEVNULL,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def _stop(proc: subprocess.Popen, *, timeout: float = 5.0) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


# ============================================================================
# e5-sta-1 — 20-reload memory ceiling
# ============================================================================


@pytest.mark.skipif(not Path("/proc").exists(), reason="Linux-only (/proc readout)")
def test_reload_20_times_stays_under_200mb_rss(
    seeded_demo: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Reload `/` 20x and verify the viewer's RSS stays under 200 MB.
    Catches request-handler leaks (closure capture of recordsets,
    SQLAlchemy connection growth, accidental global accumulation)."""
    port = _free_port()
    stderr_path = tmp_path / "viewer.stderr"
    proc = _spawn_viewer_to_file(
        [
            "--no-open",
            "--port",
            str(port),
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ],
        stderr_path,
    )
    try:
        _wait_for_server(port, timeout_s=15)
        rss_baseline = _rss_mb(proc.pid)
        assert rss_baseline is not None, "could not read /proc/<pid>/status"
        # 20 sequential reloads of /. The page touches the full pipeline:
        # adapter query + author resolution + template render.
        for _ in range(20):
            status = _http_get(port, "/")
            assert status == 200, f"GET / returned {status}"
        rss_after = _rss_mb(proc.pid)
        assert rss_after is not None
        assert rss_after < 200.0, (
            f"viewer RSS leaked past 200 MB ceiling: "
            f"baseline {rss_baseline:.1f} MB → after 20 reloads {rss_after:.1f} MB"
        )
    finally:
        _stop(proc)


# ============================================================================
# e5-sta-2 — no Logging error / OperationalError on stderr while navigating
# ============================================================================


def test_navigation_emits_no_logging_error_or_operational_error(
    seeded_demo: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Walk through every major view and verify stderr stays clean.
    Specifically watches for stdlib `logging`'s emit-failure message
    (`--- Logging error ---`) and SQLAlchemy's `OperationalError`,
    which are the two regressions §5 explicitly calls out."""
    port = _free_port()
    stderr_path = tmp_path / "viewer.stderr"
    proc = _spawn_viewer_to_file(
        [
            "--no-open",
            "--port",
            str(port),
            "--debug",  # exercise debug-only paths too
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ],
        stderr_path,
    )
    try:
        _wait_for_server(port, timeout_s=15)

        # Find a real record id and a real commit sha to exercise the
        # detail + diff views.
        import sqlite3

        with sqlite3.connect(str(seeded_demo / "logs.sqlite")) as conn:
            rec_id = int(conn.execute("SELECT MIN(id) FROM logs").fetchone()[0])
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(seeded_demo),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Walk the major paths.
        paths = [
            "/",
            "/?level=ERROR",
            "/?q=test",
            "/?show_unknown=0",
            f"/r/{rec_id}/",
            f"/diff/{sha}/",
            "/docs/",
            "/docs/quickstart/",
            "/_qa/",
            "/api/records/",
        ]
        for p in paths:
            # Some endpoints may 4xx — those don't put error noise on
            # stderr unless something else broke. Suppress so the loop
            # exercises every path.
            with contextlib.suppress(urllib.error.URLError):
                _http_get(port, p)

        # Give the request handlers a moment to flush.
        time.sleep(0.5)
    finally:
        _stop(proc)

    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    # Two stable error markers in stdlib / SQLAlchemy.
    assert "--- Logging error ---" not in stderr_text, (
        f"stdlib logging failure surfaced on stderr — handler crashed during navigation:\n"
        f"{stderr_text[-1500:]}"
    )
    assert "OperationalError" not in stderr_text, (
        f"SQLAlchemy OperationalError on stderr during navigation:\n{stderr_text[-1500:]}"
    )
    # Bonus belt-and-suspenders: 5xx responses are never silent — they
    # show up as `[ERROR]` lines too.
    assert "Internal Server Error" not in stderr_text, (
        f"500 response logged on stderr during navigation:\n{stderr_text[-1500:]}"
    )


# ============================================================================
# e5-sta-3 — git blame subprocess does not respawn during idle navigation
# ============================================================================


def test_git_blame_does_not_respawn_during_idle_navigation(
    seeded_demo: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    """The author indexer runs ONCE at startup and warms every
    (file, line) blame pair. Subsequent navigation hits the cache;
    no new `git blame` subprocess should spawn.

    Signal: count the indexer's final `ulog: indexed N records in Xs`
    line. It must appear exactly once. A second occurrence means the
    indexer re-ran on a hot navigation path → cache invalidation bug
    or the warm-up path stopped being warm.
    """
    port = _free_port()
    stderr_path = tmp_path / "viewer.stderr"
    proc = _spawn_viewer_to_file(
        [
            "--no-open",
            "--port",
            str(port),
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ],
        stderr_path,
    )
    try:
        _wait_for_server(port, timeout_s=15)
        # The indexer runs synchronously in main() before serve() —
        # wait_for_server returning 200 means it's finished.
        time.sleep(0.3)  # let stderr finish flushing the final "indexed" line
        startup_stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        indexed_count_startup = startup_stderr.count("ulog: indexed ")
        assert indexed_count_startup == 1, (
            f"expected exactly 1 'ulog: indexed' line at startup, "
            f"got {indexed_count_startup}; stderr:\n{startup_stderr[-800:]}"
        )

        # Now idle-navigate: 10 GETs that don't change any filter or
        # touch a path that would need a fresh blame.
        for _ in range(10):
            _http_get(port, "/")

        time.sleep(0.3)
        full_stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        indexed_count_after = full_stderr.count("ulog: indexed ")
        assert indexed_count_after == 1, (
            f"indexer ran AGAIN during idle navigation (count went "
            f"{indexed_count_startup} → {indexed_count_after}). Tail of stderr:\n"
            f"{full_stderr[-1500:]}"
        )
        # Additionally: no further `indexing authors` progress lines
        # should appear after the startup batch.
        progress_lines_startup = startup_stderr.count("ulog: indexing authors")
        progress_lines_after = full_stderr.count("ulog: indexing authors")
        assert progress_lines_after == progress_lines_startup, (
            f"indexer emitted new progress lines during idle nav: "
            f"{progress_lines_after - progress_lines_startup} extra. Tail:\n"
            f"{full_stderr[-1500:]}"
        )
    finally:
        _stop(proc)
