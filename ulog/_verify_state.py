"""Verify-state sidecar I/O (Story 3.10 / Decision D2).

`ulog verify` (Story 3.7) writes its result to `<db>.verify_state.json`
on a full-chain walk so the viewer can render the integrity badge
without re-walking the chain on every page load.

Schema (version 1):
{
  "version": 1,
  "status": "OK" | "BROKEN",
  "broken_at": null | <chain_pos>,
  "verified_up_to_chain_pos": <int>,
  "last_check_ts": "<ISO UTC>",
  "walk_time_s": <float>
}
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

STATE_VERSION = 1


def sidecar_path(db_path: Path) -> Path:
    return db_path.with_suffix(".verify_state.json")


def write_verify_state(db_path: Path, payload: dict[str, Any]) -> None:
    """Atomic-ish write — temp file + os.replace. Stdlib only."""
    target = sidecar_path(db_path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"version": STATE_VERSION, **payload}, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, target)


def read_verify_state(db_path: Path) -> dict[str, Any] | None:
    """Return parsed sidecar, or None if missing."""
    target = sidecar_path(db_path)
    if not target.exists():
        return None
    parsed: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    return parsed
