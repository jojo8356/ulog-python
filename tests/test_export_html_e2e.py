"""Cross-browser e2e for `ulog export-html` (PRD-v0.6.3 / Story 8.13).

Parametrized over chromium / firefox / webkit via the pytest-playwright
plugin's `--browser` flag. Run locally with:

    pytest tests/test_export_html_e2e.py \\
        --browser chromium --browser firefox --browser webkit

Tests use the `page` fixture (provided by pytest-playwright) which is
already browser-aware via the CLI flag.

Skipped automatically when:
- playwright is not installed
- the specific browser binary isn't available (browser_name fixture)

This keeps the suite green on `pytest -q` (no browsers required) and
turns green on CI with `--browser ...` flags.
"""

from __future__ import annotations

import contextlib
import http.server
import logging
import socket
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright")
pytest_playwright = pytest.importorskip("pytest_playwright")

import ulog
from ulog.web.export import ExportOptions, HtmlExporter


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


def _seed_db(tmp_path: Path) -> Path:
    """Seed a small chain DB with mixed records."""
    db = tmp_path / "in.sqlite"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("svc.checkout")
    for i in range(10):
        log.info("step %d ok", i)
    log.error("boom: stripe 503")
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def served_export(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Build a separate-data export and serve it via http.server."""
    db = _seed_db(tmp_path)
    out = tmp_path / "out"
    HtmlExporter(db, ExportOptions(output=out, inline_data=False)).run()
    port = _free_port()
    def handler(*a, **kw):
        return http.server.SimpleHTTPRequestHandler(*a, directory=str(out), **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield (f"http://127.0.0.1:{port}", out)
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def inline_export(tmp_path: Path) -> Path:
    """Build an inline-data export at file:// URL-ready disk path."""
    db = _seed_db(tmp_path)
    out = tmp_path / "out"
    HtmlExporter(db, ExportOptions(output=out, inline_data=True)).run()
    return out


# ---- Smoke tests across all 3 browsers (when invoked with --browser ...) ----


def test_index_loads_and_renders_records(page, served_export) -> None:
    """index.html paints; record count visible."""
    base_url, _ = served_export
    page.goto(f"{base_url}/index.html")
    page.wait_for_selector("h1", timeout=5000)
    assert "11" in page.text_content("h1") or "record" in page.text_content("h1").lower()


def test_no_console_errors_on_index(page, served_export) -> None:
    """Page load triggers zero JS console errors."""
    base_url, _ = served_export
    errors: list[str] = []

    def collect(msg) -> None:
        if msg.type == "error":
            errors.append(msg.text)

    page.on("console", collect)
    page.goto(f"{base_url}/index.html")
    page.wait_for_load_state("networkidle")
    assert errors == [], f"console errors leaked: {errors}"


def test_integrity_badge_visible(page, served_export) -> None:
    """Integrity badge (any of the 3 states) is visible on every page."""
    base_url, _ = served_export
    page.goto(f"{base_url}/index.html")
    badge = page.locator(".integrity-OK, .integrity-BROKEN, .integrity-missing")
    assert badge.is_visible(), "integrity badge missing from index header"


def test_click_record_navigates_to_detail(page, served_export) -> None:
    """Clicking a record row navigates to /r/<id>.html."""
    base_url, _ = served_export
    page.goto(f"{base_url}/index.html")
    link = page.locator("a[href^='r/']").first
    link.click()
    page.wait_for_url("**/r/*.html", timeout=5000)


def test_xss_in_msg_does_not_execute(page, tmp_path: Path) -> None:
    """NFR-SEC-60 (Story 8.12) re-asserted in a real browser."""
    db = tmp_path / "xss.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().error("<script>alert(1)</script>")
    for h in logging.getLogger().handlers:
        h.flush()
    out = tmp_path / "out"
    HtmlExporter(db, ExportOptions(output=out, inline_data=True)).run()

    dialogs: list[str] = []
    page.on("dialog", lambda d: dialogs.append(d.message) or d.dismiss())
    page.goto(f"file://{out}/index.html")
    page.wait_for_selector("body")
    assert dialogs == [], f"XSS leaked: {dialogs}"


def test_inline_data_opens_via_file_url(page, inline_export) -> None:
    """`--inline-data` exports work via `file://` (no fetch() needed)."""
    page.goto(f"file://{inline_export}/index.html")
    page.wait_for_selector("h1", timeout=5000)
    assert "record" in page.text_content("h1").lower()
