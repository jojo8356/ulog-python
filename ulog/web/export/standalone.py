"""Standalone Django setup for `ulog export-html` (Story 8.3 / FR140).

The live viewer runs a server; the exporter just calls
`render_to_string()` per page. Both share the same template set —
we just need Django configured WITHOUT running `runserver` or
listening on a socket.

This module isolates that bootstrap so it's idempotent and
side-effect-free for tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def ensure_django_configured(logs_path: Path, logs_kind: str) -> None:
    """Configure Django settings in standalone mode (no server).

    Idempotent — calling twice is a no-op.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ulog.web.settings")
    os.environ["ULOG_LOGS_PATH"] = str(logs_path.resolve())
    os.environ["ULOG_LOGS_KIND"] = logs_kind
    os.environ["ULOG_DEBUG"] = "0"

    import django
    from django.apps import apps as django_apps
    from django.conf import settings as _dj_settings

    if not django_apps.ready:
        django.setup()
    _dj_settings.ULOG_LOGS_PATH = str(logs_path.resolve())
    _dj_settings.ULOG_LOGS_KIND = logs_kind
    _dj_settings.DEBUG = False


def render_template(name: str, context: dict[str, Any]) -> str:
    """`render_to_string()` with the live viewer's template loader."""
    from django.template.loader import render_to_string

    return str(render_to_string(name, context))
