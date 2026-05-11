"""QA screenshots generator — captures full-page PNG of key viewer URLs.

Outputs go to `ulog/web/static/ulog/qa-screenshots/<slug>.png` so that
the `/_qa/` page can render them inline under each section, letting the
human visually verify behaviors without re-clicking through the UI.

Usage:
  python3 scripts/qa_screenshots.py [--demo-dir /tmp/ulog-demo] [--width 1920]

Requires a Chromium-based browser on PATH (brave-browser / chromium /
google-chrome). Firefox not supported (different headless screenshot
syntax). No Python dep added — just shells out to the browser binary.
"""
from __future__ import annotations

import argparse
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "ulog" / "web" / "static" / "ulog" / "qa-screenshots"


def _find_browser() -> str:
    for cmd in ("brave-browser", "chromium", "chromium-browser",
                "google-chrome", "google-chrome-stable"):
        path = shutil.which(cmd)
        if path:
            return path
    raise RuntimeError(
        "no Chromium-based browser found. Install one of: "
        "brave-browser, chromium, chromium-browser, google-chrome."
    )


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
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    raise RuntimeError(f"viewer never responded on port {port} within {timeout_s}s")


def _take_shot(browser: str, url: str, out_path: Path, *,
               width: int = 1920, height: int = 1200) -> None:
    """Capture a full-page screenshot via Chromium headless. Idempotent."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-sandbox",
        "--virtual-time-budget=3000",  # let JS settle a bit
        f"--window-size={width},{height}",
        f"--screenshot={out_path}",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            f"screenshot failed for {url}\n--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}"
        )


def _discover_ids(demo_dir: Path) -> dict[str, object]:
    """Pull live IDs from the demo DB + git repo so URLs are real."""
    db = demo_dir / "logs.sqlite"
    out: dict[str, object] = {}
    with sqlite3.connect(str(db)) as conn:
        out["first_record_id"] = int(conn.execute("SELECT MIN(id) FROM logs").fetchone()[0])
        # A record that carries test_id (so the Test context panel renders)
        row = conn.execute(
            "SELECT id, json_extract(context, '$.test_id') "
            "FROM logs WHERE json_extract(context, '$.test_id') IS NOT NULL LIMIT 1"
        ).fetchone()
        if row:
            out["record_with_test_id"] = int(row[0])
            out["sample_test_id"] = str(row[1])

    # Resolve a real commit sha from the demo repo
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=demo_dir, capture_output=True, text=True, check=True,
    )
    out["sha"] = proc.stdout.strip()
    return out


# Each entry: section slug → (relative URL builder, human description)
def _shot_plan(ids: dict[str, object]) -> dict[str, tuple[str, str]]:
    test_id_qs = urllib_quote_test_id(str(ids.get("sample_test_id", "")))
    plan: dict[str, tuple[str, str]] = {
        # Epic 1
        "section-1-1": ("/",
                        "Records list with sidebar (Tests block visible between Level and Sectors)"),
        "section-1-2": ("/?failed_only=1",
                        "Failed-only quick filter active"),
        "section-1-3": (f"/?test_id={test_id_qs}",
                        "Records filtered by test_id (mix of ulog.test + globex.*)"),
        "section-1-4": (f"/r/{ids.get('record_with_test_id', 1)}/",
                        "Detail view with Test context panel + Authored by panel"),
        "section-1-5": ("/docs/test-integration/",
                        "Test integration doc page"),
        # Epic 2
        "section-2-1": ("/",
                        "Authors sidebar visible (8 authors + <unknown>)"),
        "section-2-3": ("/?show_unknown=0",
                        "Show unknown OFF — unknown records hidden"),
        "section-2-4": (f"/r/{ids.get('first_record_id', 1)}/",
                        "Detail view (any record)"),
        "section-2-5": (f"/diff/{ids['sha']}/",
                        "Diff view (git show <sha>)"),
        "section-2-6": ("/docs/author-filter/",
                        "Author filter doc page"),
        # Cross-epic
        "section-4":   ("/",
                        "Default records list — all v0.1/v0.2 features visible (sidebars, table)"),
        # QA page itself (meta)
        "section-qa":  ("/_qa/",
                        "QA checklist page (debug-only)"),

        # Targeted captures for items the standard /  shot can't show
        # (because the Tests sidebar has max-h-60 overflow-y-auto and
        # narrow viewports require width tuning).
        # Use ?qa_screenshot=1 to remove the max-h-60 cap so all
        # deployed file groups are visible at once.
        "item-1.1-3": ("/?qa_screenshot=1",
                       "Tests sidebar with all groups visible — confirms 5 first <details> are open"),
        "item-1.1-5": ("/?qa_screenshot=1",
                       "Tests sidebar showing the full outcome mix (✓ passed / ✗ failed / 🔥 errored / ⊘ skipped)"),
        # item-1.1-8 is captured at narrow window via _shot_plan_narrow below
    }
    return plan


def _shot_plan_narrow(ids: dict[str, object]) -> dict[str, tuple[str, str]]:
    """Captures requiring a narrow viewport (≠ default width)."""
    return {
        "item-1.1-8": ("/",
                       "Records table at viewport <1024px — horizontal scroll inside the pane only"),
    }


def urllib_quote_test_id(test_id: str) -> str:
    """Same encoding as Django's |urlencode filter on a test_id string:
    leave '/' alone, encode '::' as %3A%3A."""
    if not test_id:
        return ""
    return test_id.replace("::", "%3A%3A")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-dir", type=Path, default=Path("/tmp/ulog-demo"),
                        help="Directory with logs.sqlite + git repo (default: /tmp/ulog-demo)")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if not (args.demo_dir / "logs.sqlite").exists():
        print(f"error: {args.demo_dir / 'logs.sqlite'} missing — run scripts/seed_demo_db.py first",
              file=sys.stderr)
        return 2

    try:
        browser = _find_browser()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"using browser: {browser}", file=sys.stderr)

    ids = _discover_ids(args.demo_dir)
    plan = _shot_plan(ids)

    port = _free_port()
    print(f"spawning viewer on port {port} ...", file=sys.stderr)
    proc = subprocess.Popen(
        [sys.executable, "-m", "ulog.web.cli",
         "--no-open", "--port", str(port),
         "--repo", str(args.demo_dir),
         str(args.demo_dir / "logs.sqlite")],
        stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
    )
    try:
        _wait_for_server(port)
        print(f"viewer ready on http://127.0.0.1:{port}/", file=sys.stderr)
        print(f"writing screenshots to {args.out_dir}/ ...", file=sys.stderr)

        for slug, (path, desc) in plan.items():
            url = f"http://127.0.0.1:{port}{path}"
            out_path = args.out_dir / f"{slug}.png"
            try:
                _take_shot(browser, url, out_path,
                           width=args.width, height=args.height)
                size_kb = out_path.stat().st_size / 1024
                print(f"  ✓ {slug:20s} ({size_kb:6.1f} KB) — {desc}",
                      file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {slug:20s} FAILED: {e}", file=sys.stderr)

        # Narrow-viewport captures (e.g. responsive scroll demo)
        narrow = _shot_plan_narrow(ids)
        for slug, (path, desc) in narrow.items():
            url = f"http://127.0.0.1:{port}{path}"
            out_path = args.out_dir / f"{slug}.png"
            try:
                _take_shot(browser, url, out_path, width=900, height=700)
                size_kb = out_path.stat().st_size / 1024
                print(f"  ✓ {slug:20s} ({size_kb:6.1f} KB, 900×700) — {desc}",
                      file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {slug:20s} FAILED: {e}", file=sys.stderr)

        total = len(plan) + len(narrow)
        print(f"\ndone — {total} screenshots in {args.out_dir}/",
              file=sys.stderr)
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
