"""Tests for v0.15 — community-solutions client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ulog._cli import main as cli_main
from ulog._solutions_client import (
    DEFAULT_ENDPOINT,
    fetch_signature,
    keygen,
    publish,
)


# ---- fetch (read-only, anonymous) ---------------------------------------


def test_fetch_unreachable_endpoint_returns_empty():
    """Network failure → []. Confirms graceful fallback."""
    assert fetch_signature("abc", endpoint="http://127.0.0.1:1/nope") == []


def test_fetch_parses_results_field():
    payload = b'{"results": [{"title": "fix", "by": "x"}]}'
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    with patch("urllib.request.urlopen", return_value=mock_resp):
        import json
        with patch("json.load", return_value={"results": [{"title": "fix", "by": "x"}]}):
            results = fetch_signature("sig123")
    assert len(results) == 1
    assert results[0]["title"] == "fix"


# ---- keygen + publish need cryptography opt-in ---------------------------


def test_keygen_needs_cryptography_or_works(tmp_path):
    """If cryptography is installed → success; otherwise RuntimeError."""
    try:
        import cryptography  # noqa: F401
        has_crypto = True
    except ImportError:
        has_crypto = False

    target = tmp_path / "key"
    if has_crypto:
        path = keygen(target)
        assert path.exists()
        assert path.stat().st_mode & 0o777 == 0o600
        # PEM-encoded private key starts with this header.
        assert b"BEGIN PRIVATE KEY" in path.read_bytes()
    else:
        with pytest.raises(RuntimeError, match="cryptography"):
            keygen(target)


def test_publish_without_key_raises_runtime_error(tmp_path):
    try:
        import cryptography  # noqa: F401
    except ImportError:
        pytest.skip("cryptography not installed")
    with pytest.raises(RuntimeError, match="no key"):
        publish("sig", "writeup", "alice", private_key_path=tmp_path / "missing-key")


# ---- CLI -----------------------------------------------------------------


def test_cli_keygen_writes_file(tmp_path, capsys):
    try:
        import cryptography  # noqa: F401
    except ImportError:
        pytest.skip("cryptography not installed")
    target = tmp_path / "key"
    rc = cli_main(["solutions", "keygen", "--path", str(target)])
    assert rc == 0
    assert target.exists()
    err = capsys.readouterr().err
    assert str(target) in err


def test_cli_fetch_no_results_returns_1(capsys):
    """fetch against an unroutable host → no matches → exit 1."""
    rc = cli_main(["solutions", "fetch", "abc", "--endpoint", "http://127.0.0.1:1/nope"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no matches" in err


def test_default_endpoint_constant():
    assert DEFAULT_ENDPOINT.startswith("https://")


def test_docker_recipe_exists():
    p = Path(__file__).resolve().parent.parent / "docker" / "ulog-solutions" / "docker-compose.yml"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "postgres:" in content
    assert "SOLUTIONS_GH_CLIENT_ID" in content
    assert "CC-BY-SA-4.0" in content
