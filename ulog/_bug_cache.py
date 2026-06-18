"""Known-bugs auto-lookup cache (PRD-v0.14).

Local SQLite cache of curated bug entries. The full v0.14 spec adds a
scraper for SO Data Dump / GitHub issues / official docs — this module
ships the storage + lookup layer + a `--source-file <json>` import
path so users can hand-curate matches before the scraper lands.

Cache lives at `~/.cache/ulog/bug-cache.sqlite` by default
(XDG_CACHE_HOME honored).

Schema:

    bugs (
        id INTEGER PRIMARY KEY,
        signature TEXT NOT NULL,    -- hex SHA-256 from ulog._fixes.signature
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        source TEXT NOT NULL,       -- "so" | "github" | "docs" | "manual"
        url TEXT,
        accepted INTEGER NOT NULL DEFAULT 0,
        ts DATETIME NOT NULL
    );
    CREATE INDEX ix_bugs_signature ON bugs(signature);

`ulog._solutions.search_known_bugs(sig)` queries this — once the
cache is populated, v0.16's unified search panel auto-displays
matches with the `known-bug` provenance.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


def default_cache_path() -> Path:
    """`~/.cache/ulog/bug-cache.sqlite` (XDG-aware)."""
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache / "ulog" / "bug-cache.sqlite"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bugs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT,
    accepted INTEGER NOT NULL DEFAULT 0,
    ts DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_bugs_signature ON bugs(signature);
"""


def _ensure_schema(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def import_from_json(path: Path, source_file: Path) -> int:
    """Bulk-import curated bug entries from a JSON file.

    Expected format: list of dicts with keys
    `signature` (required) / `title` (required) / `body` / `source`
    (default: 'manual') / `url` / `accepted` (default: false).

    Returns the number of rows inserted.
    """
    _ensure_schema(path)
    entries = json.loads(source_file.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("bug-cache JSON must be a list")
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None).isoformat()
    rows: list[tuple[str, str, str, str, Any, int, str]] = []
    for e in entries:
        if not e.get("signature") or not e.get("title"):
            continue
        rows.append(
            (
                e["signature"],
                e["title"],
                e.get("body", ""),
                e.get("source", "manual"),
                e.get("url"),
                1 if e.get("accepted") else 0,
                now,
            )
        )
    conn = sqlite3.connect(str(path))
    conn.executemany(
        "INSERT INTO bugs (signature, title, body, source, url, accepted, ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


def search_by_signature(path: Path, signature: str) -> list[dict[str, Any]]:
    """Lookup. Returns [] when the cache is missing or empty."""
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    rows = conn.execute(
        "SELECT signature, title, body, source, url, accepted, ts FROM bugs "
        "WHERE signature = ? ORDER BY accepted DESC, ts DESC",
        (signature,),
    ).fetchall()
    conn.close()
    return [
        {
            "signature": r[0],
            "title": r[1],
            "body": r[2],
            "source": r[3],
            "url": r[4],
            "accepted": bool(r[5]),
            "ts": r[6],
        }
        for r in rows
    ]


def count(path: Path) -> int:
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    n = conn.execute("SELECT count(*) FROM bugs").fetchone()[0]
    conn.close()
    return int(n)


def clear(path: Path) -> None:
    if path.exists():
        path.unlink()
