"""Integrity badge template tag (Story 6.6 / FR113).

Reads `<settings.ULOG_LOGS_PATH>.verify_state.json` at template-render
time and exposes the state to a small inclusion tag. Graceful degrade
when the sidecar is absent ("never verified").
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from django import template
from django.conf import settings

from ulog._verify_state import read_verify_state

register = template.Library()


@register.inclusion_tag("ulog/_integrity_badge.html")  # type: ignore[untyped-decorator]
def integrity_badge() -> dict[str, Any]:
    """Resolve the verify_state sidecar and return template context."""
    logs_path = getattr(settings, "ULOG_LOGS_PATH", None)
    if not logs_path:
        return {"status": "missing"}
    state = read_verify_state(Path(str(logs_path)))
    if state is None:
        return {"status": "missing"}
    status = state.get("status", "missing")
    last_check_iso = state.get("last_check_ts", "")
    relative = _relative_ts(last_check_iso)
    return {
        "status": status,
        "verified_up_to": state.get("verified_up_to_chain_pos"),
        "broken_at": state.get("broken_at"),
        "last_check_relative": relative,
    }


def _relative_ts(iso: str) -> str:
    """Render an ISO timestamp as `Nm ago` / `Nh ago` / `Nd ago`."""
    if not iso:
        return ""
    try:
        ts = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    now = datetime.datetime.now(datetime.UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.UTC)
    delta = now - ts
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"
