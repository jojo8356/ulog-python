"""End-to-end CLI flag tests for `ulog-web` (Story 2.2).

Replaces the manual `§2.7 — terminal tests` checklist items with
deterministic assertions: spawns real `python -m ulog.web.cli`
subprocesses, captures stderr, hits the viewer over HTTP to verify
the Authors block visibility.

Existing unit tests (`tests/test_cli_repo_flags.py`) cover the
argparse / `_resolve_repo_flag` helpers in isolation — these e2e
tests prove the SAME contract through the actual subprocess boundary,
matching what a user sees in their terminal.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .test_qa_setup_e2e import seeded_demo  # noqa: F401  reuse session-scoped fixture

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


def _spawn_viewer(args: list[str]) -> subprocess.Popen:
    """Spawn `python -m ulog.web.cli <args>`. Captures stderr so tests
    can inspect warning messages."""
    return subprocess.Popen(
        [sys.executable, "-m", "ulog.web.cli", *args],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )


def _stop(proc: subprocess.Popen, *, timeout: float = 5.0) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _html(port: int, path: str = "/") -> str:
    """GET and return the body text (str)."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ============================================================================
# §2.7 CLI flag matrix — one test class per AC for isolated subprocess setup
# ============================================================================


# ---- e2-2.7-1 — `--no-author-index` hides AUTHORS block, instant startup -


def test_no_author_index_hides_authors_block_in_sidebar(seeded_demo: Path) -> None:  # noqa: F811
    """`--no-author-index` short-circuits the indexer entirely. Result:
    no `<aside>` `Authors` section is rendered (the template's `{% if
    authors_summary %}` guard is False)."""
    port = _free_port()
    proc = _spawn_viewer(
        [
            "--no-open",
            "--port",
            str(port),
            "--no-author-index",
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ]
    )
    try:
        _wait_for_server(port, timeout_s=15)
        body = _html(port, "/")
        # The Authors block uses the literal "Authors" inside an <h3>
        # in the sidebar. With idx=None it should be absent.
        # Use the data-i18n hint or the user icon's surrounding span.
        assert ">Authors<" not in body, (
            "Authors block should be hidden when --no-author-index is set"
        )
    finally:
        _stop(proc)


def test_no_author_index_startup_under_2s(seeded_demo: Path) -> None:  # noqa: F811
    """No indexer → near-instant startup (well under 2s even on slow CI).
    Without the flag, the demo seed takes ~1s of indexer time."""
    port = _free_port()
    t0 = time.perf_counter()
    proc = _spawn_viewer(
        [
            "--no-open",
            "--port",
            str(port),
            "--no-author-index",
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ]
    )
    try:
        _wait_for_server(port, timeout_s=5)
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, (
            f"--no-author-index startup took {elapsed:.2f}s — expected near-instant"
        )
    finally:
        _stop(proc)


# ---- e2-2.7-2 — `--rebuild-author-index` drops cache, reblames ---------


def test_rebuild_author_index_emits_indexing_progress_on_stderr(seeded_demo: Path) -> None:  # noqa: F811
    """The indexer prints `ulog: indexing authors...` on stderr while
    it works. `--rebuild-author-index` forces a fresh blame even if
    the sidecar cache exists, so the progress line MUST appear."""
    # First run — primes the cache (so on rebuild we know we're forcing it).
    port1 = _free_port()
    p1 = _spawn_viewer(
        [
            "--no-open",
            "--port",
            str(port1),
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ]
    )
    try:
        _wait_for_server(port1, timeout_s=15)
    finally:
        _stop(p1)

    # Second run with --rebuild-author-index — should re-emit progress.
    port2 = _free_port()
    p2 = _spawn_viewer(
        [
            "--no-open",
            "--port",
            str(port2),
            "--rebuild-author-index",
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ]
    )
    try:
        _wait_for_server(port2, timeout_s=15)
        # Drain stderr non-blockingly (process is still running).
        # The "indexing" line is emitted BEFORE the "serving on" line
        # that _wait_for_server proves we got. So stderr is ready.
        _stop(p2)
        # Now read whatever was buffered.
        stderr_text = p2.stderr.read() if p2.stderr else ""
        assert "indexing authors" in stderr_text, (
            f"--rebuild-author-index didn't trigger indexer progress; stderr was:\n{stderr_text[:500]}"
        )
    finally:
        _stop(p2)


# ---- e2-2.7-3 — no .git/ → stderr warning, AUTHORS hidden --------------


def test_no_git_repo_emits_stderr_warning(tmp_path: Path, seeded_demo: Path) -> None:  # noqa: F811
    """When the viewer is launched from a directory with no .git/ ancestor
    AND no explicit --repo, it must warn on stderr that author resolution
    is disabled."""
    # Copy ONLY the logs.sqlite into a tmp_path that has NO git ancestry.
    # The seeded_demo dir IS a git repo (commits exist), so we'd need to
    # move outside it. tmp_path is created fresh under pytest's basetemp.
    import shutil

    log_path = tmp_path / "logs.sqlite"
    shutil.copy(seeded_demo / "logs.sqlite", log_path)

    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp_path.parent)}

    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ulog.web.cli",
            "--no-open",
            "--port",
            str(port),
            str(log_path),
        ],
        cwd=str(tmp_path),  # CRITICAL: launch FROM the no-git dir
        env=env,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_server(port, timeout_s=15)
        body = _html(port, "/")
        _stop(proc)
        stderr_text = proc.stderr.read() if proc.stderr else ""
        # Warning message — the cli.py:82 hint mentions --no-author-index
        # as the way to silence it.
        assert "no-author-index" in stderr_text or "no git" in stderr_text.lower(), (
            f"expected stderr warning when no .git/ found; got:\n{stderr_text[:500]}"
        )
        # AND the Authors block is hidden (idx=None when no repo).
        assert ">Authors<" not in body, (
            "Authors block should be hidden when no git repo is detected"
        )
    finally:
        _stop(proc)


# ---- e2-2.7-4 — `--no-author-index --rebuild-author-index` mutex error -


def test_no_index_and_rebuild_are_mutually_exclusive(seeded_demo: Path) -> None:  # noqa: F811
    """argparse `add_mutually_exclusive_group()` causes exit code 2 +
    'not allowed with' message on stderr when both flags are passed."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ulog.web.cli",
            "--no-open",
            "--port",
            "0",
            "--no-author-index",
            "--rebuild-author-index",
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2, (
        f"argparse mutex should exit 2, got {proc.returncode}; stderr={proc.stderr[:500]}"
    )
    assert "not allowed with" in proc.stderr, (
        f"expected argparse mutex error in stderr; got:\n{proc.stderr[:500]}"
    )


# ---- Bonus: tighten with one more invariant ------------------------------


def test_default_run_shows_authors_block(seeded_demo: Path) -> None:  # noqa: F811
    """Sanity check: WITHOUT --no-author-index, the Authors block IS
    rendered. Prevents the e2-2.7-1 test passing trivially because the
    block was removed altogether."""
    port = _free_port()
    proc = _spawn_viewer(
        [
            "--no-open",
            "--port",
            str(port),
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ]
    )
    try:
        _wait_for_server(port, timeout_s=15)
        body = _html(port, "/")
        assert ">Authors<" in body, (
            "Authors block expected when the indexer is enabled (no --no-author-index)"
        )
    finally:
        _stop(proc)
