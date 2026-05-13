"""`ulog snapshot` — multi-format point-in-time export (PRD-v0.6.1).

Generalises `ulog export-html` to 5 output formats:
  - html : delegates to ulog export-html (full directory bundle)
  - log  : qlnes-style plain text, one record per line
  - jsonl: line-delimited JSON (same shape as JSONLineHandler)
  - csv  : RFC 4180 CSV (same shape as CSVHandler)
  - pdf  : HTML rendered to PDF via headless Chromium (opt-in dep)

--since accepts: today / yesterday / Nm / Nh / Nd / Nw / Ny / ISO date.
Default --since = today (00:00 UTC).
"""

from __future__ import annotations

import argparse
import csv as _csv
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

SUPPORTED_FORMATS = ("html", "log", "jsonl", "csv", "pdf")


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "snapshot",
        help="Multi-format snapshot of stored records (html/log/jsonl/csv/pdf).",
    )
    sp.add_argument("input", type=Path, help="Path to the log SQLite DB (or JSONL/CSV).")
    sp.add_argument(
        "--format",
        choices=SUPPORTED_FORMATS,
        default="log",
        help="Output format (default: log).",
    )
    sp.add_argument("--out", type=Path, required=True, help="Output path (file or directory).")
    sp.add_argument("--since", default="today", help="Time span. Default: today.")
    sp.add_argument("--filter", dest="filter_dsl", default="", help="DSL filter expression.")
    sp.add_argument("--force", action="store_true", help="Overwrite existing output.")
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not args.input.exists():
        print(f"ulog snapshot: input not found: {args.input}", file=sys.stderr)
        return 2

    since_iso = _parse_since(args.since)
    if args.out.exists() and not args.force and args.format != "html":
        print(f"ulog snapshot: output exists: {args.out} (pass --force)", file=sys.stderr)
        return 2

    records = _load_records(args.input, since_iso, args.filter_dsl)

    if args.format == "html":
        return _export_html(args, records, since_iso)
    if args.format == "log":
        return _export_log(args.out, records)
    if args.format == "jsonl":
        return _export_jsonl(args.out, records)
    if args.format == "csv":
        return _export_csv(args.out, records)
    if args.format == "pdf":
        return _export_pdf(args, records, since_iso)
    print(f"ulog snapshot: unknown format {args.format!r}", file=sys.stderr)
    return 2


# ---- helpers ------------------------------------------------------------


_SPAN_DAYS = {"m": 30.0, "d": 1.0, "h": 1 / 24, "w": 7.0, "y": 365.0}


def _parse_since(s: str) -> str:
    s = s.strip().lower()
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    if s == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    if s == "yesterday":
        d = now.replace(hour=0, minute=0, second=0, microsecond=0) - _dt.timedelta(days=1)
        return d.isoformat()
    if s and s[-1] in _SPAN_DAYS:
        try:
            n = float(s[:-1])
            return (now - _dt.timedelta(days=n * _SPAN_DAYS[s[-1]])).isoformat()
        except ValueError:
            pass
    try:
        return _dt.datetime.fromisoformat(s).isoformat()
    except ValueError as e:
        raise SystemExit(f"ulog snapshot: bad --since {s!r}: {e}") from e


def _load_records(input_path: Path, since_iso: str, filter_dsl: str) -> list[Any]:
    from ulog.web.viewer.adapters import Filters, get_adapter

    adapter = get_adapter(input_path)
    # Pull everything then filter in Python — Filters.ts_from sometimes
    # mis-handles naive vs aware datetimes across SQLAlchemy + SQLite.
    result = adapter.query(Filters(), page=1, page_size=10_000_000)
    records = [r for r in result.records if r.ts and str(r.ts) >= since_iso]
    # Secondary sort by id preserves insertion order within same-ts batches.
    records.sort(key=lambda r: (str(r.ts), r.id))
    if filter_dsl:
        from ulog._filter_dsl import FilterParseError, parse

        try:
            pred = parse(filter_dsl).to_predicate()
        except FilterParseError as e:
            raise SystemExit(f"ulog snapshot: invalid --filter: {e}") from e
        records = [r for r in records if pred(_record_to_dict(r))]
    return records


def _record_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "ts": r.ts,
        "level": r.level,
        "logger": r.logger,
        "msg": r.msg,
        "file": r.file,
        "line": r.line,
        "context": dict(r.context),
    }


# ---- format-specific writers --------------------------------------------


def _export_log(out: Path, records: list[Any]) -> int:
    """qlnes plain text — one record per line."""
    lines: list[str] = []
    for r in records:
        if r.level == "INFO":
            line = f"{r.ts}  {r.logger}  {r.msg}"
        else:
            line = f"{r.ts}  {r.logger}: {r.level.lower()}: {r.msg}"
        lines.append(line)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ulog snapshot: wrote {len(records)} records → {out}", file=sys.stderr)
    return 0


def _export_jsonl(out: Path, records: list[Any]) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(_record_to_dict(r), default=str))
            fh.write("\n")
    print(f"ulog snapshot: wrote {len(records)} records → {out}", file=sys.stderr)
    return 0


def _export_csv(out: Path, records: list[Any]) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["ts", "level", "logger", "msg", "file", "line", "context_json"])
        for r in records:
            w.writerow(
                [r.ts, r.level, r.logger, r.msg, r.file, r.line, json.dumps(dict(r.context))]
            )
    print(f"ulog snapshot: wrote {len(records)} records → {out}", file=sys.stderr)
    return 0


def _export_html(args: argparse.Namespace, records: list[Any], since_iso: str) -> int:
    """Delegate to `ulog.web.export.HtmlExporter`."""
    from ulog.web.export import ExportOptions, HtmlExporter

    opts = ExportOptions(
        output=args.out,
        filter_dsl=args.filter_dsl,
        force=args.force,
        force_cap=True,
    )
    HtmlExporter(args.input, opts).run()
    return 0


def _export_pdf(args: argparse.Namespace, records: list[Any], since_iso: str) -> int:
    """Render HTML to PDF via headless Chromium (Playwright opt-in)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "ulog snapshot: --format pdf requires Playwright. Install with:\n"
            "  pip install 'ulog[snapshot-pdf]'  (or ulog[dev,web-dev])\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    # Build a transient HTML export, then render its index page to PDF.
    import tempfile

    from ulog.web.export import ExportOptions, HtmlExporter

    with tempfile.TemporaryDirectory() as td:
        html_dir = Path(td) / "html"
        HtmlExporter(
            args.input,
            ExportOptions(
                output=html_dir,
                filter_dsl=args.filter_dsl,
                inline_data=True,
                force=True,
                force_cap=True,
            ),
        ).run()
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{html_dir.resolve()}/index.html")
            page.wait_for_load_state("networkidle")
            page.pdf(path=str(args.out), format="A4", print_background=True)
            browser.close()
    print(f"ulog snapshot: wrote {len(records)} records (PDF) → {args.out}", file=sys.stderr)
    return 0
