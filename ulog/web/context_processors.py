"""Custom Django context processors for the ULog viewer.

`debug_flag`: exposes the global `debug` boolean to every template,
unconditionally (the standard `django.template.context_processors.debug`
gates on INTERNAL_IPS, which is overkill for a single-user dev tool).
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest


def debug_flag(request: HttpRequest) -> dict[str, bool]:
    """Make `{{ debug }}` available in every template."""
    return {"debug": bool(getattr(settings, "DEBUG", False))}
