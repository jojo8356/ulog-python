"""QA screenshots generator — captures key viewer URLs into PNG.

Outputs go to `ulog/web/static/ulog/qa-screenshots/<slug>.png` so the
`/_qa/` page can render them inline under each section.

Uses Playwright (chromium) for:
- proper full-page captures (no viewport-height hacks)
- locator-based sub-region shots (sidebar Tests only, etc.)
- narrow-viewport responsive captures

After capture, optionally runs scripts/optimize_screenshots.sh to
shrink the PNGs via pngquant.

Setup (one-time, in venv):
  pip install playwright
  python -m playwright install chromium

Usage:
  python3 scripts/qa_screenshots.py [--demo-dir /tmp/ulog-demo] [--no-optimize]
"""

from __future__ import annotations

import argparse
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "ulog" / "web" / "static" / "ulog" / "qa-screenshots"
OPTIMIZE_SCRIPT = REPO_ROOT / "scripts" / "optimize_screenshots.sh"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, *, timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"viewer never responded on port {port} within {timeout_s}s")


def _discover_ids(demo_dir: Path) -> dict[str, object]:
    """Pull live IDs from the demo DB + git repo so URLs are real."""
    db = demo_dir / "logs.sqlite"
    out: dict[str, object] = {}
    with sqlite3.connect(str(db)) as conn:
        out["first_record_id"] = int(conn.execute("SELECT MIN(id) FROM logs").fetchone()[0])
        row = conn.execute(
            "SELECT id, json_extract(context, '$.test_id') "
            "FROM logs WHERE json_extract(context, '$.test_id') IS NOT NULL LIMIT 1"
        ).fetchone()
        if row:
            out["record_with_test_id"] = int(row[0])
            out["sample_test_id"] = str(row[1])
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=demo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    out["sha"] = proc.stdout.strip()
    return out


def _qs_test_id(test_id: str) -> str:
    """Same encoding as Django's |urlencode on a test_id: '/' kept,
    '::' → '%3A%3A'."""
    return test_id.replace("::", "%3A%3A") if test_id else ""


# ---- Capture catalog -----------------------------------------------------
#
# Each entry: slug → dict(path, desc, kind, **kind-specific args)
#   kind = "full"     — page.screenshot(full_page=True)
#   kind = "viewport" — page.screenshot()  (viewport-only, default size)
#   kind = "narrow"   — viewport=900x700 + page.screenshot()
#   kind = "locator"  — page.locator(selector).screenshot()
# All captures hit ?qa_screenshot=1 to suppress the tutorial overlay
# AND the max-h-60 cap on the Tests sidebar.


def _catalog(ids: dict[str, object]) -> dict[str, dict]:
    test_qs = _qs_test_id(str(ids.get("sample_test_id", "")))
    rec_id = ids.get("record_with_test_id", 1)
    first_id = ids.get("first_record_id", 1)
    sha = ids["sha"]

    return {
        # ------ Full-page (used for doc-pages and detail views) ---------
        "section-1-4": {
            "path": f"/r/{rec_id}/?qa_screenshot=1",
            "kind": "full",
            "desc": "Detail view with Test context + Authored by panels",
        },
        "section-1-5": {
            "path": "/docs/test-integration/?qa_screenshot=1",
            "kind": "full",
            "desc": "Test integration doc page",
        },
        "section-2-4": {
            "path": f"/r/{first_id}/?qa_screenshot=1",
            "kind": "full",
            "desc": "Detail view (Authored by panel)",
        },
        "section-2-5": {
            "path": f"/diff/{sha}/?qa_screenshot=1",
            "kind": "full",
            "desc": "Diff view (git show <sha>)",
        },
        "section-2-6": {
            "path": "/docs/author-filter/?qa_screenshot=1",
            "kind": "full",
            "desc": "Author filter doc page",
        },
        "section-qa": {
            "path": "/_qa/",
            "kind": "viewport",
            "desc": "QA checklist page itself",
        },
        # ------ Viewport-default (records list + sidebars) ---------------
        "section-1-1": {
            "path": "/?qa_screenshot=1",
            "kind": "viewport",
            "desc": "Records list with Tests sidebar block visible",
        },
        "section-1-2": {
            "path": "/?failed_only=1&qa_screenshot=1",
            "kind": "viewport",
            "desc": "Failed-only quick filter active",
        },
        "section-1-3": {
            "path": f"/?test_id={test_qs}&qa_screenshot=1",
            "kind": "viewport",
            "desc": "Records filtered by test_id (mix of ulog.test + globex.*)",
        },
        "section-2-1": {
            "path": "/?qa_screenshot=1",
            "kind": "viewport",
            "desc": "Authors sidebar (8 authors + <unknown>)",
        },
        "section-2-3": {
            "path": "/?show_unknown=0&qa_screenshot=1",
            "kind": "viewport",
            "desc": "Show unknown OFF — unknown records hidden",
        },
        "section-4": {
            "path": "/?qa_screenshot=1",
            "kind": "viewport",
            "desc": "Default records list — v0.1/v0.2 features baseline",
        },
        # ------ Narrow viewport (responsive scroll demo) -----------------
        "item-1.1-8": {
            "path": "/?qa_screenshot=1",
            "kind": "narrow",
            "desc": "Records table at viewport <1024px — horizontal scroll inside its pane",
        },
        # ------ Locator-only (sidebar Tests block, much smaller PNG) -----
        # Per user request: shoot ONLY the sidebar instead of the whole
        # page for the "tests visible" / "outcome mix" checks. Saves tons
        # of disk + crops directly to the relevant area.
        "item-1.1-3-full": {
            "path": "/?qa_screenshot=1",
            "kind": "locator",
            "selector": "aside",  # the entire left sidebar
            "auto_height": True,  # measure aside.scrollHeight after load and
            # size the viewport to fit — avoids a fixed
            # 8000px cap that silently crops once the
            # sidebar grows past it.
            "desc": "Sidebar only — full height end-to-end (no truncation)",
        },
        "item-1.1-5-full": {
            "path": "/?qa_screenshot=1",
            "kind": "locator",
            "selector": "aside",
            "max_height": 1500,  # crop to first ~1500px of the sidebar
            "desc": "Sidebar only (cropped) — outcome icon mix ✓/✗/🔥/⊘ visible",
        },
    }


# ---- Playwright runner ---------------------------------------------------


def _capture_all(catalog: dict[str, dict], port: int, out_dir: Path) -> int:
    """Drive Playwright through the catalog. Returns number of successes."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "error: playwright not installed.\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    n_ok = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for slug, spec in catalog.items():
                kind = spec["kind"]
                path = spec["path"]
                desc = spec["desc"]
                url = f"http://127.0.0.1:{port}{path}"
                out_path = out_dir / f"{slug}.png"

                # Per-shot viewport (override via spec["viewport_h"])
                if kind == "narrow":
                    viewport = {"width": 900, "height": 700}
                else:
                    viewport = {"width": 1920, "height": spec.get("viewport_h", 1200)}

                ctx = browser.new_context(viewport=viewport)
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=15_000)

                    if kind == "locator" and spec.get("auto_height"):
                        # The aside is `h-[calc(100vh-3rem)] overflow-y-auto`
                        # so its own bounding box == viewport height and
                        # scrollHeight clamps to clientHeight. We need to
                        # size the viewport from the aside's *inner*
                        # content, not the aside itself: measure the
                        # bottom edge of the last rendered child of
                        # aside > form, plus the form's vertical padding.
                        real_h = page.evaluate(
                            """
                            () => {
                              const aside = document.querySelector('aside');
                              if (!aside) return 0;
                              const form = aside.querySelector('form') || aside;
                              const asideTop = aside.getBoundingClientRect().top;
                              const cs = getComputedStyle(aside);
                              const padBottom = parseFloat(cs.paddingBottom) || 0;
                              let bottom = 0;
                              for (const el of form.children) {
                                const b = el.getBoundingClientRect().bottom;
                                if (b > bottom) bottom = b;
                              }
                              return Math.ceil(bottom - asideTop + padBottom);
                            }
                            """
                        )
                        if real_h and real_h > viewport["height"]:
                            page.set_viewport_size(
                                {"width": viewport["width"], "height": real_h + 50}
                            )

                    if kind == "full":
                        page.screenshot(path=str(out_path), full_page=True)
                    elif kind == "viewport" or kind == "narrow":
                        page.screenshot(path=str(out_path), full_page=False)
                    elif kind == "locator":
                        sel = spec["selector"]
                        loc = page.locator(sel).first
                        max_h = spec.get("max_height")
                        if max_h:
                            # Crop to the top of the locator's bounding box
                            box = loc.bounding_box()
                            if box:
                                page.screenshot(
                                    path=str(out_path),
                                    clip={
                                        "x": box["x"],
                                        "y": box["y"],
                                        "width": box["width"],
                                        "height": min(box["height"], max_h),
                                    },
                                )
                            else:
                                loc.screenshot(path=str(out_path))
                        else:
                            loc.screenshot(path=str(out_path))
                    else:
                        raise ValueError(f"unknown kind: {kind}")

                    size_kb = out_path.stat().st_size / 1024
                    print(
                        f"  ✓ {slug:22s} ({size_kb:7.1f} KB, {kind:8s}) — {desc}", file=sys.stderr
                    )
                    n_ok += 1
                except Exception as e:
                    print(f"  ✗ {slug:22s} FAILED: {e}", file=sys.stderr)
                finally:
                    ctx.close()
        finally:
            browser.close()

    return n_ok


# ---- Entrypoint ----------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=Path("/tmp/ulog-demo"),
        help="Directory with logs.sqlite + git repo (default: /tmp/ulog-demo)",
    )
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--no-optimize", action="store_true", help="Skip pngquant post-processing")
    args = parser.parse_args()

    if not (args.demo_dir / "logs.sqlite").exists():
        print(
            f"error: {args.demo_dir / 'logs.sqlite'} missing — run scripts/seed_demo_db.py first",
            file=sys.stderr,
        )
        return 2

    ids = _discover_ids(args.demo_dir)
    catalog = _catalog(ids)

    port = _free_port()
    print(f"spawning viewer on port {port} ...", file=sys.stderr)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ulog.web.cli",
            "--no-open",
            "--port",
            str(port),
            "--repo",
            str(args.demo_dir),
            str(args.demo_dir / "logs.sqlite"),
        ],
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
    )
    try:
        _wait_for_server(port)
        print(
            f"viewer ready on http://127.0.0.1:{port}/\nwriting screenshots to {args.out_dir}/ ...",
            file=sys.stderr,
        )
        n_ok = _capture_all(catalog, port, args.out_dir)
        print(f"\n{n_ok}/{len(catalog)} screenshots written", file=sys.stderr)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    # Optimize via pngquant unless disabled
    if not args.no_optimize and OPTIMIZE_SCRIPT.exists():
        print("\noptimizing PNGs via pngquant ...", file=sys.stderr)
        subprocess.run(["bash", str(OPTIMIZE_SCRIPT)], check=False)

    return 0 if n_ok == len(catalog) else 1


if __name__ == "__main__":
    raise SystemExit(main())
