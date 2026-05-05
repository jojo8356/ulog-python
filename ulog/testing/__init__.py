"""ulog.testing — pytest plugin and programmatic test-event APIs.

Sub-package home for v0.3 test integration:
- ``pytest_plugin`` module — auto-discovered via ``[project.entry-points.pytest11]``.
- ``test_event`` (Story 1.9) — programmatic API for non-pytest runners.
- ``replay_records`` (Story 4.9) — context manager used by
  ``replay_to_pytest()`` output.

The sub-package is loaded only when the ``[testing]`` extra is installed.
"""
from __future__ import annotations

__all__: list[str] = []  # populated in Story 1.9
