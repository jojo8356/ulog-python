"""Custom Django template filters for the ulog viewer (Story 1.6+)."""
from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="test_duration_fmt")
def test_duration_fmt(seconds: object) -> str:
    """Format a `duration_s` float per Story 1.6 AC8.

    - >= 1.0     → "{:.1f}s"  e.g. "12.0s"
    - >= 0.001   → "{:.0f}ms" e.g. "24ms"
    - else       → "<1ms"

    Defensive: returns "" for non-numeric input rather than raising
    (a malformed `duration_s` shouldn't break the template render).
    """
    try:
        s = float(seconds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if s >= 1.0:
        return f"{s:.1f}s"
    if s >= 0.001:
        return f"{s * 1000:.0f}ms"
    return "<1ms"
