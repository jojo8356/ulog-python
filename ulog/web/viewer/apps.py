"""Django app config for the ULog viewer."""

from __future__ import annotations

from django.apps import AppConfig


class ViewerConfig(AppConfig):  # type: ignore[misc]  # django.apps.AppConfig is untyped
    name = "ulog.web.viewer"
    label = "ulog_viewer"
    default_auto_field = "django.db.models.BigAutoField"
