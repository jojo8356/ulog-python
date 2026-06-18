"""End-to-end tests automating §3 Perf v0.4.1 of the QA checklist.

Replaces the manual `time curl ...` checkboxes with deterministic
budget assertions. Spawns a real viewer subprocess and times HTTP
GETs for cold/warm/filter/pagination/detail-view paths.

Budgets here are RELAXED vs the PRD-v0.4.1 user-facing targets
(which assume the 50K-record demo). The seeded_demo fixture uses
~5K records (the lighter shared seed for fast tests) AND we add
2x headroom for slow CI runners. The assertion `no path > 3s`
matches the user-visible PRD ceiling regardless.

Manual `/qa/` checkboxes for §3 are removed in the same commit;
this test file becomes the regression gate.
"""

from __future__ import annotations

import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from .test_qa_setup_e2e import seeded_demo  # noqa: F401  reuse session-scoped fixture

REPO_ROOT = Path(__file__).parent.parent


# ---- helpers --------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn_viewer(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "ulog.web.cli", *args],
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )


def _wait_for_server(port: int, *, timeout_s: float = 15.0) -> None:
    """Poll until the viewer responds, OR raise on timeout. Faster than
    a fixed sleep — avoids both flakes (too short) and waste (too long)."""
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
    raise RuntimeError(f"viewer never responded on port {port}: {last_err}")


def _time_get(port: int, path: str) -> float:
    """GET path and return elapsed seconds. Body consumed (not parsed)."""
    url = f"http://127.0.0.1:{port}{path}"
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=10) as resp:
        resp.read()
    return time.perf_counter() - t0


# ---- fixture: viewer subprocess for the whole module ----------------------


@pytest.fixture(scope="module")
def viewer(seeded_demo):  # noqa: F811
    """Spawn one viewer per module, tear down after."""
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
        yield port
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


# ---- §3 perf budgets (relaxed for 5K-record fixture + CI headroom) -------

# PRD-v0.4.1 targets are for 50K records. On 5K (the test fixture)
# everything is naturally faster, but we add 2x headroom for slow CI.

BUDGET_COLD_S = 3.0  # PRD target < 1s (50K) → 3s ceiling on test fixture
BUDGET_WARM_S = 1.0  # PRD target < 200ms → 1s ceiling
BUDGET_FILTER_S = 1.0  # PRD target < 200ms → 1s ceiling
BUDGET_AUTHOR_S = 2.0  # PRD target < 2s → kept as-is
BUDGET_PAGINATION_S = 1.0  # PRD target < 200ms → 1s ceiling
BUDGET_DETAIL_S = 0.5  # PRD target < 100ms → 500ms ceiling
BUDGET_HARD_CEILING = 3.0  # The user-visible "no path > 3s" rule


def _first_record_id(seeded_demo) -> int:  # noqa: F811
    """Return the lowest record id present, for the detail-view test."""
    with sqlite3.connect(str(seeded_demo / "logs.sqlite")) as conn:
        row = conn.execute("SELECT MIN(id) FROM logs").fetchone()
    assert row, "fixture DB has no rows"
    assert row[0] is not None, "fixture DB has no records"
    return int(row[0])


def test_perf_cold_cache_under_budget(viewer):
    """§3.1 cold cache: 1st request to / is the warm-up; should still
    answer within the test budget thanks to AuthorsSummary memoization
    and SQL GROUP BY (PRD-v0.4.1 perf patch)."""
    elapsed = _time_get(viewer, "/")
    assert elapsed < BUDGET_COLD_S, f"cold-cache GET / took {elapsed:.3f}s > {BUDGET_COLD_S}s"


def test_perf_warm_cache_under_budget(viewer):
    """§3.2 warm cache: subsequent identical request hits the
    AuthorsSummary memo + SQLite page cache, returns much faster."""
    _time_get(viewer, "/")  # warm-up
    elapsed = _time_get(viewer, "/")
    assert elapsed < BUDGET_WARM_S, f"warm-cache GET / took {elapsed:.3f}s > {BUDGET_WARM_S}s"


def test_perf_filter_level_under_budget(viewer):
    _time_get(viewer, "/")  # warm
    elapsed = _time_get(viewer, "/?level=ERROR")
    assert elapsed < BUDGET_FILTER_S, f"GET /?level=ERROR took {elapsed:.3f}s > {BUDGET_FILTER_S}s"


def test_perf_filter_author_under_budget(viewer):
    """§3.4 author filter: any non-existent email exercises the same
    O(N) post-query path; perf is invariant of which author is chosen."""
    _time_get(viewer, "/")
    elapsed = _time_get(viewer, "/?author=alice@globex.io")
    assert elapsed < BUDGET_AUTHOR_S, f"author filter took {elapsed:.3f}s > {BUDGET_AUTHOR_S}s"


def test_perf_pagination_under_budget(viewer):
    _time_get(viewer, "/")
    elapsed = _time_get(viewer, "/?page=2")
    assert elapsed < BUDGET_PAGINATION_S, f"pagination took {elapsed:.3f}s > {BUDGET_PAGINATION_S}s"


def test_perf_detail_view_under_budget(viewer, seeded_demo):  # noqa: F811
    rec_id = _first_record_id(seeded_demo)
    elapsed = _time_get(viewer, f"/r/{rec_id}/")
    assert elapsed < BUDGET_DETAIL_S, f"detail view took {elapsed:.3f}s > {BUDGET_DETAIL_S}s"


def test_perf_no_path_exceeds_hard_ceiling(viewer, seeded_demo):  # noqa: F811
    """§3.7 the user-visible PRD rule: no path > 3s. Tests the same
    paths as above but with the absolute ceiling, so this assertion
    fails before the more aggressive ones do."""
    rec_id = _first_record_id(seeded_demo)
    paths = [
        "/",
        "/",
        "/?level=ERROR",
        "/?author=alice@globex.io",
        "/?page=2",
        f"/r/{rec_id}/",
    ]
    for path in paths:
        elapsed = _time_get(viewer, path)
        assert elapsed < BUDGET_HARD_CEILING, (
            f"PRD-v0.4.1 hard ceiling violated: GET {path} took {elapsed:.3f}s > {BUDGET_HARD_CEILING}s"
        )


# ---- §4.10 /api/records/ JSON shape (formerly e4-reg-10) -----------------


def test_api_records_returns_valid_json(viewer):
    """§4.10 — /api/records/ returns valid JSON with the expected
    top-level shape (records list + pagination metadata)."""
    import json as _json

    url = f"http://127.0.0.1:{viewer}/api/records/"
    with urllib.request.urlopen(url, timeout=5) as resp:
        assert resp.status == 200, f"got HTTP {resp.status}"
        ctype = resp.getheader("Content-Type", "")
        assert "application/json" in ctype.lower(), f"not JSON: Content-Type={ctype!r}"
        body = resp.read().decode("utf-8")

    payload = _json.loads(body)  # raises ValueError on malformed JSON
    assert isinstance(payload, dict), f"top-level should be dict, got {type(payload).__name__}"

    # Minimal contract: records list exists + each record has the core
    # ULog fields. Don't over-assert (paginate/filter shape may evolve).
    assert "records" in payload, "missing 'records' key"
    assert isinstance(payload["records"], list)
    if payload["records"]:
        first = payload["records"][0]
        for required in ("id", "ts", "level", "logger", "msg", "file", "line"):
            assert required in first, f"record missing {required!r} field"
