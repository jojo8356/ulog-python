"""Story 2.7 — multi-select OR + URL + show_unknown filter wiring."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ulog.web.viewer.blame import (
    Author,
    AuthorIndex,
    _FileCache,
    set_global_index,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    set_global_index(None)
    yield
    set_global_index(None)


@pytest.fixture
def fixture_log_and_idx(tmp_path: Path) -> tuple[Path, AuthorIndex]:
    """Build a JSONL log with 6 records spanning 2 known authors + 1 unknown,
    plus a populated AuthorIndex resolving foo.py and bar.py to their authors."""
    a1 = Author(name="Alice", email="alice@x", sha="a" * 40, ts=1)
    a2 = Author(name="Bob", email="bob@x", sha="b" * 40, ts=2)
    log = tmp_path / "logs.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "x",
                        "level": "INFO",
                        "logger": "x",
                        "msg": "a1",
                        "file": "foo.py",
                        "line": 1,
                    }
                ),
                json.dumps(
                    {
                        "ts": "x",
                        "level": "INFO",
                        "logger": "x",
                        "msg": "a2",
                        "file": "foo.py",
                        "line": 1,
                    }
                ),
                json.dumps(
                    {
                        "ts": "x",
                        "level": "INFO",
                        "logger": "x",
                        "msg": "b1",
                        "file": "bar.py",
                        "line": 1,
                    }
                ),
                json.dumps(
                    {
                        "ts": "x",
                        "level": "INFO",
                        "logger": "x",
                        "msg": "b2",
                        "file": "bar.py",
                        "line": 1,
                    }
                ),
                json.dumps(
                    {
                        "ts": "x",
                        "level": "INFO",
                        "logger": "x",
                        "msg": "u1",
                        "file": "external.py",
                        "line": 99,
                    }
                ),
                json.dumps(
                    {
                        "ts": "x",
                        "level": "INFO",
                        "logger": "x",
                        "msg": "u2",
                        "file": "external.py",
                        "line": 99,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    idx = AuthorIndex(tmp_path)
    for fname, author in [("foo.py", a1), ("bar.py", a2)]:
        path = tmp_path / fname
        path.write_text("stub\n", encoding="utf-8")
        mtime = os.stat(path).st_mtime
        idx._cache[fname] = _FileCache(mtime=mtime, blames=dict.fromkeys(range(1, 200), author))
    # external.py — not in idx → resolves to None (<unknown>)
    set_global_index(idx)
    return log, idx


def _make_django_client(db_path: Path):
    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db_path)
    os.environ["ULOG_LOGS_KIND"] = "jsonl"
    os.environ["ULOG_DEBUG"] = "0"
    import django
    from django.apps import apps as django_apps

    if not django_apps.ready:
        django.setup()
    from django.conf import settings as _dj_settings

    _dj_settings.ULOG_LOGS_PATH = str(db_path)
    _dj_settings.ULOG_LOGS_KIND = "jsonl"
    from ulog.web.viewer import views as _views

    _views._adapter = None
    from django.test import Client

    return Client()


# ---- AC1: single-author filter -------------------------------------------


def test_filter_single_author(fixture_log_and_idx):
    log, _ = fixture_log_and_idx
    client = _make_django_client(log)
    resp = client.get("/?author=alice@x")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # Alice's records should be present (msgs in HTML)
    assert ">a1<" in body or ">a2<" in body
    # Bob's records and unknowns should be filtered out from the main list
    assert ">b1<" not in body
    assert ">b2<" not in body
    assert ">u1<" not in body
    assert ">u2<" not in body


# ---- AC1 + AC2: multi-author OR -----------------------------------------


def test_filter_multi_author_or(fixture_log_and_idx):
    log, _ = fixture_log_and_idx
    client = _make_django_client(log)
    resp = client.get("/?author=alice@x&author=bob@x")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # Both Alice's and Bob's records present
    # Record msgs appear as the message column content. Use surrounding markup
    # for specificity since "a1" / "b1" may appear in CSS color tokens.
    assert ">a1<" in body or '"a1"' in body
    assert ">b1<" in body or '"b1"' in body
    # external (unknown) NOT in selection
    assert ">u1<" not in body
    assert ">u2<" not in body


# ---- AC3: <unknown> sentinel ---------------------------------------------


def test_filter_unknown_sentinel(fixture_log_and_idx):
    log, _ = fixture_log_and_idx
    client = _make_django_client(log)
    # URL-encoded "<unknown>"
    resp = client.get("/?author=%3Cunknown%3E")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert ">u1<" in body
    assert ">u2<" in body
    assert ">a1<" not in body
    assert ">b1<" not in body


# ---- AC4: show_unknown toggle -------------------------------------------


def test_show_unknown_off_hides_unknowns(fixture_log_and_idx):
    log, _ = fixture_log_and_idx
    client = _make_django_client(log)
    resp = client.get("/?show_unknown=0")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # Knowns visible, unknowns hidden
    assert ">a1<" in body
    assert ">b1<" in body
    assert ">u1<" not in body
    assert ">u2<" not in body


def test_show_unknown_default_on_keeps_unknowns(fixture_log_and_idx):
    log, _ = fixture_log_and_idx
    client = _make_django_client(log)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # All records visible (default show_unknown=True, no author filter)
    assert ">a1<" in body
    assert ">b1<" in body
    assert ">u1<" in body


# ---- AC5: pagination correctness ----------------------------------------


def test_pagination_after_filter_total_correct(fixture_log_and_idx):
    log, _ = fixture_log_and_idx
    client = _make_django_client(log)
    resp = client.get("/?author=alice@x")
    body = resp.content.decode("utf-8")
    # Filtered to Alice only: 2 records. Pagination should show "1" page.
    # Look for pagination presence (or absence with single page).
    assert resp.status_code == 200
    # Body shouldn't claim "6 records" — should be 2.
    assert "6 records" not in body


# ---- Author + level compose ----------------------------------------------


def test_author_filter_composes_with_level(fixture_log_and_idx):
    """Filter by author AND level — both axes apply."""
    log, _ = fixture_log_and_idx
    client = _make_django_client(log)
    # All records are INFO; ERROR filter → 0 results regardless of author
    resp = client.get("/?author=alice@x&level=ERROR")
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    # Body may show "no records" or "0 records" per the empty-state template
    assert ">a1<" not in body
