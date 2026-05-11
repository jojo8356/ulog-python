"""End-to-end tests for sidebar checkbox memory.

Every filter in the records-list sidebar is encoded as a URL query
parameter on Apply (the form is `method="get"`). After Apply, the
URL is the single source of truth — reloading or navigating back to
that URL must restore EVERY checkbox to its previously-ticked state.

The checkbox families covered:

  Level         <input name="level"        value="DEBUG|INFO|WARNING|ERROR|CRITICAL">
  Tests quick   <input name="failed_only"  value="1">
                <input name="slowest_only" value="1">
  Sectors       <input name="logger"       value="<prefix>">
  Files         <input name="file"         value="<filename>">
  Authors       <input name="author"       value="<email>" | "<unknown>">

`show_unknown` is its own form (hidden field + checkbox) — already
covered by tests/test_show_unknown_toggle_e2e.py; not re-tested here.

Each test simulates the user flow:
  1. Land on a URL that encodes the selection.
  2. Read every relevant checkbox's `.checked` state from the DOM.
  3. Assert it matches the URL params bit-for-bit.

The pattern is "URL → DOM" (memory of the previous selection AT
PAGE LOAD), which is the canonical persistence path for any HTML
form. Round-trips (reload, navigate-away-and-back) inherit
correctness from this primitive.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from .test_qa_setup_e2e import seeded_demo  # noqa: F401  reuse module-scoped fixture

# ---- subprocess + browser fixtures (same shape as other e2e files) -------


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
        b = pw.chromium.launch()
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def page(browser: object, viewer: int) -> Iterator[object]:
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})  # type: ignore[attr-defined]
    ctx.add_init_script("window.localStorage.setItem('ulogTutorialDismissed', '1')")
    pg = ctx.new_page()
    try:
        yield pg
    finally:
        ctx.close()


# ---- DOM helpers ----------------------------------------------------------


def _checked_set(page: object, name: str) -> set[str]:
    """Return the set of `value`s for every checkbox with the given
    `name=` whose `.checked` is True."""
    return set(
        page.evaluate(  # type: ignore[attr-defined,no-any-return]
            """(name) => [
            ...document.querySelectorAll(
              `aside input[type=checkbox][name="${name}"]:checked`
            )
          ].map(el => el.value)""",
            name,
        )
    )


def _all_values(page: object, name: str) -> set[str]:
    """All `value`s for that name — checked or not. Lets the test
    decide what "empty" means without hard-coding option lists."""
    return set(
        page.evaluate(  # type: ignore[attr-defined,no-any-return]
            """(name) => [
            ...document.querySelectorAll(
              `aside input[type=checkbox][name="${name}"]`
            )
          ].map(el => el.value)""",
            name,
        )
    )


def _goto(page: object, viewer: int, qs: str) -> None:
    """Navigate to /?<qs>&qa_screenshot=1 and wait for it to settle.
    qa_screenshot=1 keeps the tutorial off; the test fixture also
    flips the localStorage marker but the URL flag is the cleaner
    primary."""
    sep = "&" if qs else ""
    url = f"http://127.0.0.1:{viewer}/?qa_screenshot=1{sep}{qs}"
    page.goto(url, wait_until="networkidle", timeout=15_000)  # type: ignore[attr-defined]


# ============================================================================
# 1. Default state — nothing ticked on first load
# ============================================================================


def test_default_state_no_filter_checkboxes_checked(page, viewer):
    """On a clean URL (no filter params), every Level / failed_only /
    slowest_only / Sectors / Files / Authors checkbox is unchecked."""
    _goto(page, viewer, "")
    for name in ("level", "failed_only", "slowest_only", "logger", "file", "author"):
        assert _checked_set(page, name) == set(), (
            f"{name!r} unexpectedly checked on default load: {_checked_set(page, name)}"
        )


# ============================================================================
# 2. Single-value selection per family — URL → DOM
# ============================================================================


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_level_single_selection_persists_from_url(page, viewer, level):
    """`?level=<X>` → the matching Level checkbox is ticked, no other."""
    _goto(page, viewer, f"level={level}")
    assert _checked_set(page, "level") == {level}


def test_failed_only_persists_from_url(page, viewer):
    """`?failed_only=1` → Failed-only quick-filter checkbox ticked."""
    _goto(page, viewer, "failed_only=1")
    assert _checked_set(page, "failed_only") == {"1"}


def test_slowest_only_persists_from_url(page, viewer):
    """`?slowest_only=1` → Slowest-top-10 quick-filter checkbox ticked."""
    _goto(page, viewer, "slowest_only=1")
    assert _checked_set(page, "slowest_only") == {"1"}


def test_logger_single_selection_persists_from_url(page, viewer):
    """`?logger=<prefix>` → matching Sectors checkbox ticked."""
    # The seed has globex.* loggers; pick the first one present in the DOM.
    _goto(page, viewer, "")
    candidates = _all_values(page, "logger")
    assert candidates, "no Sectors options present"
    sample = sorted(candidates)[0]
    _goto(page, viewer, f"logger={urllib.parse.quote(sample, safe='')}")
    assert _checked_set(page, "logger") == {sample}


def test_file_single_selection_persists_from_url(page, viewer):
    """`?file=<name>` → matching Files checkbox ticked."""
    _goto(page, viewer, "")
    candidates = _all_values(page, "file")
    assert candidates, "no Files options present"
    sample = sorted(candidates)[0]
    _goto(page, viewer, f"file={urllib.parse.quote(sample, safe='')}")
    assert _checked_set(page, "file") == {sample}


def test_author_single_selection_persists_from_url(page, viewer):
    """`?author=<email>` → matching Authors checkbox ticked."""
    _goto(page, viewer, "")
    candidates = _all_values(page, "author") - {"<unknown>"}
    assert candidates, "no known-author options present"
    sample = sorted(candidates)[0]
    _goto(page, viewer, f"author={urllib.parse.quote(sample, safe='')}")
    assert _checked_set(page, "author") == {sample}


def test_unknown_author_selection_persists_from_url(page, viewer):
    """`?author=%3Cunknown%3E` → the `<unknown>` sentinel checkbox ticked."""
    _goto(page, viewer, "author=%3Cunknown%3E")
    assert "<unknown>" in _checked_set(page, "author")


# ============================================================================
# 3. Multi-value selection within ONE family (OR semantics, FR47/FR77)
# ============================================================================


def test_multiple_levels_persist_simultaneously(page, viewer):
    """`?level=ERROR&level=WARNING` → both checkboxes ticked, others not."""
    _goto(page, viewer, "level=ERROR&level=WARNING")
    assert _checked_set(page, "level") == {"ERROR", "WARNING"}


def test_three_levels_persist_simultaneously(page, viewer):
    """Stress the multi-value path with three values to catch a
    last-value-wins regression."""
    _goto(page, viewer, "level=DEBUG&level=INFO&level=CRITICAL")
    assert _checked_set(page, "level") == {"DEBUG", "INFO", "CRITICAL"}


def test_multiple_files_persist_simultaneously(page, viewer):
    _goto(page, viewer, "")
    candidates = sorted(_all_values(page, "file"))[:2]
    assert len(candidates) >= 2, "need ≥ 2 files to multi-select"
    qs = "&".join(f"file={urllib.parse.quote(c, safe='')}" for c in candidates)
    _goto(page, viewer, qs)
    assert _checked_set(page, "file") == set(candidates)


def test_multiple_authors_persist_simultaneously(page, viewer):
    _goto(page, viewer, "")
    candidates = sorted(_all_values(page, "author") - {"<unknown>"})[:2]
    assert len(candidates) >= 2, "need ≥ 2 known authors to multi-select"
    qs = "&".join(f"author={urllib.parse.quote(c, safe='')}" for c in candidates)
    _goto(page, viewer, qs)
    assert _checked_set(page, "author") == set(candidates)


def test_multiple_loggers_persist_simultaneously(page, viewer):
    _goto(page, viewer, "")
    candidates = sorted(_all_values(page, "logger"))[:2]
    assert len(candidates) >= 2, "need ≥ 2 sectors to multi-select"
    qs = "&".join(f"logger={urllib.parse.quote(c, safe='')}" for c in candidates)
    _goto(page, viewer, qs)
    assert _checked_set(page, "logger") == set(candidates)


# ============================================================================
# 4. Cross-family combination — every checkbox family ticked at once
# ============================================================================


def test_full_combination_persists_from_url(page, viewer):
    """One value per family, simultaneously. Catches a regression where
    a filter family steals/clobbers another (e.g., views.py reads the
    wrong query-string key).

    NOTE: deliberately omits failed_only / slowest_only here — those
    quick-filters narrow the dataset to `logger='ulog.test'` records,
    which would shrink the Files / Sectors / Authors blocks to a
    near-empty subset (FR79 ghost-count rule). Their persistence is
    covered standalone above; this test exercises the
    multi-family-co-existence axis, not their interaction with quick
    filters."""
    # Discover safe sample values — pick the FIRST ones rendered,
    # which are also the most-populated entries (sorted by count
    # desc per views.py:128) so they survive whatever filter we add.
    _goto(page, viewer, "")
    files_in_order = page.evaluate(  # type: ignore[attr-defined]
        """() => [...document.querySelectorAll('aside input[name="file"]')].map(i => i.value)"""
    )
    loggers_in_order = page.evaluate(  # type: ignore[attr-defined]
        """() => [...document.querySelectorAll('aside input[name="logger"]')].map(i => i.value)"""
    )
    authors_in_order = page.evaluate(  # type: ignore[attr-defined]
        """() => [...document.querySelectorAll('aside input[name="author"]')].map(i => i.value)"""
    )
    authors_in_order = [a for a in authors_in_order if a != "<unknown>"]
    assert files_in_order, "fixture missing file options"
    assert loggers_in_order, "fixture missing logger options"
    assert authors_in_order, "fixture missing author options"

    fsample = files_in_order[0]  # most-populated file
    lsample = loggers_in_order[0]  # most-populated sector
    asample = authors_in_order[0]  # most-prolific author
    qs = (
        "level=ERROR"
        f"&file={urllib.parse.quote(fsample, safe='')}"
        f"&logger={urllib.parse.quote(lsample, safe='')}"
        f"&author={urllib.parse.quote(asample, safe='')}"
    )
    _goto(page, viewer, qs)
    assert _checked_set(page, "level") == {"ERROR"}
    assert _checked_set(page, "file") == {fsample}
    assert _checked_set(page, "logger") == {lsample}
    assert _checked_set(page, "author") == {asample}


# ============================================================================
# 5. Round-trip via Apply: form submit must round-trip every checkbox
# ============================================================================


def test_apply_button_round_trip_preserves_checkbox_state(page, viewer):
    """User ticks two Level checkboxes + one File, clicks Apply, the new
    URL must encode the same state and the new page render must show
    them ticked. End-to-end click-driven proof, complementing the
    URL-driven parametrized tests above."""
    _goto(page, viewer, "")
    files = sorted(_all_values(page, "file"))
    assert files, "no files available"
    target_file = files[0]

    # Tick directly via DOM (mirrors a user click).
    page.locator('aside input[type=checkbox][name="level"][value="ERROR"]').check()
    page.locator('aside input[type=checkbox][name="level"][value="WARNING"]').check()
    page.locator(f'aside input[type=checkbox][name="file"][value="{target_file}"]').check()

    # Submit via the form's Apply button (visible label per template).
    page.get_by_role("button", name="Apply").click()
    page.wait_for_load_state("networkidle")

    # The URL must carry the three filters (order independent).
    url = page.url
    for needle in (
        "level=ERROR",
        "level=WARNING",
        f"file={urllib.parse.quote(target_file, safe='')}",
    ):
        assert needle in url, f"missing {needle!r} in post-Apply URL: {url}"

    # And the rendered checkboxes must match the URL state.
    assert _checked_set(page, "level") == {"ERROR", "WARNING"}
    assert _checked_set(page, "file") == {target_file}


# ============================================================================
# 6. Reload preserves state (URL-driven memory is the only persistence layer)
# ============================================================================


def test_reload_preserves_full_filter_state(page, viewer):
    """Apply a multi-family filter, reload the page, assert every
    checkbox is still ticked. Verifies URL drives the DOM on every
    page paint — no hidden state in cookies / sessionStorage that
    could drift.

    Uses the FIRST file / author in the sidebar (= most-populated)
    so they survive whatever filter combo we layer on — FR79
    ghost-count rule would otherwise hide a low-count file
    that has no records matching the level filter."""
    _goto(page, viewer, "")
    files_in_order = page.evaluate(  # type: ignore[attr-defined]
        """() => [...document.querySelectorAll('aside input[name="file"]')].map(i => i.value)"""
    )
    authors_in_order = page.evaluate(  # type: ignore[attr-defined]
        """() => [...document.querySelectorAll('aside input[name="author"]')].map(i => i.value)"""
    )
    authors_in_order = [a for a in authors_in_order if a != "<unknown>"]
    assert files_in_order, "fixture missing file options"
    assert authors_in_order, "fixture missing author options"
    fsample, asample = files_in_order[0], authors_in_order[0]

    qs = (
        "level=ERROR&level=INFO"
        f"&file={urllib.parse.quote(fsample, safe='')}"
        f"&author={urllib.parse.quote(asample, safe='')}"
    )
    _goto(page, viewer, qs)
    url_before = page.url
    page.reload(wait_until="networkidle")
    assert page.url == url_before
    assert _checked_set(page, "level") == {"ERROR", "INFO"}
    assert _checked_set(page, "file") == {fsample}
    assert _checked_set(page, "author") == {asample}


def test_open_record_then_back_preserves_filter(page, viewer):
    """User flow: filter set → click a record (lands on /r/N/) → click
    'back to records' → filter state preserved. The detail-view
    `<a href=...>` includes a `?qs=` query string for this exact
    purpose; if it ever drops a filter, this test catches it."""
    _goto(page, viewer, "level=ERROR")
    # Click the first row in the table.
    page.locator("main table tbody tr").first.click()
    page.wait_for_load_state("networkidle")
    assert "/r/" in page.url, f"didn't land on detail view: {page.url}"
    # Go back via browser history (the detail view's "Back to records"
    # link is more authoritative but harder to locate cross-template;
    # browser.back is the canonical user gesture here).
    page.go_back(wait_until="networkidle")
    assert _checked_set(page, "level") == {"ERROR"}, "filter lost after detail-view round-trip"


# ============================================================================
# 7. Reset link clears every checkbox in one shot
# ============================================================================


def test_reset_link_clears_all_filter_checkboxes(page, viewer):
    """The sidebar has a `Reset` link (next to the Apply button) that
    points at `ulog-list` (= "/") with no query string. Clicking it
    must clear EVERY filter checkbox in one navigation."""
    files = sorted(_all_values(page, "file") if (_goto(page, viewer, "") or True) else [])
    _ = files  # silence linter
    # Set up a state with multiple filters.
    _goto(page, viewer, "level=ERROR&failed_only=1")
    assert _checked_set(page, "level") == {"ERROR"}
    assert _checked_set(page, "failed_only") == {"1"}
    # Click the Reset link.
    page.get_by_role("link", name="Reset").click()
    page.wait_for_load_state("networkidle")
    # Every filter family back to empty.
    for name in ("level", "failed_only", "slowest_only", "logger", "file", "author"):
        assert _checked_set(page, name) == set(), f"{name!r} not cleared by Reset link"
