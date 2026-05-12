"""Incident lifecycle — resolve / reopen + state walk (Epic 5).

`resolve()` / `reopen()` are the public APIs (re-exported from
`ulog.__init__`). Both emit a new immutable record into the active
chain via the configured SQLHandler, with `resolves=<hash>` in
context.

`compute_states(adapter)` walks the chain and returns the
current state per incident (latest-wins, per FR106).
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from . import context as _ulog_context
from .setup import get_logger


def _find_sql_handler() -> Any:
    """Locate the active ulog-managed SQLHandler.

    Raises RuntimeError if not configured (resolve/reopen require
    a SQL handler with `integrity='hash-chain'`).
    """
    from .handlers.sql import SQLHandler

    for h in logging.getLogger().handlers:
        if isinstance(h, SQLHandler):
            return h
    raise RuntimeError(
        "ulog incidents require a SQL handler — call "
        "`ulog.setup(handlers=['sql'], integrity='hash-chain', ...)` first"
    )


def _lookup_record_by_hash(handler: Any, incident_hash: str) -> Any:
    """Return the row whose `record_hash` matches `incident_hash` (hex prefix OK).

    Raises LookupError when no row matches (PRD-v0.5 §2.3 edge case).
    """
    from sqlalchemy import text

    if not incident_hash or not isinstance(incident_hash, str):
        raise LookupError(f"empty / non-string incident_hash: {incident_hash!r}")
    # Accept hex prefix ≥ 4 chars — same convention as `ulog verify`.
    if len(incident_hash) < 4:
        raise LookupError(f"incident_hash too short (need ≥4 hex chars): {incident_hash!r}")
    h_norm = incident_hash.lower().strip()

    # Flush any pending records first so an incident emitted moments ago
    # is visible.
    handler.flush()

    with handler._engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, chain_pos, record_hash, msg, level, ts "
                "FROM logs WHERE hex(record_hash) LIKE :prefix LIMIT 2"
            ),
            {"prefix": h_norm + "%"},
        ).all()
    if not row:
        raise LookupError(f"no record with hash prefix {incident_hash!r}")
    if len(row) > 1:
        raise LookupError(f"ambiguous hash prefix {incident_hash!r} — matches multiple records")
    return row[0]


def _git_head_sha() -> str:
    """Return short `git rev-parse HEAD` or empty string when unavailable."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return os.environ.get("GIT_COMMIT", "")


def resolve(incident_hash: str, by: str, note: str = "") -> None:
    """Emit a `RESOLVED` record referencing `incident_hash`.

    FK validation: `incident_hash` must exist as a `record_hash` in
    the chain (hex-prefix lookup, ≥4 chars). Raises LookupError if
    absent (PRD-v0.5 §2.3).

    Story 6 detail-view cross-links read the `resolves=<hash>`
    context field.
    """
    handler = _find_sql_handler()
    target = _lookup_record_by_hash(handler, incident_hash)
    # Resolve the canonical hex form of the target so cross-links don't
    # need to fuzzy-match.
    target_hash_hex = bytes(target.record_hash).hex()
    with _ulog_context.context(
        resolves=target_hash_hex,
        by=by,
        note=note,
        commit_sha=_git_head_sha(),
        incident_action="resolve",
    ):
        get_logger().info("RESOLVED")
    handler.flush()


def reopen(incident_hash: str, reason: str = "") -> None:
    """Emit a `REOPENED` record referencing `incident_hash`.

    Same FK rules as `resolve()`.
    """
    handler = _find_sql_handler()
    target = _lookup_record_by_hash(handler, incident_hash)
    target_hash_hex = bytes(target.record_hash).hex()
    with _ulog_context.context(
        resolves=target_hash_hex,
        reason=reason,
        commit_sha=_git_head_sha(),
        incident_action="reopen",
    ):
        get_logger().info("REOPENED")
    handler.flush()


# ---- State walk (Story 5.3) ----------------------------------------------


@dataclass(frozen=True)
class IncidentState:
    """One incident's current state, derived from the chain walk."""

    incident_hash: str
    state: str  # "open" | "closed" | "reopened"
    last_action: dict[str, Any]  # last RESOLVED / REOPENED record dict, or {} for open
    opened_ts: str  # ts of the original incident record
    last_action_ts: str  # ts of the latest resolve/reopen, or = opened_ts when open


def compute_states(records: list[Any]) -> dict[str, IncidentState]:
    """Walk a list of records and return per-incident current state.

    Inputs: every record from the chain (any order — sorted internally
    by chain_pos ASC for latest-wins).
    Output keyed by the resolved incident hash (the hash being
    referenced via `context.resolves`, OR the record's own hash if
    it's a candidate incident-bearing record).

    `state` semantics (FR106 — latest-wins):
      - "open": the original record exists but no resolve/reopen yet.
      - "closed": the latest action is "resolve".
      - "reopened": the latest action is "reopen".

    An incident is anything with `level >= ERROR` (a strong default; UI
    can override). The chain walk also includes records explicitly
    referenced by a resolve/reopen action even if their level < ERROR
    (e.g. a WARNING the user decided to track).
    """
    # Order-agnostic: sort by chain_pos ASC so the last action processed
    # is the one with the highest chain_pos (FR106 latest-wins).
    records = sorted(records, key=lambda r: int(_get(r, "chain_pos", 0)))
    states: dict[str, IncidentState] = {}
    by_hash: dict[str, Any] = {}

    # Pass 1: index records by their own hash.
    for r in records:
        rh = r.get("record_hash") if isinstance(r, dict) else getattr(r, "record_hash", None)
        if rh:
            hex_h = bytes(rh).hex() if isinstance(rh, (bytes, bytearray)) else str(rh)
            by_hash[hex_h] = r

    # Pass 2: every ERROR/CRITICAL record is an incident candidate (open
    # by default).
    for r in records:
        level = _get(r, "level", "")
        rh = _get(r, "record_hash", None)
        if not rh:
            continue
        hex_h = bytes(rh).hex() if isinstance(rh, (bytes, bytearray)) else str(rh)
        if level in ("ERROR", "CRITICAL"):
            ts = _get(r, "ts", "")
            states[hex_h] = IncidentState(
                incident_hash=hex_h,
                state="open",
                last_action={},
                opened_ts=str(ts),
                last_action_ts=str(ts),
            )

    # Pass 3: apply resolve/reopen actions in order.
    for r in records:
        ctx = _get(r, "context", {}) or {}
        action = ctx.get("incident_action")
        if action not in ("resolve", "reopen"):
            continue
        target = ctx.get("resolves")
        if not target:
            continue
        ts = _get(r, "ts", "")
        # Auto-track the target even when level < ERROR.
        if target not in states:
            origin = by_hash.get(target)
            opened_ts = _get(origin, "ts", "") if origin is not None else ""
            states[target] = IncidentState(
                incident_hash=target,
                state="open",
                last_action={},
                opened_ts=str(opened_ts),
                last_action_ts=str(opened_ts),
            )
        new_state = "closed" if action == "resolve" else "reopened"
        states[target] = IncidentState(
            incident_hash=target,
            state=new_state,
            last_action=_record_as_dict(r),
            opened_ts=states[target].opened_ts,
            last_action_ts=str(ts),
        )
    return states


def _get(r: Any, name: str, default: Any) -> Any:
    if isinstance(r, dict):
        return r.get(name, default)
    return getattr(r, name, default)


def _record_as_dict(r: Any) -> dict[str, Any]:
    if isinstance(r, dict):
        return dict(r)
    return {
        "id": getattr(r, "id", None),
        "chain_pos": getattr(r, "chain_pos", 0),
        "ts": getattr(r, "ts", ""),
        "level": getattr(r, "level", ""),
        "msg": getattr(r, "msg", ""),
        "context": dict(getattr(r, "context", {}) or {}),
    }
