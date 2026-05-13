"""Seed a 100K-record chain-mode SQLite for `bench-export` (PRD-v0.6.4).

Run:
    python3 scripts/seed_bench_fixture.py tests/fixtures/bench_100k.sqlite

Idempotent: bails fast if the file already exists with >= 100K records.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(2026)

LEVEL_WEIGHTS = [("DEBUG", 15), ("INFO", 70), ("WARNING", 10), ("ERROR", 4), ("CRITICAL", 1)]
SECTORS = [f"globex.svc{i:03d}" for i in range(100)]
TENANTS = [f"tenant_{i:04d}" for i in range(1000)]

MESSAGES = [
    "checkout session %s started",
    "user %s authenticated",
    "cache miss key=%s",
    "rate limit hit",
    "stripe webhook delivered",
    "search served %d hits in %dms",
    "invoice %s issued",
    "queue depth %d",
]


def seed(path: Path, n: int = 100_000) -> None:
    if path.exists() and path.stat().st_size > 5_000_000:
        existing = sqlite3.connect(str(path)).execute("SELECT count(*) FROM logs").fetchone()[0]
        if existing >= n:
            print(f"fixture already at {path} ({existing} rows); skipping", file=sys.stderr)
            return

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(str(path))
    # v0.5 schema mirror (subset used by the exporter).
    conn.executescript(
        """
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME NOT NULL,
            level VARCHAR(10) NOT NULL,
            logger VARCHAR(255) NOT NULL,
            msg TEXT NOT NULL,
            file VARCHAR(255) NOT NULL,
            line INTEGER NOT NULL,
            exc JSON,
            context JSON,
            chain_pos INTEGER NOT NULL DEFAULT 0,
            record_hash BLOB,
            prev_hash BLOB,
            immutable INTEGER NOT NULL DEFAULT 0,
            is_replay INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX ix_logs_ts ON logs(ts);
        CREATE INDEX ix_logs_level ON logs(level);
        CREATE INDEX ix_logs_logger ON logs(logger);
        """
    )

    levels = [lv for lv, _ in LEVEL_WEIGHTS]
    weights = [w for _, w in LEVEL_WEIGHTS]

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = now - timedelta(days=7)
    span = (now - start).total_seconds()

    rows = []
    for i in range(n):
        lvl = random.choices(levels, weights=weights, k=1)[0]
        logger = random.choice(SECTORS)
        msg_template = random.choice(MESSAGES)
        try:
            if "%s" in msg_template and "%d" in msg_template:
                msg = msg_template % (random.choice(TENANTS), random.randint(1, 5000))
            elif "%d" in msg_template:
                msg = msg_template % (random.randint(1, 9999),)
            elif "%s" in msg_template:
                msg = msg_template % (random.choice(TENANTS),)
            else:
                msg = msg_template
        except TypeError:
            msg = msg_template

        ts = (start + timedelta(seconds=random.uniform(0, span))).isoformat()
        ctx = {"tenant_id": random.choice(TENANTS), "duration_s": round(random.uniform(0.001, 2.0), 4)}
        if random.random() < 0.3:
            ctx["service"] = logger.split(".", 1)[1]
        rows.append(
            (
                ts,
                lvl,
                logger,
                msg,
                f"{logger.split('.')[-1]}.py",
                random.randint(10, 500),
                None,
                json.dumps(ctx),
                i + 1,
            )
        )
        if i % 10000 == 0 and i:
            print(f"  …{i}/{n}", file=sys.stderr)

    print(f"inserting {len(rows)} records…", file=sys.stderr)
    conn.executemany(
        "INSERT INTO logs (ts, level, logger, msg, file, line, exc, context, chain_pos) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    print(f"wrote {path} ({path.stat().st_size / 1024 / 1024:.1f} MB)", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--records", type=int, default=100_000)
    args = parser.parse_args()
    seed(args.out, args.records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
