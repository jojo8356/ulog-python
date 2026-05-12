"""`ulog incidents` CLI subcommand (Epic 5 / Stories 5.4 + 5.5).

Supports two modes:
  - `--status open|closed|reopened|all` — list incidents, exit code = open count
    (FR107). Useful as a CI gate.
  - `--report --since <span>` — print a Markdown KPI table over the time span
    (FR108): opened / closed / net debt / MTTR / P95 / reopens / top closers.

The state walk lives in `ulog._incidents.compute_states` (Story 5.3).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "incidents",
        help="List incidents (CI gate) or print a Markdown KPI report.",
    )
    sp.add_argument("--db", required=True, help="Path to the SQLite DB.")
    sp.add_argument(
        "--status",
        choices=("open", "closed", "reopened", "all"),
        help="List incidents in this state. Exit code = open count.",
    )
    sp.add_argument(
        "--report",
        action="store_true",
        help="Print a Markdown KPI report. Requires --since.",
    )
    sp.add_argument(
        "--since",
        help="Time span for --report (e.g. '1m', '7d', '24h'). "
        "Accepts ISO date too (e.g. '2026-04-01').",
    )
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not Path(args.db).exists():
        print(f"ulog incidents: DB not found: {args.db}", file=sys.stderr)
        return 2

    records = _load_records(args.db)
    from .._incidents import compute_states

    states = compute_states(records)

    if args.report:
        if not args.since:
            print("ulog incidents: --report requires --since", file=sys.stderr)
            return 2
        since_dt = _parse_since(args.since)
        report = _build_report(records, states, since_dt)
        print(report)
        return 0

    if args.status:
        return _print_status(states, args.status)

    # Default: brief summary.
    open_n = sum(1 for s in states.values() if s.state in ("open", "reopened"))
    closed_n = sum(1 for s in states.values() if s.state == "closed")
    print(f"incidents: {open_n} open, {closed_n} closed (of {len(states)} tracked).")
    return open_n


# ---- helpers -------------------------------------------------------------


def _load_records(db: str) -> list[dict[str, Any]]:
    """Read all chain records into a uniform dict shape."""
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, chain_pos, ts, level, logger, msg, "
                "hex(record_hash) AS hh, context "
                "FROM logs ORDER BY chain_pos ASC"
            )
        ).all()
    engine.dispose()
    out: list[dict[str, Any]] = []
    for r in rows:
        ctx = json.loads(r.context) if r.context else {}
        out.append(
            {
                "id": r.id,
                "chain_pos": r.chain_pos,
                "ts": r.ts,
                "level": r.level,
                "logger": r.logger,
                "msg": r.msg,
                "record_hash": bytes.fromhex(r.hh) if r.hh else None,
                "context": ctx,
            }
        )
    return out


def _print_status(states: dict[str, Any], filt: str) -> int:
    """FR107 — list incidents matching `filt` (open/closed/reopened/all)."""
    selected = [
        s
        for s in states.values()
        if filt == "all" or s.state == filt or (filt == "open" and s.state == "reopened")
    ]
    selected.sort(key=lambda s: s.last_action_ts or s.opened_ts)
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    for s in selected:
        age = _format_age(s.opened_ts, now)
        print(f"#{s.incident_hash[:8]}  {s.opened_ts:<20}  [{s.state}]  age={age}")
    open_n = sum(1 for s in states.values() if s.state in ("open", "reopened"))
    return open_n


def _format_age(opened_iso: str, now: _dt.datetime) -> str:
    try:
        t = _dt.datetime.fromisoformat(opened_iso.replace("Z", "+00:00"))
        if t.tzinfo is not None:
            t = t.replace(tzinfo=None)
        delta = now - t
    except ValueError:
        return "?"
    days = delta.days
    if days >= 1:
        return f"{days}d"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h"
    return f"{delta.seconds // 60}m"


_SPAN_UNITS = {"m": 30, "d": 1, "h": 1 / 24, "w": 7, "y": 365}


def _parse_since(s: str) -> _dt.datetime:
    """Accept '1m' / '7d' / '24h' / '4w' / '1y' or an ISO date."""
    s = s.strip()
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    if s and s[-1].lower() in _SPAN_UNITS:
        try:
            n = float(s[:-1])
            unit = s[-1].lower()
            delta_days = n * _SPAN_UNITS[unit]
            return now - _dt.timedelta(days=delta_days)
        except ValueError:
            pass
    try:
        return _dt.datetime.fromisoformat(s)
    except ValueError as e:
        raise SystemExit(f"ulog incidents: bad --since {s!r}: {e}") from e


def _build_report(
    records: list[dict[str, Any]],
    states: dict[str, Any],
    since: _dt.datetime,
) -> str:
    """FR108 — Markdown table of KPIs over a time window."""
    since_iso = since.isoformat(timespec="seconds")
    opened_since = [
        r for r in records if r["level"] in ("ERROR", "CRITICAL") and r["ts"] >= since_iso
    ]
    resolved_since = [
        r
        for r in records
        if r["context"].get("incident_action") == "resolve" and r["ts"] >= since_iso
    ]
    reopened_since = [
        r
        for r in records
        if r["context"].get("incident_action") == "reopen" and r["ts"] >= since_iso
    ]

    # MTTR + P95 — time from open ts to first resolve ts, per incident hash.
    by_hash_open: dict[str, str] = {}
    for r in records:
        rh = r.get("record_hash")
        if not rh:
            continue
        h = bytes(rh).hex()
        if r["level"] in ("ERROR", "CRITICAL") and h not in by_hash_open:
            by_hash_open[h] = r["ts"]

    durations_s: list[float] = []
    closers: dict[str, int] = {}
    for r in resolved_since:
        target = r["context"].get("resolves")
        if not target or target not in by_hash_open:
            continue
        try:
            t_open = _dt.datetime.fromisoformat(by_hash_open[target])
            t_close = _dt.datetime.fromisoformat(r["ts"])
            durations_s.append((t_close - t_open).total_seconds())
        except ValueError:
            continue
        who = str(r["context"].get("by") or "anon")
        closers[who] = closers.get(who, 0) + 1

    mttr = _fmt_duration(statistics.mean(durations_s)) if durations_s else "—"
    p95 = _fmt_duration(_percentile(durations_s, 95.0)) if durations_s else "—"

    top_closers = sorted(closers.items(), key=lambda kv: -kv[1])[:5]
    top_closers_str = ", ".join(f"{who} ({n})" for who, n in top_closers) if top_closers else "—"

    net_debt = len(opened_since) - len(resolved_since)

    lines = [
        f"# Incidents report — since {since_iso}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Opened | {len(opened_since)} |",
        f"| Closed | {len(resolved_since)} |",
        f"| Net debt | {net_debt:+d} |",
        f"| MTTR | {mttr} |",
        f"| P95 time-to-close | {p95} |",
        f"| Reopens | {len(reopened_since)} |",
        f"| Top closers | {top_closers_str} |",
    ]
    return "\n".join(lines)


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs_sorted = sorted(xs)
    k = max(0, min(len(xs_sorted) - 1, round((p / 100.0) * (len(xs_sorted) - 1))))
    return xs_sorted[k]


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"
