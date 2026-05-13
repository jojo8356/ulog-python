"""Static HTML export — `ulog export-html` (PRD-v0.6, Epic 8).

Renders a stored log file (SQLite / JSONL / CSV) into a
self-contained directory of HTML pages, sharing every template
with the live viewer. The result is `file://`-openable, zippable,
GitHub-Pages-hostable.
"""

from __future__ import annotations

from .exporter import ExportOptions, HtmlExporter

__all__ = ["ExportOptions", "HtmlExporter"]
