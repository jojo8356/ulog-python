"""Community-solutions client (PRD-v0.15).

Thin client for the hosted `ulog.solutions` site:
  - fetch(signature)       — GET search results (anonymous; no auth)
  - publish(signature, …)  — POST a fix, signed via ed25519 keypair
                             bound to a GitHub OAuth identity
  - keygen(path)           — generate an ed25519 keypair (cryptography
                             package opt-in via `[solutions]` extra)

The hosted site itself is a separate project — this module is the
client that talks to it. A `docker/ulog-solutions/docker-compose.yml`
self-host recipe ships alongside so any team can run their own
private instance.

Per PRD-v0.15 Decision D1: ed25519 (RFC 8032) is the signature
scheme. Decision D5: keys are bound to a GH OAuth identity verified
by the server at first-publish time.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_ENDPOINT = "https://ulog.solutions/v1"
DEFAULT_KEY_PATH = Path.home() / ".config" / "ulog" / "solutions-key"


def fetch_signature(signature: str, *, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 2.0) -> list[dict[str, Any]]:
    """GET /search?sig=… — returns the raw `results` list, [] on error."""
    try:
        req = urllib.request.Request(
            f"{endpoint}/search?sig={signature}",
            headers={"User-Agent": "ulog/0.16"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return []
    return list(payload.get("results", []))


def publish(
    signature: str,
    writeup: str,
    by: str,
    *,
    private_key_path: Path | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """POST a fix to /publish. Signs the body via ed25519.

    Raises RuntimeError if the `cryptography` opt-in dep is missing.
    Returns the server's JSON response (or {"error": "..."}).
    """
    try:
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PrivateFormat,
            PublicFormat,
            NoEncryption,
            load_pem_private_key,
        )
    except ImportError as e:
        raise RuntimeError(
            "ulog solutions publish needs the cryptography package. "
            "Install with `pip install 'ulog[solutions]'`."
        ) from e

    key_path = private_key_path or DEFAULT_KEY_PATH
    if not key_path.exists():
        raise RuntimeError(
            f"no key at {key_path}; run `ulog solutions keygen` first"
        )
    private_key = load_pem_private_key(key_path.read_bytes(), password=None)

    body = json.dumps(
        {"signature": signature, "writeup": writeup, "by": by},
        sort_keys=True,
    ).encode("utf-8")

    signature_bytes = private_key.sign(body)  # ed25519 has no algo arg
    public_key_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )

    req = urllib.request.Request(
        f"{endpoint}/publish",
        data=body,
        headers={
            "User-Agent": "ulog/0.16",
            "Content-Type": "application/json",
            "X-Ulog-Signature": signature_bytes.hex(),
            "X-Ulog-Public-Key": public_key_pem.decode("ascii").replace("\n", "\\n"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return dict(json.load(resp))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}"}
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return {"error": str(e)}


def keygen(path: Path | None = None) -> Path:
    """Generate an ed25519 keypair, write the private key to `path`.

    Returns the actual path written. Raises RuntimeError if the
    cryptography opt-in dep is missing.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PrivateFormat,
            NoEncryption,
        )
    except ImportError as e:
        raise RuntimeError(
            "keygen needs the cryptography package. "
            "Install with `pip install 'ulog[solutions]'`."
        ) from e

    target = path or DEFAULT_KEY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    pk = Ed25519PrivateKey.generate()
    pem = pk.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    target.write_bytes(pem)
    target.chmod(0o600)
    return target
