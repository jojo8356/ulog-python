"""Tests for PRD-v0.16 — unified solution search."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

import ulog
from ulog._fixes import resolve_fix, signature
from ulog._solutions import (
    SearchResult,
    grant_session_consent,
    revoke_session_consent,
    search_community,
    search_local,
    session_consent_active,
    unified_search,
)


@pytest.fixture(autouse=True)
def _isolate():
    revoke_session_consent()
    ulog.clear()
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    revoke_session_consent()
    ulog.clear()


def _seed_with_fix(tmp_path: Path, msg: str = "boom", writeup: str = "fix it") -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().error(msg)
    for h in logging.getLogger().handlers:
        h.flush()
    resolve_fix(db, signature(msg), writeup, "Johan")
    return db


def test_search_local_returns_fix(tmp_path):
    db = _seed_with_fix(tmp_path, "test_error")
    sig = signature("test_error")
    results = search_local(db, sig)
    assert len(results) == 1
    assert results[0].provenance == "local"
    assert results[0].writeup == "fix it"


def test_search_local_returns_empty_when_no_fix(tmp_path):
    db = tmp_path / "empty.sqlite"
    db.write_bytes(b"")  # placeholder; no fixes sidecar yet
    results = search_local(db, signature("anything"))
    assert results == []


def test_search_community_no_network_returns_empty():
    """No mock → real URL → DNS fails → []. Confirms graceful fallback."""
    results = search_community("abc123", endpoint="http://127.0.0.1:1/nope")
    assert results == []


def test_unified_search_consent_gates_community(tmp_path):
    """consent_community=False MUST NOT call urlopen."""
    db = _seed_with_fix(tmp_path)
    with patch("urllib.request.urlopen") as mock_urlopen:
        results = unified_search(db, "boom", consent_community=False)
        mock_urlopen.assert_not_called()
    assert any(r.provenance == "local" for r in results)


def test_unified_search_with_consent_attempts_community(tmp_path):
    """consent_community=True MUST attempt the network call."""
    db = _seed_with_fix(tmp_path)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = ConnectionError("offline")
        unified_search(db, "boom", consent_community=True)
        mock_urlopen.assert_called_once()


def test_unified_search_dedupes_same_writeup(tmp_path):
    """Two entries with the same provenance + same writeup collapse."""
    db = _seed_with_fix(tmp_path, "x", "shared writeup")
    # Mock community returning the same writeup as local.
    with patch(
        "ulog._solutions.search_community",
        return_value=[
            SearchResult(
                provenance="local",
                title="dup",
                writeup="shared writeup",
                by="other",
                ts="2026",
                score=0.5,
                extras={},
            )
        ],
    ):
        results = unified_search(db, "x", consent_community=True)
    assert len(results) == 1


def test_session_consent_toggle():
    assert not session_consent_active()
    grant_session_consent()
    assert session_consent_active()
    revoke_session_consent()
    assert not session_consent_active()


def test_known_bugs_returns_empty_until_v014():
    """v0.14 stub — must return [] until that PRD ships."""
    from ulog._solutions import search_known_bugs

    assert search_known_bugs("anything") == []


def test_unified_search_returns_sorted_by_score(tmp_path):
    db = _seed_with_fix(tmp_path, "x", "local fix")
    # Inject a higher-score community-accepted item via mock.
    with patch(
        "ulog._solutions.search_community",
        return_value=[
            SearchResult(
                provenance="community-accepted",
                title="hi",
                writeup="community wins",
                by="other",
                ts="2026",
                score=1.0,
                extras={},
            )
        ],
    ):
        results = unified_search(db, "x", consent_community=True)
    assert results[0].provenance == "community-accepted"
    assert results[1].provenance == "local"
