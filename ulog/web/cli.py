"""`ulog-web` console-script entry point (FR33).

Usage:
    ulog-web /path/to/logs.sqlite     # default port, opens browser
    ulog-web --port 8080 ./logs.jsonl # specific port
    ulog-web --no-open ./logs.csv     # don't auto-open browser

The script:
  1. Sniffs the file extension to set ULOG_LOGS_KIND.
  2. Configures Django settings via env vars.
  3. Spins up `manage.py runserver` on the requested port.
  4. Opens the system browser via `webbrowser`.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .viewer.adapters import detect_kind


def _find_free_port() -> int:
    """Bind to port 0 to grab a free port from the OS, then close.
    There's a short race between close and Django binding it; on
    localhost-only it's not an attack surface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _open_browser_when_ready(host: str, port: int, delay_s: float = 1.0) -> None:
    """Run in a background thread: wait briefly, then open the URL."""

    def _open() -> None:
        time.sleep(delay_s)
        url = f"http://{host}:{port}/"
        webbrowser.open(url)

    t = threading.Thread(target=_open, daemon=True)
    t.start()


def _walk_for_git_root(start: Path) -> Path | None:
    """Walk parents (including `start` itself) until a directory with
    a `.git/` subdirectory is found. Returns None if filesystem root
    is reached without finding one."""
    ceilings = {
        Path(p).resolve()
        for p in os.environ.get("GIT_CEILING_DIRECTORIES", "").split(os.pathsep)
        if p
    }
    for d in [start, *start.parents]:
        if (d / ".git").is_dir():
            return d
        if d.resolve() in ceilings:
            break
    return None


def _resolve_repo_flag(args: argparse.Namespace, cwd: Path) -> tuple[Path | None, str | None]:
    """Resolve the effective --repo value.

    Returns (repo_root, warning_message). repo_root is None when
    indexing should be skipped (no .git/ found and no explicit flag).
    warning_message is the exact stderr line to print, or None.
    """
    if args.no_author_index:
        return None, None  # explicit skip — no warning
    if args.repo is not None:
        explicit = Path(args.repo).resolve()
        if not (explicit / ".git").is_dir():
            return explicit, (
                f"ulog-web: --repo {args.repo} has no .git/ subdirectory; "
                "records will show <unknown>"
            )
        return explicit, None
    auto = _walk_for_git_root(cwd)
    if auto is None:
        return None, (
            "ulog-web: no git repo detected (cwd has no .git/ ancestor); "
            "records will show <unknown> author. Use --repo PATH or "
            "--no-author-index to silence."
        )
    return auto, None


def _set_env_for_django(repo: Path | None, disabled: bool, rebuild: bool) -> None:
    """Populate env vars so the Django process can pick up the flags."""
    if disabled:
        os.environ["ULOG_AUTHOR_INDEX_DISABLED"] = "1"
    elif repo is not None:
        os.environ["ULOG_AUTHOR_REPO"] = str(repo)
    if rebuild:
        os.environ["ULOG_AUTHOR_INDEX_REBUILD"] = "1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ulog-web",
        description="Open the ULog inspection UI for a stored log file.",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Log file: .sqlite/.sqlite3/.db, .jsonl/.ndjson, or .csv",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to bind (default: random free port).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host. Default 127.0.0.1 (localhost only). "
        "Set to 0.0.0.0 to expose to the network — requires explicit opt-in.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't auto-open a browser tab.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Git repo root for author attribution. Default: walk parents "
        "of cwd until .git/ is found.",
    )
    index_group = parser.add_mutually_exclusive_group()
    index_group.add_argument(
        "--no-author-index",
        action="store_true",
        help="Skip the author indexer; hides the Authors sidebar.",
    )
    index_group.add_argument(
        "--rebuild-author-index",
        action="store_true",
        help="Force rebuild of the author cache (drops the existing one).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Django DEBUG mode + show the /_qa/ checklist link "
        "in the header. Dev-only — never use against shared logs.",
    )
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"ulog-web: file not found: {args.path}", file=sys.stderr)
        return 2
    try:
        kind = detect_kind(args.path)
    except ValueError as e:
        print(f"ulog-web: {e}", file=sys.stderr)
        return 2

    if args.host != "127.0.0.1" and args.host != "localhost":
        print(
            f"ulog-web: WARNING — binding to {args.host}, "
            "exposing logs to the network. Continue at your own risk.",
            file=sys.stderr,
        )

    port = args.port or _find_free_port()

    # Configure Django via env vars before importing it.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ulog.web.settings")
    os.environ["ULOG_LOGS_PATH"] = str(args.path.resolve())
    os.environ["ULOG_LOGS_KIND"] = kind
    # `--debug` is the user-facing switch; settings.py reads ULOG_DEBUG
    # internally because Django settings load before main() returns.
    if args.debug:
        os.environ["ULOG_DEBUG"] = "1"

    # Resolve author-index flags + emit any warning.
    repo, warning = _resolve_repo_flag(args, Path.cwd())
    if warning:
        print(warning, file=sys.stderr)
    _set_env_for_django(repo, args.no_author_index, args.rebuild_author_index)

    # Build the author index at startup (Story 2.3 / FR71). Failures
    # don't abort the CLI — records just show <unknown> in the UI.
    if repo is not None and not args.no_author_index:
        try:
            from .viewer.adapters import get_adapter
            from .viewer.blame import build_index_at_startup

            build_index_at_startup(get_adapter(args.path), repo)
        except Exception as e:
            print(
                f"ulog-web: author index build failed: {e}; records will show <unknown>",
                file=sys.stderr,
            )

    import django

    django.setup()

    # PRD-v0.4.4 — startup pre-warm. Issue a default Filters query so
    # SQLite page cache + reflected schema + bound-context column scan
    # are warm before the user's first request. Best-effort: any error
    # is swallowed (the viewer still serves uncached).
    try:
        from .viewer.adapters import Filters, get_adapter

        _prewarm_adapter = get_adapter(args.path)
        _prewarm_adapter.query(Filters(), page=1, page_size=100)
    except Exception as e:
        print(f"ulog-web: prewarm failed (non-fatal): {e}", file=sys.stderr)

    if not args.no_open:
        _open_browser_when_ready(args.host, port)

    print(
        f"ulog-web: serving {args.path} ({kind}) on http://{args.host}:{port}/",
        file=sys.stderr,
    )

    # Bypass `runserver` and call Django's underlying WSGI runner
    # directly. This skips runserver's banner ("Starting development
    # server at...", date line, dev-server WARNING) and its migration
    # check, which fires false positives against our `:memory:` stub
    # DB. We still get the per-request access log via
    # WSGIRequestHandler, plus static-file serving via StaticFilesHandler.
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.servers.basehttp import run
    from django.core.wsgi import get_wsgi_application

    handler = StaticFilesHandler(get_wsgi_application())

    def _serve() -> None:
        run(args.host, port, handler, threading=True)

    # In --debug mode, wrap in Django's autoreloader: any .py change
    # under the project (views, models, settings, the cli itself, etc.)
    # forks a fresh process. Templates and static files reload per-
    # request anyway when DEBUG=True (no restart needed).
    try:
        if args.debug:
            from django.utils.autoreload import run_with_reloader

            print(
                "ulog-web: --debug active → autoreload on .py changes",
                file=sys.stderr,
            )
            run_with_reloader(_serve)
        else:
            _serve()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
