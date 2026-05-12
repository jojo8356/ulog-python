"""ulog.testing — pytest plugin and programmatic test-event APIs.

Sub-package home for v0.3 test integration and v0.5 replay tooling:

- ``pytest_plugin`` module — auto-discovered via
  ``[project.entry-points.pytest11]``. Loaded by pytest itself, not
  imported manually.
- ``test_event`` (Story 1.9) — programmatic ``@contextmanager`` for
  non-pytest runners.
- ``replay_records`` + ``ReplaySession`` + ``CapturedRecord`` (Story
  4.9 / v0.5) — context manager that re-emits a frozen record list
  through the logging pipeline with ``_REPLAY_ACTIVE=True``. Gap G5
  signature lock honoured.
- ``TestSession`` (v0.5) — STUB dataclass; importable name only.

The sub-package is loaded only when the ``[testing]`` extra is installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._replay_records import CapturedRecord, ReplaySession, replay_records
from .test_event import test_event

__all__ = [
    "CapturedRecord",
    "ReplaySession",
    "TestSession",
    "replay_records",
    "test_event",
]


@dataclass
class TestSession:
    """STUB dataclass — full implementation in v0.5.

    The shape is locked here per architecture.md (step-06 sub-package
    layout names this class as exported from ``ulog.testing``) to allow
    v0.3 client code to ``from ulog.testing import TestSession`` without
    ImportError. The ``name`` + ``records`` fields are minimal
    placeholders; v0.5 (Story 4.9) will pin the final shape in its own
    architectural review.
    """

    name: str = ""
    records: list[Any] = field(default_factory=list)

    # No __post_init__ defined — a `pass`-only post-init would add a
    # call-frame on every construction with zero behavior. Construction is
    # allowed by the dataclass-generated __init__; v0.5 (Story 4.9) will
    # decide whether to add validation or full session semantics.
