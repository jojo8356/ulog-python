"""End-to-end test for the first-launch tutorial overlay (FR38).

The overlay (`#tutorial`) is rendered hidden, then a small inline
script in `list.html:428-440` unhides it on page load IFF:

  - `?qa_screenshot=1` is NOT in the URL (headless screenshot bypass), AND
  - `localStorage.ulogTutorialDismissed` is NOT set (= first visit).

Clicking the `#tutorial-dismiss` button (label "Got it") writes the
localStorage flag and re-adds the `hidden` class.

Other e2e tests (`test_show_unknown_toggle_e2e.py`, etc.) bake the
localStorage flag into their `page` fixture via `add_init_script` so
the modal stays out of the way. This file does the opposite —
fresh context per test so the FIRST visit really IS a first visit.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from .e2e_helpers import launch_e2e_browser, new_e2e_context
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


@pytest.fixture(scope="module")
def browser() -> Iterator[object]:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = launch_e2e_browser(pw)
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def fresh_context(browser: object) -> Iterator[object]:
    """A pristine browser context — NO `ulogTutorialDismissed` pre-set
    in localStorage. This is what a real first-time visitor sees."""
    with new_e2e_context(browser, dismiss_tutorial=False) as ctx:
        yield ctx


# ---- DOM helpers ----------------------------------------------------------


def _tutorial_visible(page: object) -> bool:
    """`#tutorial` is "shown" iff it does NOT have the `hidden` class."""
    return bool(
        page.evaluate(  # type: ignore[attr-defined]
            "() => { const t = document.getElementById('tutorial');"
            " return t && !t.classList.contains('hidden'); }"
        )
    )


def _tutorial_dismissed_in_storage(page: object) -> bool:
    return bool(
        page.evaluate(  # type: ignore[attr-defined]
            "() => localStorage.getItem('ulogTutorialDismissed') === '1'"
        )
    )


# ============================================================================
# 1. First launch — overlay visible
# ============================================================================


def test_tutorial_visible_on_first_visit(fresh_context, viewer):
    """Fresh browser, no `?qa_screenshot` flag → tutorial overlay
    appears on top of the records list."""
    page = fresh_context.new_page()
    page.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)
    assert _tutorial_visible(page), (
        "tutorial overlay should appear on first visit (no localStorage flag, no qa_screenshot=1)"
    )
    assert not _tutorial_dismissed_in_storage(page), (
        "localStorage flag should NOT yet be set on first paint"
    )


def test_tutorial_renders_welcome_heading_and_4_steps(fresh_context, viewer):
    """Content invariants: the modal carries the `Welcome to ULog`
    heading, exactly 4 numbered list items (Filter / Click / Sectors /
    Docs), and the `Got it` dismiss button. Catches a regression that
    drops a step or breaks the copy."""
    page = fresh_context.new_page()
    page.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)

    modal = page.locator("#tutorial")
    assert modal.locator("h2").text_content().strip().startswith("Welcome to ULog")
    li_count = modal.locator("ol > li").count()
    assert li_count == 4, f"expected 4 onboarding steps, got {li_count}"
    assert modal.locator("#tutorial-dismiss").text_content().strip().endswith("Got it")


# ============================================================================
# 2. Dismiss flow
# ============================================================================


def test_dismiss_button_hides_overlay_and_sets_localstorage(fresh_context, viewer):
    """Click `Got it` → overlay gains `.hidden` AND
    localStorage.ulogTutorialDismissed = '1'."""
    page = fresh_context.new_page()
    page.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)
    assert _tutorial_visible(page), "precondition: overlay starts visible"
    page.locator("#tutorial-dismiss").click()
    assert not _tutorial_visible(page), "overlay should hide after Got it click"
    assert _tutorial_dismissed_in_storage(page), "localStorage flag must be set after dismissal"


def test_dismiss_persists_across_reload(fresh_context, viewer):
    """Dismiss once, reload — overlay stays hidden. The flag in
    localStorage drives the unhide-or-not decision on every page load."""
    page = fresh_context.new_page()
    page.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)
    page.locator("#tutorial-dismiss").click()
    page.reload(wait_until="networkidle")
    assert not _tutorial_visible(page), (
        "overlay should stay hidden after reload — localStorage flag persists"
    )


def test_dismiss_persists_across_navigation(fresh_context, viewer):
    """Dismiss, navigate to a detail view, navigate back — overlay
    stays hidden. Same browsing context = same localStorage."""
    page = fresh_context.new_page()
    page.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)
    page.locator("#tutorial-dismiss").click()
    # Click a row to open its detail view.
    page.locator("main table tbody tr").first.click()
    page.wait_for_load_state("networkidle")
    page.go_back(wait_until="networkidle")
    assert not _tutorial_visible(page), "overlay re-appeared after nav round-trip"


# ============================================================================
# 3. Bypass paths
# ============================================================================


def test_qa_screenshot_flag_suppresses_tutorial_on_first_visit(fresh_context, viewer):
    """`?qa_screenshot=1` keeps the overlay hidden even on a fresh
    context. Used by `scripts/qa_screenshots.py` so the headless
    capture isn't covered by the modal."""
    page = fresh_context.new_page()
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1",
        wait_until="networkidle",
        timeout=15_000,
    )
    assert not _tutorial_visible(page), (
        "tutorial leaked through despite ?qa_screenshot=1 — the screenshot script will fail"
    )
    # And localStorage stays clean (no implicit dismiss).
    assert not _tutorial_dismissed_in_storage(page), (
        "qa_screenshot bypass should NOT write the localStorage flag"
    )


def test_preset_localstorage_flag_suppresses_tutorial(fresh_context, viewer):
    """If `ulogTutorialDismissed` is set BEFORE the page loads, the
    overlay never appears — mirrors a returning user whose previous
    session already dismissed it."""
    # Set the flag via init script, before the first navigation runs the
    # inline check in list.html.
    fresh_context.add_init_script("window.localStorage.setItem('ulogTutorialDismissed', '1')")
    page = fresh_context.new_page()
    page.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)
    assert not _tutorial_visible(page), (
        "tutorial should NOT show when localStorage flag is already set"
    )


# ============================================================================
# 4. Modal behavior — the overlay traps clicks (no leaks behind)
# ============================================================================


def test_overlay_intercepts_clicks_behind_it(fresh_context, viewer):
    """`fixed inset-0 z-50` means the overlay covers the page. A click
    on the spot where a record-row sits behind the overlay must NOT
    navigate to that record's detail view — proves the modal is
    actually modal."""
    page = fresh_context.new_page()
    page.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)
    # Find a row's bounding box; pretend to click ON it.
    row = page.locator("main table tbody tr").first
    box = row.bounding_box()
    assert box is not None, "no record row to click"
    # Click at the center of that row's coordinates — but the overlay
    # is on top, so the click should NOT reach the row.
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(200)
    # We must still be on / and the tutorial must still be visible
    # (the click landed on the overlay backdrop, not on the dismiss
    # button).
    assert "/r/" not in page.url, f"click pierced the modal and navigated to a record: {page.url}"
    assert _tutorial_visible(page), (
        "tutorial disappeared after a click outside its dismiss button — modal leak"
    )


# ============================================================================
# 5. Multi-tab isolation note — localStorage is per-origin, NOT per-tab
# ============================================================================


def test_dismiss_in_one_page_persists_to_a_second_page_in_same_context(
    fresh_context,
    viewer,
):
    """localStorage is shared across all pages in the same context.
    Dismiss in page A → open page B → no overlay (because B reads
    the same flag A just set). Different browser contexts would NOT
    share state — but that's not what users see day-to-day."""
    page_a = fresh_context.new_page()
    page_a.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)
    page_a.locator("#tutorial-dismiss").click()
    assert _tutorial_dismissed_in_storage(page_a)

    page_b = fresh_context.new_page()
    page_b.goto(f"http://127.0.0.1:{viewer}/", wait_until="networkidle", timeout=15_000)
    assert not _tutorial_visible(page_b), (
        "overlay should stay hidden in a sibling page of the same context"
    )
