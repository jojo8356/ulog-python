"""Tests for v0.14 — known-bugs cache + ulog bug-cache CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ulog._bug_cache import (
    clear,
    count,
    import_from_json,
    search_by_signature,
)
from ulog._cli import main as cli_main


def _curated_json(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "curated.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p


def test_import_then_search(tmp_path):
    cache = tmp_path / "cache.sqlite"
    src = _curated_json(
        tmp_path,
        [
            {
                "signature": "deadbeef",
                "title": "TimeoutError on httpx",
                "body": "increase timeout=10",
                "source": "github",
                "url": "https://github.com/encode/httpx/issues/1",
                "accepted": True,
            }
        ],
    )
    n = import_from_json(cache, src)
    assert n == 1
    matches = search_by_signature(cache, "deadbeef")
    assert len(matches) == 1
    assert matches[0]["accepted"] is True
    assert matches[0]["source"] == "github"


def test_search_empty_cache_returns_empty(tmp_path):
    matches = search_by_signature(tmp_path / "missing.sqlite", "sig")
    assert matches == []


def test_count_zero_when_absent(tmp_path):
    assert count(tmp_path / "nope.sqlite") == 0


def test_clear_removes_cache(tmp_path):
    cache = tmp_path / "cache.sqlite"
    src = _curated_json(tmp_path, [{"signature": "a", "title": "t"}])
    import_from_json(cache, src)
    assert cache.exists()
    clear(cache)
    assert not cache.exists()


# ---- CLI subcommands ---------------------------------------------------


def test_cli_refresh_requires_source_file(tmp_path, capsys):
    rc = cli_main(["bug-cache", "refresh", "--cache", str(tmp_path / "c.sqlite")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "scraper is deferred" in err


def test_cli_refresh_imports_from_source(tmp_path, capsys):
    cache = tmp_path / "c.sqlite"
    src = _curated_json(tmp_path, [{"signature": "x", "title": "y"}])
    rc = cli_main(["bug-cache", "refresh", "--source-file", str(src), "--cache", str(cache)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "imported 1 entries" in err


def test_cli_search_returns_1_on_no_match(tmp_path, capsys):
    rc = cli_main(["bug-cache", "search", "no-such-sig", "--cache", str(tmp_path / "nope.sqlite")])
    assert rc == 1


def test_cli_search_lists_matches(tmp_path, capsys):
    cache = tmp_path / "c.sqlite"
    src = _curated_json(
        tmp_path,
        [
            {
                "signature": "abc",
                "title": "Big bug",
                "source": "so",
                "url": "https://stackoverflow.com/q/123",
                "accepted": True,
            }
        ],
    )
    cli_main(["bug-cache", "refresh", "--source-file", str(src), "--cache", str(cache)])
    capsys.readouterr()  # drain
    rc = cli_main(["bug-cache", "search", "abc", "--cache", str(cache)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Big bug" in out
    assert "★ accepted" in out
    assert "stackoverflow.com" in out


def test_cli_status_reports_count(tmp_path, capsys):
    cache = tmp_path / "c.sqlite"
    src = _curated_json(tmp_path, [{"signature": "a", "title": "t"}, {"signature": "b", "title": "u"}])
    cli_main(["bug-cache", "refresh", "--source-file", str(src), "--cache", str(cache)])
    capsys.readouterr()
    rc = cli_main(["bug-cache", "status", "--cache", str(cache)])
    err = capsys.readouterr().err
    assert rc == 0
    assert "2 entries" in err


def test_cli_clear_removes_cache(tmp_path, capsys):
    cache = tmp_path / "c.sqlite"
    src = _curated_json(tmp_path, [{"signature": "a", "title": "t"}])
    cli_main(["bug-cache", "refresh", "--source-file", str(src), "--cache", str(cache)])
    assert cache.exists()
    rc = cli_main(["bug-cache", "clear", "--cache", str(cache)])
    assert rc == 0
    assert not cache.exists()


# ---- v0.16 integration -------------------------------------------------


def test_known_bugs_results_picked_up_by_unified_search(tmp_path, monkeypatch):
    """search_known_bugs() returns the cache rows."""
    cache = tmp_path / "c.sqlite"
    src = _curated_json(
        tmp_path,
        [
            {
                "signature": "boom-sig",
                "title": "Look at this fix",
                "body": "set MAX_CONN=10",
                "source": "so",
                "accepted": True,
            }
        ],
    )
    cli_main(["bug-cache", "refresh", "--source-file", str(src), "--cache", str(cache)])

    # Re-point the default cache path to our tmp via monkeypatching.
    import ulog._bug_cache as bc
    monkeypatch.setattr(bc, "default_cache_path", lambda: cache)

    from ulog._solutions import search_known_bugs
    results = search_known_bugs("boom-sig")
    assert len(results) == 1
    assert results[0].provenance == "known-bug-accepted"
    assert results[0].title == "Look at this fix"
