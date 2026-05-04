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
        return s.getsockname()[1]


def _open_browser_when_ready(host: str, port: int, delay_s: float = 1.0) -> None:
    """Run in a background thread: wait briefly, then open the URL."""
    def _open() -> None:
        time.sleep(delay_s)
        url = f"http://{host}:{port}/"
        webbrowser.open(url)

    t = threading.Thread(target=_open, daemon=True)
    t.start()


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
        "--port", type=int, default=0,
        help="Port to bind (default: random free port).",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind host. Default 127.0.0.1 (localhost only). "
             "Set to 0.0.0.0 to expose to the network — requires explicit opt-in.",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="Don't auto-open a browser tab.",
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

    import django
    django.setup()

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
    try:
        run(args.host, port, handler, threading=True)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
