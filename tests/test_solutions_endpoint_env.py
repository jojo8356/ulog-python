"""Tests for the ULOG_SOLUTIONS_ENDPOINT env var (PRD-v0.15 self-host)."""

from __future__ import annotations

from unittest.mock import patch

from ulog._solutions import _default_community_endpoint, search_community
from ulog._solutions_client import _resolved_endpoint, fetch_signature


def test_resolved_endpoint_env_override(monkeypatch):
    monkeypatch.setenv("ULOG_SOLUTIONS_ENDPOINT", "https://internal/v1")
    assert _resolved_endpoint() == "https://internal/v1"


def test_resolved_endpoint_default_when_unset(monkeypatch):
    monkeypatch.delenv("ULOG_SOLUTIONS_ENDPOINT", raising=False)
    assert _resolved_endpoint() == "https://ulog.solutions/v1"


def test_solutions_default_search_endpoint_env(monkeypatch):
    monkeypatch.setenv("ULOG_SOLUTIONS_ENDPOINT", "https://internal/v1")
    assert _default_community_endpoint() == "https://internal/v1/search"


def test_solutions_default_search_endpoint_default(monkeypatch):
    monkeypatch.delenv("ULOG_SOLUTIONS_ENDPOINT", raising=False)
    assert _default_community_endpoint() == "https://ulog.solutions/v1/search"


def test_search_community_uses_env_endpoint(monkeypatch):
    """The env var feeds into the actual fetch URL."""
    monkeypatch.setenv("ULOG_SOLUTIONS_ENDPOINT", "https://internal/v1")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = ConnectionError("expected")
        search_community("abc")
        called_req = mock_urlopen.call_args.args[0]
        assert "internal/v1/search" in called_req.full_url


def test_fetch_signature_uses_env_endpoint(monkeypatch):
    monkeypatch.setenv("ULOG_SOLUTIONS_ENDPOINT", "https://internal/v1")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = ConnectionError("expected")
        fetch_signature("abc")
        called_req = mock_urlopen.call_args.args[0]
        assert "internal/v1/search" in called_req.full_url
