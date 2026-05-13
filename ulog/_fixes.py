"""Local fix database (PRD-v0.13) — sidecar SQLite of resolved errors.

Signature = sha256(canonical_msg + stack_hash). Stored alongside the
main DB at `<main_db>.fixes.sqlite`. Next time the same error
fires, the viewer auto-links to the prior fix.

Schema:

    fixes (
        signature TEXT PRIMARY KEY,
        writeup TEXT NOT NULL,
        by TEXT NOT NULL,
        ts DATETIME NOT NULL,
        commit_sha TEXT
    )
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

_NUMBER_RE = re.compile(r"\d+")
# Hex run threshold = 6 chars (covers typical request IDs like `a1b2c3`)
_HEX_RE = re.compile(r"[0-9a-f]{6,}", re.IGNORECASE)


def canonical_msg(msg: str) -> str:
    """Strip numbers + hex IDs so 'timeout: req_abc123' and
    'timeout: req_def456' produce the same signature."""
    # Order matters: hex first (digits + letters), then plain digits.
    s = _HEX_RE.sub("H", msg)
    s = _NUMBER_RE.sub("N", s)
    return s.strip()


def signature(msg: str, stack: list[dict[str, Any]] | None = None) -> str:
    """sha256(canonical_msg + stack_hash). Stack is the optional v0.12
    capture; absent → falls back to msg-only signature."""
    cm = canonical_msg(msg)
    stack_hash = ""
    if stack:
        frames = [f"{f.get('file', '')}:{f.get('function', '')}" for f in stack]
        stack_hash = hashlib.sha256("\n".join(frames).encode("utf-8")).hexdigest()
    payload = f"{cm}\0{stack_hash}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fixes_db_path(main_db: Path) -> Path:
    """Sidecar location next to the main DB."""
    return main_db.with_suffix(main_db.suffix + ".fixes.sqlite")


_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS fixes (
    signature TEXT PRIMARY KEY,
    writeup TEXT NOT NULL,
    by TEXT NOT NULL,
    ts DATETIME NOT NULL,
    commit_sha TEXT
);
"""


def _ensure_schema(db_path: Path) -> None:
    import sqlite3

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA_DDL)
    conn.commit()
    conn.close()


def resolve_fix(
    main_db: Path,
    sig: str,
    writeup: str,
    by: str,
    commit_sha: str = "",
) -> None:
    """Insert or replace a fix entry."""
    import sqlite3

    path = fixes_db_path(main_db)
    _ensure_schema(path)
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT OR REPLACE INTO fixes(signature, writeup, by, ts, commit_sha) "
        "VALUES (?, ?, ?, ?, ?)",
        (sig, writeup, by, _dt.datetime.now(_dt.UTC).replace(tzinfo=None).isoformat(), commit_sha),
    )
    conn.commit()
    conn.close()


def unresolve_fix(main_db: Path, sig: str) -> bool:
    """Drop a fix entry. Returns True if a row was removed."""
    import sqlite3

    path = fixes_db_path(main_db)
    if not path.exists():
        return False
    conn = sqlite3.connect(str(path))
    cur = conn.execute("DELETE FROM fixes WHERE signature = ?", (sig,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n > 0


def lookup_fix(main_db: Path, sig: str) -> dict[str, Any] | None:
    """Return the matching fix entry as a dict, or None."""
    import sqlite3

    path = fixes_db_path(main_db)
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    row = conn.execute(
        "SELECT signature, writeup, by, ts, commit_sha FROM fixes WHERE signature = ?",
        (sig,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "signature": row[0],
        "writeup": row[1],
        "by": row[2],
        "ts": row[3],
        "commit_sha": row[4],
    }


def list_fixes(main_db: Path) -> list[dict[str, Any]]:
    import sqlite3

    path = fixes_db_path(main_db)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    rows = conn.execute(
        "SELECT signature, writeup, by, ts, commit_sha FROM fixes ORDER BY ts DESC"
    ).fetchall()
    conn.close()
    return [
        {"signature": r[0], "writeup": r[1], "by": r[2], "ts": r[3], "commit_sha": r[4]}
        for r in rows
    ]
