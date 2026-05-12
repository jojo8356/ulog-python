"""Seed a chain-integrity demo DB with incidents + resolves + reopens.

Produces a tiny but realistic DB to eyeball the Epic 5 / 6 GUI features
(detail-page Incident panel + sidebar Incidents quick filters).

Run:
    python3 scripts/seed_demo_incidents.py /tmp/incidents-demo.sqlite

Then:
    ulog-web --debug /tmp/incidents-demo.sqlite

Open / → click an ERROR row → see the Incident panel.
Sidebar 'Incidents' section: Open / Closed last 7d / Reopened with counts.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import ulog


def _flush_and_close() -> None:
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            h.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path, help="Output SQLite path.")
    args = parser.parse_args()

    db = args.db_path
    if db.exists():
        db.unlink()
    db.parent.mkdir(parents=True, exist_ok=True)

    ulog.setup(
        integrity="hash-chain",
        handlers=["sql"],
        sql_url=f"sqlite:///{db}",
        sql_batch_size=1,
    )
    log = ulog.get_logger("globex.payments")

    # 5 ERRORs with realistic messages.
    errors = [
        ("database connection timeout", "checkout.py", 187),
        ("stripe webhook signature mismatch", "stripe_adapter.py", 92),
        ("invoice PDF generation failed", "invoice.py", 244),
        ("rate limit exceeded (tenant=acme)", "shared/throttle.py", 53),
        ("auth provider returning 503", "oauth.py", 128),
    ]
    hashes: list[str] = []
    for msg, file, line in errors:
        with ulog.context(file=file, line=line):
            log.error(msg)
        _flush_and_close()
        time.sleep(0.02)  # keep ts strictly increasing

    # Fetch the 5 hashes we just emitted.
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT hex(record_hash) FROM logs "
                "WHERE level='ERROR' ORDER BY chain_pos ASC"
            )
        ).all()
    engine.dispose()
    hashes = [r[0] for r in rows]
    assert len(hashes) == 5

    # State plan:
    #   #1 → CLOSED (resolved by Johan)
    #   #2 → CLOSED (resolved by Erwan, with note)
    #   #3 → REOPENED (resolved then reopened)
    #   #4 → OPEN (never resolved)
    #   #5 → OPEN (never resolved)
    ulog.resolve(hashes[0], by="Johan", note="restarted db pool, set max_conn=50")
    ulog.resolve(hashes[1], by="Erwan", note="rotated stripe webhook secret")
    ulog.resolve(hashes[2], by="Johan", note="hotfix in invoice.py")
    ulog.reopen(hashes[2], reason="recurrence after deploy on 2026-05-04")
    _flush_and_close()

    print(f"\nSeeded {db}", file=sys.stderr)
    print(f"  5 incidents: 2 closed, 1 reopened, 2 open", file=sys.stderr)
    print(f"\nLaunch the viewer:", file=sys.stderr)
    print(f"  ulog-web --debug {db}", file=sys.stderr)
    print(f"\nCheck the CLI status mirror:", file=sys.stderr)
    print(f"  python3 -m ulog._cli incidents --db {db} --status all", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
