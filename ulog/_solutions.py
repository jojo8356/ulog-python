"""Unified solution search (PRD-v0.16).

Orchestrates 3 sources behind one consent-gated panel:
  - local: v0.13 sidecar fixes DB (always queried, zero network).
  - known-bugs: v0.14 local bug cache (queried when SDK present).
  - community: v0.15 hosted ulog.solutions endpoint (consent-gated).

Returns a merged + reranked list of results with a `provenance` tag
on each item. Network calls (community) ONLY fire when consent for
THIS record is given (the viewer renders a modal).

v0.14 and v0.15 ship later — the stubs here return [] until those
land, so v0.16 is shippable today against v0.13 alone.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ulog._fixes import lookup_fix, signature


@dataclass
class SearchResult:
    provenance: str  # "local" | "community" | "known-bug"
    title: str
    writeup: str
    by: str
    ts: str
    score: float
    extras: dict[str, Any]


# Rerank weights per Decision D3 of PRD-v0.16.
_PROVENANCE_WEIGHTS = {
    "community-accepted": 1.0,
    "local-trusted": 0.85,
    "known-bug-accepted": 0.75,
    "community": 0.50,
    "local": 0.40,
    "known-bug": 0.30,
}


def search_local(main_db: Path, sig: str) -> list[SearchResult]:
    """v0.13 backend — always available, zero network."""
    entry = lookup_fix(main_db, sig)
    if entry is None:
        return []
    return [
        SearchResult(
            provenance="local",
            title=entry["writeup"][:60],
            writeup=entry["writeup"],
            by=entry["by"],
            ts=entry["ts"],
            score=_PROVENANCE_WEIGHTS["local"],
            extras={"commit_sha": entry.get("commit_sha", "")},
        )
    ]


def search_known_bugs(sig: str) -> list[SearchResult]:
    """v0.14 backend — local bug cache. Empty until v0.14 ships."""
    return []


def search_community(sig: str, *, endpoint: str = "https://ulog.solutions/v1/search") -> list[SearchResult]:
    """v0.15 backend — community site lookup.

    Network call gated by the caller (the viewer's consent modal).
    Returns [] on any error (timeout, 5xx, DNS, missing deps).
    """
    try:
        req = urllib.request.Request(
            f"{endpoint}?sig={sig}",
            headers={"User-Agent": "ulog/0.16"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            import json as _j

            payload = _j.load(resp)
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return []
    out: list[SearchResult] = []
    for item in payload.get("results", []):
        out.append(
            SearchResult(
                provenance="community-accepted" if item.get("accepted") else "community",
                title=str(item.get("title", ""))[:60],
                writeup=str(item.get("writeup", "")),
                by=str(item.get("by", "anon")),
                ts=str(item.get("ts", "")),
                score=_PROVENANCE_WEIGHTS["community-accepted" if item.get("accepted") else "community"],
                extras={"url": item.get("url", "")},
            )
        )
    return out


def unified_search(
    main_db: Path,
    msg: str,
    stack: list[dict[str, Any]] | None = None,
    *,
    consent_community: bool = False,
) -> list[SearchResult]:
    """Fan-out across all 3 backends + rerank.

    `consent_community=False` skips the community fetch entirely
    (no network call). This is the per-record consent gate (D2).
    """
    sig = signature(msg, stack)
    results: list[SearchResult] = []
    results.extend(search_local(main_db, sig))
    results.extend(search_known_bugs(sig))
    if consent_community:
        results.extend(search_community(sig))
    # Dedup: same provenance + same writeup hash → keep first.
    seen: set[tuple[str, str]] = set()
    deduped: list[SearchResult] = []
    for r in results:
        key = (r.provenance, r.writeup[:120])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    deduped.sort(key=lambda r: r.score, reverse=True)
    return deduped


def session_consent_active() -> bool:
    """Process-global session consent flag. Toggled via API."""
    return _SESSION_CONSENT


_SESSION_CONSENT: bool = False


def grant_session_consent() -> None:
    global _SESSION_CONSENT
    _SESSION_CONSENT = True


def revoke_session_consent() -> None:
    global _SESSION_CONSENT
    _SESSION_CONSENT = False
