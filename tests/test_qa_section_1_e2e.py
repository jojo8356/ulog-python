"""End-to-end tests automating section §1.1 (Tests sidebar) of the QA checklist.

Replaces manual checkbox-clicks for items that can be deterministically
asserted on the rendered HTML.

Reuses the seeded_demo fixture from test_qa_setup_e2e.py via pytest's
fixture discovery (same `tests/` package).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from .test_qa_setup_e2e import seeded_demo  # noqa: F401  reuse the module-scoped seed


def _make_django_client(db_path: Path):
    """Configure Django settings + return a test client pointing at db_path.
    Mirrors the helper duplicated across tests/test_*_view.py — kept local
    for now (no shared conftest fixture yet)."""
    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db_path)
    os.environ["ULOG_LOGS_KIND"] = "sqlite"
    os.environ["ULOG_DEBUG"] = "0"
    import django
    from django.apps import apps as django_apps
    if not django_apps.ready:
        django.setup()
    from django.conf import settings as _dj_settings
    _dj_settings.ULOG_LOGS_PATH = str(db_path)
    _dj_settings.ULOG_LOGS_KIND = "sqlite"
    from ulog.web.viewer import views as _views
    _views._adapter = None
    from django.test import Client
    return Client()


def test_tests_sidebar_groups_by_file(seeded_demo):  # noqa: F811
    """§1.1.2 — Tests grouped by file (tests/checkout.py, tests/login.py, ...).

    Asserts that the rendered TESTS sidebar contains at least 3 distinct
    `tests/<name>.py` summary headers AND that each file group contains
    at least one nested test name.
    """
    client = _make_django_client(seeded_demo / "logs.sqlite")
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")

    # The seed script creates 10 test files × 50 tests each. The sidebar
    # uses `<details><summary>tests/<file>.py</summary>` per group via
    # Django's `{% regroup %}`. Match the file paths inside summaries.
    file_paths = re.findall(r"<summary[^>]*>\s*(tests/[^<\s]+\.py)", body)
    distinct_files = set(file_paths)

    assert len(distinct_files) >= 3, (
        f"§1.1.2 expects ≥ 3 distinct test files grouped in the sidebar; "
        f"got {len(distinct_files)}: {sorted(distinct_files)[:5]}"
    )

    # For each detected file, there should be at least one nested test
    # name (rendered as an <a href="?test_id=<file>%3A%3A<test_name>"> link).
    # Django's |urlencode filter leaves "/" unescaped (valid in query
    # strings) but encodes ":" as %3A. So the href contains the raw
    # file path followed by %3A%3A.
    for file_path in sorted(distinct_files)[:3]:  # spot-check first 3
        pattern = rf'href="\?test_id={re.escape(file_path)}%3A%3A'
        nested_test_links = re.findall(pattern, body)
        assert len(nested_test_links) >= 1, (
            f"§1.1.2 expects ≥ 1 nested test under {file_path}; found 0 "
            f"links matching {pattern!r}"
        )


def test_tests_sidebar_renders_when_seed_has_test_records(seeded_demo):  # noqa: F811
    """§1.1.1 corollary — the 'Tests' header itself is present when the
    DB contains `logger='ulog.test'` records (which the seed always
    produces). Catches regressions in the {% if test_summary %} gate."""
    client = _make_django_client(seeded_demo / "logs.sqlite")
    resp = client.get("/")
    body = resp.content.decode("utf-8")
    assert "<span>Tests</span>" in body, (
        "TESTS sidebar header missing despite seed having test records"
    )
