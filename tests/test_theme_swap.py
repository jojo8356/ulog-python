"""Tests for PRD-v0.4.5 — theme swap sync (universal selector + View
Transitions API).

These tests are markup smoke checks; the visual desync the PRD
addresses is browser-side and best verified by the Playwright matrix
(v0.6.3), but we lock in the markup that prevents the regression.
"""

from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "ulog/web/templates/ulog/base.html"


def test_universal_selector_in_transition_rule():
    body = BASE.read_text(encoding="utf-8")
    # Universal selector replaces the per-tag list.
    assert "*, *::before, *::after" in body
    assert "fill 500ms ease" in body
    assert "stroke 500ms ease" in body
    assert "box-shadow 500ms ease" in body


def test_view_transition_api_wired_in_toggle():
    body = BASE.read_text(encoding="utf-8")
    assert "document.startViewTransition" in body
    # And falls back when unsupported.
    assert "} else {" in body and "swap();" in body
