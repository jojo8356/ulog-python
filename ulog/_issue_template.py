"""Issue-template URL config + builder (Story 6.3 / FR111, NFR-SEC-51, G3).

Process-global stores the URL template configured via
`ulog.setup(issue_template_url=...)`. The renderer URL-encodes every
placeholder value before substitution so a user clicking the "Open
issue" link cannot inject markup or unbalanced query separators into
the target tracker.

Recognized placeholders:
    {msg}, {level}, {service}, {author}, {author_handle}, {commit_sha},
    {record_hash}, {labels}, {body}

`{body}` is a JSON list of 5 records (2 before + target + 2 after,
sliced by chain_pos). Resolution of {author*}/{commit_sha} is done
opportunistically by the caller via the blame index — keys absent
from the resolver dict are substituted with empty string.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

ISSUE_TEMPLATE_URL: str | None = None

_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_KNOWN_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "msg",
        "level",
        "service",
        "author",
        "author_handle",
        "commit_sha",
        "record_hash",
        "labels",
        "body",
    }
)


def set_issue_template_url(url: str | None) -> None:
    """Set (or clear, with `None`) the global issue-template URL."""
    if url is not None and not isinstance(url, str):
        raise TypeError(f"issue_template_url must be str or None, got {type(url).__name__}")
    global ISSUE_TEMPLATE_URL
    ISSUE_TEMPLATE_URL = url


def get_issue_template_url() -> str | None:
    return ISSUE_TEMPLATE_URL


def render_issue_url(template: str, values: dict[str, Any]) -> str:
    """Render `template` with `values`, URL-encoding each substitution.

    Only placeholders in `_KNOWN_PLACEHOLDERS` are substituted; others
    are left intact (NFR-SEC-51 — don't leak unintended state).
    Missing known keys become empty strings.
    """

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in _KNOWN_PLACEHOLDERS:
            return match.group(0)
        raw = values.get(name, "")
        if raw is None:
            raw = ""
        if name == "body" and not isinstance(raw, str):
            raw = json.dumps(raw, ensure_ascii=False, default=str)
        return urllib.parse.quote(str(raw), safe="")

    return _PLACEHOLDER_RE.sub(_sub, template)


def known_placeholders() -> frozenset[str]:
    return _KNOWN_PLACEHOLDERS
