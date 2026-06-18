"""Shared helpers for browser-backed E2E tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

E2E_VIEWPORT = {"width": 1400, "height": 900}


def e2e_timeout_ms() -> int:
    """Default to short local timeouts so actionability bugs fail fast."""
    raw = os.environ.get("ULOG_PW_TIMEOUT_MS", "5000")
    try:
        return max(1000, int(raw))
    except ValueError:
        return 5000


def _configure_timeout(obj: Any) -> None:
    timeout = e2e_timeout_ms()
    if hasattr(obj, "set_default_timeout"):
        obj.set_default_timeout(timeout)
    if hasattr(obj, "set_default_navigation_timeout"):
        obj.set_default_navigation_timeout(max(timeout, 15_000))


def launch_e2e_browser(pw: Any, browser_name: str | None = None) -> Any:
    """Launch Chromium/Firefox/WebKit, or connect to Lightpanda through CDP.

    Lightpanda intentionally has no graphical renderer. Use it only for
    fast DOM/JS/URL tests:

        ULOG_E2E_BROWSER=lightpanda ULOG_LIGHTPANDA_CDP=ws://127.0.0.1:9222 pytest ...
    """
    selected = (browser_name or os.environ.get("ULOG_E2E_BROWSER", "chromium")).strip()
    if selected == "lightpanda":
        cdp_url = os.environ.get("ULOG_LIGHTPANDA_CDP")
        if not cdp_url:
            pytest.skip("ULOG_LIGHTPANDA_CDP is required for ULOG_E2E_BROWSER=lightpanda")
        browser = pw.chromium.connect_over_cdp(cdp_url)
    else:
        launcher = getattr(pw, selected)
        browser = launcher.launch()
    return browser


@contextmanager
def new_e2e_context(browser: Any, *, dismiss_tutorial: bool = True) -> Iterator[Any]:
    ctx = browser.new_context(viewport=E2E_VIEWPORT)
    _configure_timeout(ctx)
    if dismiss_tutorial:
        ctx.add_init_script("window.localStorage.setItem('ulogTutorialDismissed', '1')")
    try:
        yield ctx
    finally:
        ctx.close()
