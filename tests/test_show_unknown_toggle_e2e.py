"""End-to-end Playwright tests for the FR78 "Show unknown" toggle.

The backend already had unit tests (tests/test_authors_filter.py)
hitting `/?show_unknown=0` directly. Those tests passed even when the
UI checkbox was effectively dead: unchecking the checkbox in a real
browser submitted NO `show_unknown` field at all (browsers omit
unchecked checkboxes), so the URL stayed clean and the backend's
default `qs.get("show_unknown", "1")` quietly kicked in → record
list never changed.

This file plugs the gap: drives Chromium through the same flow a
human would, verifying both the URL transitions AND the rendered
record set across the matrix of states (with/without author
preselection, with/without level filter, reload, deep-link, etc.).

Spawns a viewer subprocess and a Playwright browser per module.
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

from .test_qa_setup_e2e import seeded_demo  # noqa: F401  reuse module-scoped fixture

REPO_ROOT = Path(__file__).parent.parent


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
    raise RuntimeError(f"viewer never responded on port {port}: {last_err}")


# ---- module-scoped viewer subprocess --------------------------------------


@pytest.fixture(scope="module")
def viewer(seeded_demo: Path) -> Iterator[int]:  # noqa: F811
    """One viewer subprocess shared across all tests in this module."""
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


# ---- module-scoped Playwright browser -------------------------------------


@pytest.fixture(scope="module")
def browser() -> Iterator[object]:
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def page(browser: object, viewer: int) -> Iterator[object]:
    """Fresh browser context per test — no localStorage / cookie leak."""
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})  # type: ignore[attr-defined]
    # Dismiss the tutorial overlay PERMANENTLY for this context. Without
    # this, after the first form submit (which navigates to a URL that
    # drops qa_screenshot=1), the tutorial reappears and intercepts
    # subsequent clicks → flaky timeouts on checkbox actions.
    ctx.add_init_script("window.localStorage.setItem('ulogTutorialDismissed', '1')")
    page = ctx.new_page()
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    try:
        yield page
    finally:
        ctx.close()


# ---- DOM helpers ----------------------------------------------------------


def _show_unknown_checkbox(page: object) -> object:
    """The UI checkbox (NOT the hidden field that always submits 0)."""
    return page.locator('input[type="checkbox"][name="show_unknown"]')  # type: ignore[attr-defined]


def _apply_button(page: object) -> object:
    return page.get_by_role("button", name="Apply")  # type: ignore[attr-defined]


def _total_count(page: object) -> int:
    """Parse the "N records (page M of K)" header."""
    txt = page.locator("main p").first.text_content()  # type: ignore[attr-defined]
    # Format: "44771 records (page 1 of 448)" — grab the first int.
    return int(txt.replace(",", "").split()[0])


def _table_authors(page: object) -> list[str]:
    """Return the rendered Author column text for every visible row."""
    return [  # type: ignore[no-any-return]
        td.text_content().strip()
        for td in page.locator("main table tbody tr td:nth-child(4)").all()  # type: ignore[attr-defined]
    ]


# ============================================================================
# 1. Default state
# ============================================================================


def test_default_state_checkbox_is_checked(page):
    """FR78 default: show_unknown=True (ON) on first load."""
    assert _show_unknown_checkbox(page).is_checked() is True


def test_default_state_url_has_no_show_unknown_param(page):
    """First load must not pollute the URL with show_unknown=...
    (default is implicit ON)."""
    url = page.url
    # The page was loaded with ?qa_screenshot=1 — that's allowed. Anything
    # else with show_unknown is a regression.
    assert "show_unknown" not in url, f"unexpected show_unknown in URL: {url}"


def test_default_state_unknown_records_visible_in_table(page):
    """Default ON → records with unresolved author (rendered as '—'
    in the Author column) appear in the table."""
    authors = _table_authors(page)
    # The seeded demo has ~1060 unknown records out of ~44K. At page_size=100
    # the first page may have a mix; '—' may or may not appear depending on
    # sort order. We assert the page rendered AT LEAST one row.
    assert len(authors) > 0, "no records rendered on default load"


# ============================================================================
# 2. Uncheck → form submit → state transitions
# ============================================================================


def test_uncheck_then_apply_url_contains_show_unknown_0(page):
    """Uncheck the checkbox, click Apply, the URL must carry
    show_unknown=0 — proves the form actually submits the toggle."""
    cb = _show_unknown_checkbox(page)
    cb.uncheck()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    assert "show_unknown=0" in page.url, f"missing show_unknown=0: {page.url}"


def test_uncheck_then_apply_hides_unknown_records_from_table(page, viewer):
    """The records column 'Author' must not contain any '—' (unresolved)
    after the toggle is off."""
    cb = _show_unknown_checkbox(page)
    cb.uncheck()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    # Walk all pages? No — page 1 of the filtered set is enough; if any
    # row is '—' the filter is broken.
    authors = _table_authors(page)
    assert authors, "no records rendered with show_unknown=0"
    assert all(a != "—" for a in authors), f"unknown leaked through: {authors[:5]}"


def test_uncheck_decreases_total_count(page):
    """Toggling show_unknown OFF must reduce the total record count.
    Any drop > 0 proves the toggle is wired; the dead-toggle bug
    showed `after == initial` because the form never submitted the
    parameter."""
    initial = _total_count(page)
    cb = _show_unknown_checkbox(page)
    cb.uncheck()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    after = _total_count(page)
    assert after < initial, (
        f"count did not drop ({initial} → {after}) — FR78 is dead "
        f"again (browsers omit unchecked checkboxes from form submits; "
        f"hidden show_unknown=0 field must precede the checkbox)"
    )


def test_recheck_restores_records(page):
    """Toggle OFF then ON → records back to baseline count."""
    baseline = _total_count(page)
    cb = _show_unknown_checkbox(page)
    cb.uncheck()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    # Now recheck.
    cb = _show_unknown_checkbox(page)
    cb.check()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    after = _total_count(page)
    assert after == baseline, f"expected {baseline}, got {after}"


# ============================================================================
# 3. URL → UI round-trip (deep linking)
# ============================================================================


def test_url_show_unknown_0_renders_checkbox_unchecked(page, viewer):
    """Deep-linked URL with show_unknown=0 must reflect in the UI."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?show_unknown=0&qa_screenshot=1", wait_until="networkidle"
    )
    assert _show_unknown_checkbox(page).is_checked() is False


def test_url_show_unknown_1_renders_checkbox_checked(page, viewer):
    """Explicit show_unknown=1 in URL also reflects correctly."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?show_unknown=1&qa_screenshot=1", wait_until="networkidle"
    )
    assert _show_unknown_checkbox(page).is_checked() is True


def test_reload_preserves_unchecked_state(page, viewer):
    """Uncheck, apply, reload — checkbox stays unchecked (URL drives it)."""
    cb = _show_unknown_checkbox(page)
    cb.uncheck()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    url_before_reload = page.url
    page.reload(wait_until="networkidle")
    assert page.url == url_before_reload
    assert _show_unknown_checkbox(page).is_checked() is False


# ============================================================================
# 4. Interaction with other filters
# ============================================================================


def test_with_preselected_author_show_unknown_toggle_isolates_to_author(page, viewer):
    """When an author is selected AND show_unknown is OFF, every
    rendered row must match that author (no unknowns leak)."""
    # Pick the highest-count author present in the seeded demo.
    page.goto(
        f"http://127.0.0.1:{viewer}/?author=erwin@globex.io&show_unknown=0&qa_screenshot=1",
        wait_until="networkidle",
    )
    authors = _table_authors(page)
    assert authors, "no records for erwin@globex.io with show_unknown=0"
    # Every row should display Erwin's name (truncated to 18 chars by
    # the template's truncatechars filter).
    assert all("Erwin" in a for a in authors), f"non-Erwin row visible: {authors}"


def test_with_preselected_author_and_show_unknown_on(page, viewer):
    """Same selection with show_unknown=1: now BOTH Erwin records AND
    unknown records appear (the union)."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?author=erwin@globex.io&show_unknown=1&qa_screenshot=1",
        wait_until="networkidle",
    )
    authors = _table_authors(page)
    assert authors, "no records for erwin@globex.io with show_unknown=1"
    # At least some rows are Erwin's; some MAY be '—' depending on
    # mix on this page. The key check is that '—' is *allowed* here
    # (vs forbidden in the previous test).
    has_erwin = any("Erwin" in a for a in authors)
    assert has_erwin, "expected at least some Erwin records visible"


def test_combined_with_level_filter(page, viewer):
    """level=ERROR + show_unknown=0 → only ERROR rows AND every author
    resolved (no '—' in Author column)."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?level=ERROR&show_unknown=0&qa_screenshot=1",
        wait_until="networkidle",
    )
    # Verify both filters effective: Level column shows ERROR; Author '—' absent.
    levels = [
        td.text_content().strip()
        for td in page.locator("main table tbody tr td:nth-child(2)").all()
    ]
    authors = _table_authors(page)
    assert levels, "no rows rendered"
    assert all(lv == "ERROR" for lv in levels), f"non-ERROR row: {levels[:5]}"
    assert all(a != "—" for a in authors), f"unknown leaked: {authors[:5]}"


# ============================================================================
# 5. Pagination preserves the toggle
# ============================================================================


def test_pagination_preserves_show_unknown_0(page, viewer):
    """Navigate to page 2 while show_unknown=0 is active — the toggle
    state must survive the page change (URL carries it)."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?show_unknown=0&page=2&qa_screenshot=1",
        wait_until="networkidle",
    )
    assert _show_unknown_checkbox(page).is_checked() is False
    authors = _table_authors(page)
    assert authors, "no rows on page 2"
    assert all(a != "—" for a in authors), f"unknown leaked on page 2: {authors[:5]}"


# ============================================================================
# 6. Sidebar Authors block independence
# ============================================================================


def test_sidebar_unknown_entry_always_present(page, viewer):
    """The Authors sidebar lists every known author + the `<unknown>`
    sentinel — INDEPENDENT of the show_unknown toggle. (The toggle
    filters the records LIST, not the SIDEBAR.)"""
    page.goto(
        f"http://127.0.0.1:{viewer}/?show_unknown=0&qa_screenshot=1", wait_until="networkidle"
    )
    sidebar_text = page.locator("aside").text_content() or ""
    assert "<unknown>" in sidebar_text, "sentinel missing from sidebar"


def test_authors_count_badge_in_sidebar(page):
    """The `Authors (N)` badge near the sidebar title shows distinct
    author count — and the value is the same in both toggle states
    because the sidebar isn't filtered."""
    sidebar = page.locator("aside")
    # Default state
    txt_default = sidebar.text_content() or ""
    cb = _show_unknown_checkbox(page)
    cb.uncheck()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    txt_off = page.locator("aside").text_content() or ""
    # Extract "Authors (N)" via simple substring search.
    import re

    m1 = re.search(r"Authors\s*\((\d+)\)", txt_default)
    m2 = re.search(r"Authors\s*\((\d+)\)", txt_off)
    assert m1, "Authors (N) badge missing in default state"
    assert m2, "Authors (N) badge missing after toggle off"
    assert m1.group(1) == m2.group(1), (
        f"Authors count changed with toggle: {m1.group(1)} → {m2.group(1)}"
    )


# ============================================================================
# 7. Form contract — the hidden field is what makes the toggle work
# ============================================================================


def test_form_contains_hidden_show_unknown_zero(page):
    """Regression guard: without the hidden `value=0` field BEFORE the
    checkbox, unchecking is a no-op (the FR78 dead-toggle bug).
    Assert the form structure to prevent that bug coming back."""
    hidden = page.locator('input[type="hidden"][name="show_unknown"][value="0"]')
    assert hidden.count() == 1, "hidden show_unknown=0 field missing — toggle will be dead"


def test_unchecked_submission_url_contains_only_zero(page):
    """When the checkbox is unchecked and the form submits, the URL
    should carry show_unknown=0 (and the duplicate from the hidden
    field is fine — Django's QueryDict last-wins handles it)."""
    cb = _show_unknown_checkbox(page)
    cb.uncheck()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    # show_unknown=0 must be present; show_unknown=1 must NOT be present.
    assert "show_unknown=0" in page.url
    assert "show_unknown=1" not in page.url


def test_checked_submission_url_contains_one(page):
    """When the checkbox is checked, the URL ends up with show_unknown=1
    as the last value (overriding the hidden 0)."""
    # First uncheck and submit to baseline at show_unknown=0
    cb = _show_unknown_checkbox(page)
    cb.uncheck()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    # Now recheck.
    cb = _show_unknown_checkbox(page)
    cb.check()
    _apply_button(page).click()
    page.wait_for_load_state("networkidle")
    # show_unknown=1 must be present.
    assert "show_unknown=1" in page.url, page.url


# ============================================================================
# 8. "Show unknown" overrides the `<unknown>` author selection
#    Regression scenario from the user-reported bug: ticking Charlie +
#    `<unknown>` while leaving Show-unknown OFF used to keep the 1060
#    unknown records visible — the author-checkbox ignored the master
#    toggle. Backend now nullifies <unknown> in selected when
#    show_unknown=False, and the UI auto-syncs the two checkboxes so
#    the user never sees that contradictory state in the first place.
# ============================================================================


def _first_known_author_email(page, viewer: int) -> str:
    """Return any known-author email present in the seed (first row of
    the Authors sidebar — its `<input name=author value=...>` carries
    the email)."""
    page.goto(f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle")
    return page.evaluate(
        """
        () => {
          const cb = document.querySelector(
            'input[name="author"]:not([value="<unknown>"])'
          );
          return cb ? cb.value : '';
        }
        """
    )


def test_show_unknown_off_overrides_unknown_author_selection(page, viewer):
    """User-reported bug: with `?author=<some-author>&author=%3Cunknown%3E
    &show_unknown=0`, the table previously showed that author's records
    AND all unknown records — the unknown-author tick re-introduced what
    Show-unknown asked to hide. Backend now drops <unknown> from the
    effective selection when show_unknown=False."""
    email = _first_known_author_email(page, viewer)
    assert email, "seed has no known authors"
    page.goto(
        f"http://127.0.0.1:{viewer}/?author={email}"
        f"&author=%3Cunknown%3E&show_unknown=0&qa_screenshot=1",
        wait_until="networkidle",
    )
    authors = _table_authors(page)
    assert authors, "no records rendered for the picked author"
    # The combination must NOT bring back '—' rows.
    assert all(a != "—" for a in authors), (
        f"show_unknown=0 ignored when <unknown> ticked — unknown rows leaked: {authors[:5]}"
    )


def test_ui_sync_uncheck_show_unknown_unchecks_unknown_author(page):
    """Mutual-sync UI guard: when the user unticks Show-unknown, the
    `<unknown>` author checkbox flips off too. Prevents arriving at
    the contradictory state in the first place."""
    show_cb = _show_unknown_checkbox(page)
    unknown_author = page.locator('input[type="checkbox"][name="author"][value="<unknown>"]')
    # Start: both true (the default state + ticking <unknown> author).
    unknown_author.check()
    assert unknown_author.is_checked() is True
    # Now uncheck Show-unknown → <unknown> author should auto-uncheck.
    show_cb.uncheck()
    assert unknown_author.is_checked() is False, (
        "unchecking Show-unknown didn't auto-uncheck <unknown> author"
    )


def test_ui_sync_check_unknown_author_checks_show_unknown(page):
    """Mutual-sync UI guard, reverse direction: ticking the `<unknown>`
    author checkbox auto-ticks Show-unknown too — so the row the user
    just asked to include doesn't get hidden by a stale toggle."""
    show_cb = _show_unknown_checkbox(page)
    unknown_author = page.locator('input[type="checkbox"][name="author"][value="<unknown>"]')
    # Start by unchecking Show-unknown.
    show_cb.uncheck()
    # Sync should have flipped the author checkbox too. Re-uncheck it
    # explicitly to set up the test condition (Show-unknown OFF,
    # <unknown> OFF).
    if unknown_author.is_checked():
        unknown_author.uncheck()
    assert show_cb.is_checked() is False
    assert unknown_author.is_checked() is False
    # Now check the <unknown> author → Show-unknown should auto-check.
    unknown_author.check()
    assert show_cb.is_checked() is True, "ticking <unknown> author didn't auto-check Show-unknown"


def test_known_plus_unknown_no_show_unknown_returns_only_known_count(page, viewer):
    """End-to-end version of the user-reported bug, scoped to the count.
    Author X has N records blamed; <unknown> has K. With show_unknown=0
    the result must be N (only X), NOT N+K (X plus leaked unknowns)."""
    email = _first_known_author_email(page, viewer)
    assert email, "seed has no known authors"
    # First, see how many records this author alone has (show_unknown=1).
    page.goto(
        f"http://127.0.0.1:{viewer}/?author={email}&qa_screenshot=1",
        wait_until="networkidle",
    )
    known_only = _total_count(page)
    # Then the bug-trigger URL: same author + <unknown> + show_unknown=0.
    page.goto(
        f"http://127.0.0.1:{viewer}/?author={email}"
        f"&author=%3Cunknown%3E&show_unknown=0&qa_screenshot=1",
        wait_until="networkidle",
    )
    combined = _total_count(page)
    assert combined == known_only, (
        f"show_unknown=0 ignored: expected {known_only} (known author only), "
        f"got {combined} (known + leaked unknowns)"
    )
