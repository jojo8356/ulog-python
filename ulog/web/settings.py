"""Minimal Django settings for the ULog web inspection UI.

Designed to be configured at runtime by `ulog-web` (the console
script), not via environment variables. The script sets:
  - `ULOG_LOGS_PATH`      → path to the .sqlite/.jsonl/.csv to load
  - `ULOG_LOGS_KIND`      → 'sqlite' / 'jsonl' / 'csv'
  - `ULOG_BIND_HOST`      → '127.0.0.1' (default)
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ULog-specific runtime context — set by ulog-web before runserver.
ULOG_LOGS_PATH = os.environ.get("ULOG_LOGS_PATH", "")
ULOG_LOGS_KIND = os.environ.get("ULOG_LOGS_KIND", "")  # sqlite/jsonl/csv

# Fresh secret per process — this is a read-only local viewer, no
# session-state security to preserve across restarts.
SECRET_KEY = os.environ.get("ULOG_SECRET_KEY", secrets.token_hex(32))

DEBUG = os.environ.get("ULOG_DEBUG") == "1"

# `ulog-web` binds to 127.0.0.1 only by default (NFR-SEC-10). If the
# user opts into 0.0.0.0 they'd see a stderr warning from the script.
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "lucide",  # SVG icons via {% lucide "name" %} template tag
    "ulog.web.viewer",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.middleware.security.SecurityMiddleware",
]

# Optional dev convenience: when DEBUG is on AND the user installed
# `pip install ulog[web-dev]` (or django-browser-reload directly),
# wire the browser-reload middleware so .py / template / static
# changes auto-refresh the open browser tab. Silently skipped when
# the package is absent — keeps the [web]-only install clean.
if DEBUG:
    try:
        import django_browser_reload  # noqa: F401
        INSTALLED_APPS.append("django_browser_reload")
        MIDDLEWARE.append("django_browser_reload.middleware.BrowserReloadMiddleware")
    except ImportError:
        pass

ROOT_URLCONF = "ulog.web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                # Custom processor — exposes `debug` in every template
                # (drives the QA-link visibility in the header).
                "ulog.web.context_processors.debug_flag",
            ],
            # Make {% lucide "name" %} available in every template
            # without per-file `{% load lucide %}`.
            "builtins": [
                "lucide.templatetags.lucide",
            ],
        },
    },
]

# No DB needed — the viewer reads ULOG_LOGS_PATH directly. We declare
# a stub so Django doesn't complain.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Markdown doc pages location (FR40)
ULOG_DOCS_DIR = BASE_DIR / "docs"

# Skip migrations for apps we never query — DATABASES['default'] is a
# `:memory:` stub (we read external .sqlite/.jsonl/.csv files instead),
# so contenttypes models are never used. This silences the noisy
# "You have N unapplied migration(s)" warning on every server start.
MIGRATION_MODULES = {"contenttypes": None}
