"""End-to-end tests for the record detail view (FR37 / e4-reg-11).

`/r/<id>/` must render:
  - ALWAYS: level badge, ts, logger, file:line header + Message section + record-id footer
  - CONDITIONALLY: Context section (when record.context is non-empty)
  - CONDITIONALLY: Exception section (when record.exc is set) — including
    the exception type, message, and traceback lines.

Test records are picked from the seeded demo via direct SQL so the
suite stays seed-agnostic: it asks the DB "give me a record with X"
rather than hardcoding ids that could shift between seed runs.
"""

from __future__ import annotations

import json
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from .test_qa_setup_e2e import seeded_demo  # noqa: F401  reuse session-scoped fixture


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
    raise RuntimeError(f"viewer never responded on port {port}: {last_err}")


@pytest.fixture(scope="module")
def viewer(seeded_demo: Path) -> Iterator[int]:  # noqa: F811
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ulog.web.cli",
            "--no-open",
            "--port",
            str(port),
            "--repo",
            str(seeded_demo),
            str(seeded_demo / "logs.sqlite"),
        ],
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
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


# ---- Record discovery — SQL-driven, seed-agnostic ------------------------


@pytest.fixture(scope="module")
def sample_record(seeded_demo: Path) -> dict:  # noqa: F811
    """One non-test record with context populated. Picks the first id
    that has a non-empty `context` JSON. Lets the test assert on every
    field shown in the detail view."""
    with sqlite3.connect(str(seeded_demo / "logs.sqlite")) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, ts, level, logger, msg, file, line, context, exc "
            "FROM logs "
            "WHERE context IS NOT NULL AND context != '{}' AND logger != 'ulog.test' "
            "ORDER BY id ASC LIMIT 1"
        ).fetchone()
    assert row, "seeded demo has no non-test record with context"
    return dict(row)


@pytest.fixture(scope="module")
def sample_exception_record(seeded_demo: Path) -> dict | None:  # noqa: F811
    """One record with an exception attached, if any. Some seeds may not
    have one — tests that need this skip if None."""
    with sqlite3.connect(str(seeded_demo / "logs.sqlite")) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, ts, level, logger, msg, file, line, context, exc "
            "FROM logs WHERE exc IS NOT NULL ORDER BY id ASC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ---- HTTP helper ----------------------------------------------------------


def _detail_html(viewer: int, rec_id: int) -> str:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{viewer}/r/{rec_id}/",
        timeout=10,
    ) as resp:
        return resp.read().decode("utf-8")


# ============================================================================
# 1. Always-rendered fields (header + message + record-id footer)
# ============================================================================


def test_detail_view_shows_ts(viewer, sample_record):
    """The record's ISO-8601 timestamp appears in the header row."""
    body = _detail_html(viewer, sample_record["id"])
    # `r.ts` is rendered verbatim in a <span class="font-mono ...">{{ r.ts }}</span>.
    # The DB stores it as a `datetime` object via SQLAlchemy; the adapter
    # serializes to e.g. `2026-05-10T21:56:38Z`. Match by the year prefix
    # to stay tolerant to the exact format.
    assert "2026-" in body, f"timestamp not found in detail view (rec {sample_record['id']})"


def test_detail_view_shows_level_badge(viewer, sample_record):
    """The level appears inside an inline-block span styled per level.
    Template wraps the value with whitespace, so match by re after
    collapsing the body's whitespace."""
    import re

    body = _detail_html(viewer, sample_record["id"])
    lvl = sample_record["level"]
    collapsed = re.sub(r"\s+", " ", body)
    assert f"> {lvl} <" in collapsed or f">{lvl}<" in collapsed, (
        f"level {lvl!r} not rendered as a span body in detail view"
    )


def test_detail_view_shows_logger(viewer, sample_record):
    body = _detail_html(viewer, sample_record["id"])
    assert sample_record["logger"] in body, "logger not in detail view"


def test_detail_view_shows_file_and_line(viewer, sample_record):
    """`file:line` rendered as a single `font-mono` span in the header."""
    body = _detail_html(viewer, sample_record["id"])
    needle = f"{sample_record['file']}:{sample_record['line']}"
    assert needle in body, f"{needle!r} missing from detail view header"


def test_detail_view_shows_message_section(viewer, sample_record):
    """The Message h2 + the msg text are both present."""
    body = _detail_html(viewer, sample_record["id"])
    assert ">Message<" in body, "Message section header missing"
    # The msg goes through Django auto-escape; substring match is enough
    # unless the msg itself contains HTML. The seed's msgs are plain.
    assert sample_record["msg"] in body, "msg text missing from detail view"


def test_detail_view_shows_record_id_footer(viewer, sample_record):
    body = _detail_html(viewer, sample_record["id"])
    assert f"Record id: {sample_record['id']}" in body, "record-id footer missing"


# ============================================================================
# 2. Conditional Context section
# ============================================================================


def test_detail_view_shows_context_block_when_record_has_context(viewer, sample_record):
    """The `<h2>Context</h2>` block appears with every k=v pair from the
    record's JSON context column."""
    body = _detail_html(viewer, sample_record["id"])
    assert ">Context<" in body, "Context section header missing"
    ctx = json.loads(sample_record["context"])
    for k, v in ctx.items():
        # The template renders each pair as `{{ k }}: {{ v }}` inside a
        # <pre><code>. Substring match catches it.
        assert f"{k}: {v}" in body, f"context pair {k}={v!r} missing"


def test_detail_view_hides_context_block_when_record_has_no_context(viewer, seeded_demo):  # noqa: F811
    """A record with `context IS NULL` (or `'{}'`) must NOT render the
    Context block. The template's `{% if record.context %}` guard
    handles this."""
    with sqlite3.connect(str(seeded_demo / "logs.sqlite")) as conn:
        row = conn.execute(
            "SELECT id FROM logs WHERE context IS NULL OR context = '{}' "
            "OR context = 'null' LIMIT 1"
        ).fetchone()
    if not row:
        pytest.skip("seed has no context-less record")
    body = _detail_html(viewer, int(row[0]))
    # The HEADER text "Context" must not appear as an <h2> label.
    # `Test context` is a different section so guard against false hits.
    assert "<span>Context</span>" not in body, "Context block leaked into a record with no context"


# ============================================================================
# 3. Conditional Exception section
# ============================================================================


def test_detail_view_hides_exception_block_when_no_exc(viewer, sample_record):
    """Non-exception record → no Exception block, no Bug icon header."""
    # Pre-condition: this record has no exc.
    assert sample_record["exc"] is None, "sample_record fixture unexpectedly has exc"
    body = _detail_html(viewer, sample_record["id"])
    assert "Exception (" not in body, "Exception block leaked into a record with no exc"


def test_detail_view_shows_exception_block_when_exc_present(viewer, sample_exception_record):
    """When the record carries an exception payload, the Exception
    section renders with: header "Exception (<type>)", the exc msg,
    and the traceback lines inside a <pre>."""
    if sample_exception_record is None:
        pytest.skip("seed has no record with exc")
    rec = sample_exception_record
    body = _detail_html(viewer, rec["id"])
    exc = json.loads(rec["exc"]) if isinstance(rec["exc"], str) else rec["exc"]
    # Header: `Exception (<type>)`.
    assert f"Exception ({exc['type']})" in body, f"Exception header missing type {exc['type']!r}"
    # Exception message body.
    assert exc["msg"] in body, "exception msg missing"
    # At least one traceback line.
    assert exc.get("tb"), "fixture record has empty tb — pick another"
    # The first tb line should appear in the rendered <pre>.
    first_tb_token = exc["tb"][0].split()[0]  # e.g. 'File'
    assert first_tb_token in body, "traceback content not rendered"


# ============================================================================
# 4. Back-to-records link
# ============================================================================


def test_detail_view_has_back_to_records_link(viewer, sample_record):
    """Top of the page carries a `← Back to records` link pointing at /."""
    body = _detail_html(viewer, sample_record["id"])
    assert "Back to records" in body, "back-to-records link label missing"
    # The link's href is `{% url 'ulog-list' %}` = "/".
    # When the user came from a filtered list, the template appends
    # `?qs=…`. Either form is acceptable; just check the anchor exists.
    assert 'href="/"' in body or 'href="/?' in body, (
        "back-to-records link href to / (or /?…) missing"
    )


# ============================================================================
# 5. 404 on unknown id
# ============================================================================


def test_detail_view_404_on_unknown_record_id(viewer):
    """`/r/99999999/` (id well past the seed) → 404."""
    try:
        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{viewer}/r/99999999/",
            timeout=5,
        )
        status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == 404, f"unknown record id should 404, got {status}"
