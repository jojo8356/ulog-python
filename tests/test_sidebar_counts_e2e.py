"""End-to-end stability tests for sidebar count semantics (FR79 ghost counts).

Investigates the user-reported confusion: "au début il y a pas bcp de
files et après les chiffres à gauches des texts changent + le nombre
de files change". Two competing hypotheses:

  (a) Real bug — file_counts fluctuate across identical GETs (e.g., a
      cache warm-up race, or pagination silently affecting counts).
  (b) Expected behavior misread by the user — FR79 ghost-count rule
      shrinks the file list when filters reduce matching records,
      which IS deliberate but visually surprising.

This file codifies the contract so any future regression that breaks
either invariant is caught immediately.
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


# ---- DOM extractors -------------------------------------------------------


_FILES_JS = """
() => {
  const headers = [...document.querySelectorAll('aside h3')];
  const filesH = headers.find(h => h.textContent.trim().startsWith('Files'));
  if (!filesH) return null;
  const block = filesH.parentElement;
  return [...block.querySelectorAll('label')].map(l => ({
    value: l.querySelector('input[type=checkbox]')?.value || '?',
    count: parseInt(
      (l.querySelector('span.ml-auto') || l.querySelectorAll('span')[1])?.textContent?.trim() || '0',
      10,
    ),
  }));
}
"""


_SECTORS_JS = """
() => {
  const headers = [...document.querySelectorAll('aside h3')];
  const h = headers.find(x => x.textContent.trim().startsWith('Sectors'));
  if (!h) return null;
  const block = h.parentElement;
  return [...block.querySelectorAll('label')].map(l => ({
    value: l.querySelector('input[type=checkbox]')?.value || '?',
    count: parseInt(
      (l.querySelector('span.ml-auto') || l.querySelectorAll('span')[1])?.textContent?.trim() || '0',
      10,
    ),
  }));
}
"""


def _files(page: object) -> list[dict]:
    return page.evaluate(_FILES_JS)  # type: ignore[no-any-return,attr-defined]


def _sectors(page: object) -> list[dict]:
    return page.evaluate(_SECTORS_JS)  # type: ignore[no-any-return,attr-defined]


# ============================================================================
# 1. Stability across identical GETs (no random fluctuation)
# ============================================================================


def test_files_block_identical_across_5_fresh_loads(page, viewer):
    """Five back-to-back navigations to / must produce the SAME files list
    in the SAME order with the SAME counts. Catches: cache warm-up race,
    nondeterministic SQL ORDER BY, indexer-completion-side effects."""
    snaps = []
    for i in range(5):
        page.goto(
            f"http://127.0.0.1:{viewer}/?qa_screenshot=1&_={i}",
            wait_until="networkidle",
            timeout=15_000,
        )
        snaps.append(_files(page))
    # Every snap must equal the first one — bitwise.
    base = snaps[0]
    assert base, "no Files block rendered on baseline"
    for i, s in enumerate(snaps[1:], start=1):
        assert s == base, (
            f"Files block differed between fresh-load #0 and #{i}.\n#0: {base[:5]}\n#{i}: {s[:5]}"
        )


def test_sectors_block_identical_across_5_fresh_loads(page, viewer):
    """Same invariant for the Sectors block."""
    snaps = []
    for i in range(5):
        page.goto(
            f"http://127.0.0.1:{viewer}/?qa_screenshot=1&_={i}",
            wait_until="networkidle",
            timeout=15_000,
        )
        snaps.append(_sectors(page))
    base = snaps[0]
    assert base, "no Sectors block rendered"
    for i, s in enumerate(snaps[1:], start=1):
        assert s == base, (
            f"Sectors block differed between fresh-load #0 and #{i}.\n#0: {base[:5]}\n#{i}: {s[:5]}"
        )


# ============================================================================
# 2. Pagination MUST NOT change file_counts (FR79 ghost-count rule)
# ============================================================================


def test_pagination_does_not_change_files_block(page, viewer):
    """Navigating to ?page=2 / ?page=N must NOT alter the Files block —
    file_counts are computed over the FULL filtered dataset, not just
    the current page's records. Anything else is an FR79 regression."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    baseline = _files(page)
    for p in (2, 5, 10):
        page.goto(
            f"http://127.0.0.1:{viewer}/?page={p}&qa_screenshot=1",
            wait_until="networkidle",
            timeout=15_000,
        )
        cur = _files(page)
        assert cur == baseline, (
            f"Files block changed when navigating to page={p} — pagination "
            f"should NOT affect file_counts (FR79).\n"
            f"baseline first 3: {baseline[:3]}\n"
            f"page={p} first 3: {cur[:3]}"
        )


def test_pagination_does_not_change_sectors_block(page, viewer):
    """Same invariant for Sectors."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    baseline = _sectors(page)
    page.goto(
        f"http://127.0.0.1:{viewer}/?page=2&qa_screenshot=1",
        wait_until="networkidle",
        timeout=15_000,
    )
    assert _sectors(page) == baseline, "Sectors changed with pagination"


# ============================================================================
# 3. Filter-induced shrinkage IS expected (and is what users see)
# ============================================================================


def test_zero_match_search_shrinks_files_to_empty(page, viewer):
    """A search that matches no record empties the Files block — confirms
    the user's observation that "the number of files changes" is the
    designed FR79 behavior, not a stability bug."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?q=zzz-no-such-token-zzz&qa_screenshot=1",
        wait_until="networkidle",
        timeout=15_000,
    )
    files = _files(page)
    assert files == [], f"no-match search should empty the Files block; got {len(files)} entries"


def test_critical_level_filter_can_drop_files_without_critical_records(page, viewer):
    """Files with zero CRITICAL records disappear from the Files block when
    level=CRITICAL is active — confirms FR79 ghost-count rule."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    baseline = _files(page)
    page.goto(
        f"http://127.0.0.1:{viewer}/?level=CRITICAL&qa_screenshot=1",
        wait_until="networkidle",
        timeout=15_000,
    )
    critical = _files(page)
    assert len(critical) <= len(baseline), (
        f"CRITICAL filter should reduce or keep file count; {len(critical)} > {len(baseline)}"
    )
    # The critical files must be a SUBSET of baseline (no new file appears
    # under a stricter filter).
    base_names = {f["value"] for f in baseline}
    for f in critical:
        assert f["value"] in base_names, (
            f"file {f['value']!r} present with level=CRITICAL but absent "
            f"from baseline — counts are not monotone under filter restriction"
        )


# ============================================================================
# 4. Counts are STRICTLY positive on the rendered list
# ============================================================================


def test_files_block_never_renders_zero_count_rows(page, viewer):
    """Sanity: a file with 0 matching records under the current filter
    must NOT render in the Files block. If a row shows '0', it's a
    rendering bug (the user would see "stale" entries)."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    for f in _files(page):
        assert f["count"] > 0, f"zero-count file leaked into Files block: {f}"


def test_sectors_block_never_renders_zero_count_rows(page, viewer):
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    for s in _sectors(page):
        assert s["count"] > 0, f"zero-count sector leaked: {s}"


# ============================================================================
# 5. Files block is sorted by count desc (stable order)
# ============================================================================


def test_files_block_sorted_by_count_desc(page, viewer):
    """`views.py:128` sorts files by `-kv[1]` (count desc). Verify the
    rendered order matches — catches a regression that flips the sort."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    counts = [f["count"] for f in _files(page)]
    assert counts == sorted(counts, reverse=True), f"files not sorted by count desc: {counts[:10]}"


# ============================================================================
# 6. Total file count matches across filter clears
# ============================================================================


def test_clearing_filter_restores_baseline_files_block(page, viewer):
    """Apply a filter, then navigate back to /. The Files block must
    return to its exact baseline state — no residual filtered state,
    no stale counts."""
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    baseline = _files(page)
    # Apply a filter.
    page.goto(
        f"http://127.0.0.1:{viewer}/?level=ERROR&qa_screenshot=1",
        wait_until="networkidle",
        timeout=15_000,
    )
    _ = _files(page)
    # Clear.
    page.goto(
        f"http://127.0.0.1:{viewer}/?qa_screenshot=1", wait_until="networkidle", timeout=15_000
    )
    after = _files(page)
    assert after == baseline, "Files block didn't restore to baseline after clearing the filter"
