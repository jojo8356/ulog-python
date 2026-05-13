"""`ulog enable-fts5` — opt-in FTS5 mirror for full-text search (PRD-v0.4.4).

Creates a `logs_fts` SQLite FTS5 virtual table mirroring the `msg`
column, plus triggers to keep it in sync with future INSERT/UPDATE/
DELETE on `logs`. Backfills from existing rows in one statement.

After this runs, the viewer's adapter switches the `?q=` filter to a
SQL `MATCH` against logs_fts (sub-millisecond for million-record
archives) instead of the v0.2 `LIKE %q%` scan.

Idempotent: if the FTS table already exists, the command reports
the row count and exits 0.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "enable-fts5",
        help="Enable FTS5 full-text search on a stored SQLite DB.",
    )
    sp.add_argument("db", type=Path, help="Path to the log SQLite DB.")
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"ulog enable-fts5: DB not found: {args.db}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(str(args.db))
    try:
        # Detect FTS5 availability (compile-time option; usually on).
        try:
            conn.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
            conn.execute("DROP TABLE _fts5_probe")
        except sqlite3.OperationalError as e:
            print(f"ulog enable-fts5: FTS5 not available in this SQLite: {e}", file=sys.stderr)
            return 2

        # Idempotency: skip create if already done.
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='logs_fts'"
        ).fetchone()
        if existing:
            n = conn.execute("SELECT count(*) FROM logs_fts").fetchone()[0]
            print(
                f"ulog enable-fts5: logs_fts already exists ({n:,} rows). No-op.",
                file=sys.stderr,
            )
            return 0

        conn.executescript(
            """
            CREATE VIRTUAL TABLE logs_fts USING fts5(msg, content='logs', content_rowid='id');

            -- Backfill from existing rows.
            INSERT INTO logs_fts(rowid, msg) SELECT id, msg FROM logs;

            -- Keep in sync on future writes.
            CREATE TRIGGER logs_fts_ai AFTER INSERT ON logs BEGIN
                INSERT INTO logs_fts(rowid, msg) VALUES (new.id, new.msg);
            END;
            CREATE TRIGGER logs_fts_ad AFTER DELETE ON logs BEGIN
                INSERT INTO logs_fts(logs_fts, rowid, msg) VALUES('delete', old.id, old.msg);
            END;
            CREATE TRIGGER logs_fts_au AFTER UPDATE ON logs BEGIN
                INSERT INTO logs_fts(logs_fts, rowid, msg) VALUES('delete', old.id, old.msg);
                INSERT INTO logs_fts(rowid, msg) VALUES (new.id, new.msg);
            END;
            """
        )
        conn.commit()
        n = conn.execute("SELECT count(*) FROM logs_fts").fetchone()[0]
        print(
            f"ulog enable-fts5: indexed {n:,} records. "
            f"Future writes auto-sync via triggers.",
            file=sys.stderr,
        )
        return 0
    finally:
        conn.close()
