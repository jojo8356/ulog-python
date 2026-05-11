"""End-to-end security tests for the `/diff/<sha>/` view (Story 2.9 / FR81 / NFR-SEC-30).

Replaces the manual `§2.5 — paste in URL bar` checklist items with
deterministic assertions against a live viewer subprocess. Same shape
as tests/test_qa_perf_e2e.py: spawn one viewer per module, hit the
viewer over HTTP, assert status codes + body shape.

These tests are intentionally orthogonal to tests/test_diff_view.py
(which uses Django's in-process test client). They prove the security
contract holds through the FULL request stack (URL parser, Django
middleware, the view, the subprocess call to `git`) — exactly what
the QA item description "paste in URL bar" means.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
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


def _http_get(port: int, path: str) -> tuple[int, str]:
    """GET path and return (status_code, body). Handles non-2xx without raising."""
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, body


# ---- module-scoped viewer subprocess --------------------------------------


@pytest.fixture(scope="module")
def viewer(seeded_demo: Path) -> Iterator[int]:  # noqa: F811
    """One viewer subprocess shared across all tests in this module.

    Uses the seeded_demo fixture (the same one tests/test_qa_perf_e2e.py
    uses), which builds a real git repo under tmp_path with several
    commits so the valid-sha case has SOMETHING to resolve against.
    """
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


# ============================================================================
# §2.5 security checklist items — each maps to one QA AC
# ============================================================================


# ---- e2-2.5-sec-1 — `/diff/abc/` (too short) → 400 Bad Request ----------


def test_diff_too_short_sha_returns_400(viewer):
    """The `<str:sha>` URL converter accepts 'abc' but `_validate_sha`
    rejects it: the regex `^[0-9a-f]{4,40}$` requires ≥ 4 chars."""
    status, body = _http_get(viewer, "/diff/abc/")
    assert status == 400, f"expected 400 for short sha, got {status}: {body[:200]}"
    assert "invalid sha" in body.lower(), f"missing 'invalid sha' marker: {body[:200]}"


def test_diff_3_char_sha_returns_400(viewer):
    """Boundary: 'a' / 'ab' / 'abc' all under the 4-char minimum."""
    for short in ("a", "ab", "abc"):
        status, _body = _http_get(viewer, f"/diff/{short}/")
        assert status == 400, f"len-{len(short)} sha {short!r} should 400, got {status}"


# ---- e2-2.5-sec-2 — `/diff/abc;rm/` (shell chars) → 400 -----------------


def test_diff_shell_metachar_semicolon_returns_400(viewer):
    """Non-hex chars (here `;` + `r` + `m`) rejected — first line of
    defense against shell injection via the URL path."""
    status, body = _http_get(viewer, "/diff/abc;rm/")
    assert status == 400, f"shell-char sha should 400, got {status}: {body[:200]}"


def test_diff_shell_metachars_battery_all_return_400(viewer):
    """Battery of common shell metacharacters that MUST never reach a
    subprocess argv. NFR-SEC-30."""
    cases = [
        "abc;rm",  # command chaining
        "abc&ls",  # background
        "abc|cat",  # pipe
        "abc`cat`",  # backtick
        "abc$PATH",  # variable expansion
        "abc..%2f",  # encoded path traversal
        "abc/etc",  # path separator
        "abc\\nrm",  # newline injection
        "abc'or'1",  # quote
    ]
    for sha in cases:
        # urllib.quote keeps a few chars; the URL converter receives
        # the raw byte sequence which `_validate_sha` re-checks.
        status, _ = _http_get(viewer, f"/diff/{urllib.request.quote(sha, safe='')}/")
        assert status in (400, 404), f"{sha!r} should be rejected (400/404), got {status}"


# ---- e2-2.5-sec-3 — `/diff/0000…0000/` (valid hex unreachable) → 404 ----


def test_diff_valid_hex_unreachable_sha_returns_404(viewer):
    """40-char hex sha that parses cleanly but doesn't exist in the
    repo. `_validate_sha` lets it through; `git rev-parse --verify`
    rejects it; view returns 404."""
    status, body = _http_get(viewer, "/diff/0000000000000000000000000000000000000000/")
    assert status == 404, f"unreachable sha should 404, got {status}: {body[:200]}"
    assert "not reachable" in body.lower(), f"missing 'not reachable': {body[:200]}"


def test_diff_almost_real_sha_returns_404(viewer):
    """A 7-char-ish hex string that looks like a short sha but isn't
    in the repo also 404s (rev-parse handles short shas, just not
    bogus ones)."""
    status, _body = _http_get(viewer, "/diff/deadbeef/")
    assert status == 404, f"non-existent short sha should 404, got {status}"


# ---- e2-2.5-3 — HTML escape in rendered diff (test with `<` or `>`) ----


def test_diff_html_escapes_commit_message_and_content(viewer, seeded_demo, tmp_path):  # noqa: F811
    """Decision D4 — Django auto-escape kicks in on the rendered
    `<pre>` block. Inject a commit with HTML-like content + message
    into the seeded repo and assert it comes back escaped.

    Test isolates by adding a NEW commit (doesn't mutate the seed's
    history): clean rollback after the test."""
    sha_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=seeded_demo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # Inject a file with HTML-like content.
    evil = seeded_demo / "evil-xss.py"
    evil.write_text("<script>alert('xss')</script>\n# <h1>bad</h1>\n", encoding="utf-8")
    subprocess.run(["git", "add", "evil-xss.py"], cwd=seeded_demo, check=True)
    # Commit with HTML-like message.
    subprocess.run(
        ["git", "commit", "-q", "-m", "<script>evil commit</script>"],
        cwd=seeded_demo,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
        check=True,
    )
    new_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=seeded_demo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    try:
        status, body = _http_get(viewer, f"/diff/{new_sha}/")
        assert status == 200, f"diff for newly-added commit should 200, got {status}"
        # The dangerous payload MUST NOT appear as raw HTML.
        assert "<script>alert" not in body, "raw <script> leaked into rendered HTML — XSS!"
        # Escaped form MUST appear (commit message + file content).
        assert "&lt;script&gt;" in body or "&#x3C;script&#x3E;" in body, (
            "expected HTML-escaped <script> marker in body"
        )
    finally:
        # Rewind the demo repo to its pre-test state.
        subprocess.run(
            ["git", "reset", "--hard", sha_before],
            cwd=seeded_demo,
            capture_output=True,
            check=True,
        )
        # Clean up the file too (in case `reset --hard` left it untracked).
        if evil.exists():
            evil.unlink()


# ---- Bonus regression guards ---------------------------------------------


def test_diff_uppercase_hex_rejected_by_validator(viewer):
    """`_validate_sha` uses lower-case [0-9a-f] only. Git itself
    accepts uppercase shas, but ULog normalizes — we reject uppercase
    at the URL boundary so the security check has ONE canonical form
    to reason about."""
    status, _ = _http_get(viewer, "/diff/ABCDEF1234/")
    # Either 400 (re.match rejects) or 404 (rev-parse fails) is fine
    # for this regression — the key check is "no 500".
    assert status in (400, 404), f"uppercase hex should be 400/404, got {status}"


def test_diff_empty_sha_returns_404_not_500(viewer):
    """`/diff//` — empty sha. The route shouldn't 500."""
    status, _ = _http_get(viewer, "/diff//")
    # Django typically 404s missing path segments. Anything other
    # than 5xx is acceptable.
    assert status < 500, f"empty sha caused server error: {status}"


# ============================================================================
# §2.5 happy-path rendering (e2-2.5-1 + e2-2.5-2)
# ============================================================================


def _head_sha(repo: Path) -> str:
    """Return the current HEAD sha of the demo repo."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_diff_valid_sha_renders_full_git_show_in_pre_monospace(viewer, seeded_demo):  # noqa: F811
    """e2-2.5-1 — Clicking 'view diff' lands on /diff/<sha>/ which renders
    the FULL `git show <sha>` output inside a `<pre>` block with
    monospace + whitespace-preserved styling per Decision D4."""
    sha = _head_sha(seeded_demo)
    status, body = _http_get(viewer, f"/diff/{sha}/")
    assert status == 200, f"valid sha should 200, got {status}"

    # The <pre> block carries Tailwind classes the architecture pins:
    # font-mono (monospace) + whitespace-pre (no collapsing) +
    # overflow-x-auto (long lines scroll). Marker attribute
    # data-diff-content="true" lets tests/template asserts pin it down.
    assert 'data-diff-content="true"' in body, "diff <pre> marker missing"
    # Each Tailwind class on the same element — explicit, deliberate.
    for cls in ("font-mono", "whitespace-pre", "overflow-x-auto"):
        assert cls in body, f"diff <pre> missing class {cls!r}"

    # The `git show` payload itself must be visible: header line +
    # at least one `diff --git` chunk + the commit message.
    assert "commit " + sha in body, "full sha header line missing from rendered diff"
    assert "diff --git" in body, "no diff hunks rendered"
    assert "Author:" in body, "commit Author header missing"
    assert "Date:" in body, "commit Date header missing"


def test_diff_page_has_back_to_records_link_in_header(viewer, seeded_demo):  # noqa: F811
    """e2-2.5-2 — The diff page header carries a `← back to records` link
    pointing at the root `/` (records list)."""
    sha = _head_sha(seeded_demo)
    status, body = _http_get(viewer, f"/diff/{sha}/")
    assert status == 200, f"valid sha should 200, got {status}"

    # The text is literal in diff.html; the href resolves through the
    # `ulog-list` URL name (= "/"). Check both the visible label AND
    # the link target to catch a regression that renames either.
    assert "← back to records" in body, "back-to-records link label missing"
    # The link is `<a href="/" ...>` once the {% url %} tag resolves.
    # Match the most-specific anchor pattern to avoid catching any
    # unrelated `href="/"` further down.
    assert 'href="/"' in body, "back link href to / missing"
    # And it's wrapped in an <a> tag styled as a link (blue + hover).
    assert "text-blue-600" in body, "back link missing blue styling"
    assert "hover:underline" in body, "back link missing hover-underline styling"


def test_diff_page_short_sha_in_h1(viewer, seeded_demo):  # noqa: F811
    """The h1 shows `git show <short-sha>` where short-sha is 7 chars —
    visual confirmation the page is about the right commit."""
    sha = _head_sha(seeded_demo)
    status, body = _http_get(viewer, f"/diff/{sha}/")
    assert status == 200
    assert f"git show {sha[:7]}" in body, "h1 missing short-sha header"
