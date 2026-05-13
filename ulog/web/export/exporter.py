"""HtmlExporter — drives the static-HTML export (Epic 8 / PRD-v0.6).

Spec: PRD-v0.6 §2.1.2 (output layout), §2.1.3 (data plumbing).

Pipeline:
  1. Validate output dir + record cap (8.2 / FR135, FR136).
  2. Load records via the existing adapter contract (8.3 / FR141).
  3. Apply --filter DSL (8.5 / FR131).
  4. Decide inline vs separate data (8.8 / FR134 heuristic).
  5. Render base.html + per-section pages via `render_to_string`
     (8.3 / FR140).
  6. Freeze integrity badge state (8.10 / FR143, FR144).
  7. Write `README.html` (8.11 / FR139).

The exporter intentionally shares 100% of templates with the live
viewer — see PRD-v0.6 §2.1.3 (SC5 of PRD-v0.6).
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ..viewer.adapters import (
    Adapter,
    Filters,
    QueryResult,
    detect_kind,
    get_adapter,
)
from .standalone import ensure_django_configured

# Sections recognised by --include (Story 8.6 / FR132).
SECTIONS: tuple[str, ...] = (
    "level",
    "sectors",
    "authors",
    "tests",
    "incidents",
    "multi-track",
    "docs",
    "integrity",
)
DEFAULT_INCLUDE: frozenset[str] = frozenset(SECTIONS)

# Heuristic threshold for inline-vs-separate data (Story 8.8).
INLINE_DATA_THRESHOLD = 10_000

# Hard cap on records (Story 8.2 / FR136).
HARD_CAP = 1_000_000

PAGE_SIZE = 1000


@dataclass
class ExportOptions:
    """Parsed CLI options for `ulog export-html`."""

    output: Path
    filter_dsl: str = ""
    include: frozenset[str] = DEFAULT_INCLUDE
    theme: Literal["light", "dark"] = "light"
    inline_data: bool | None = None  # None → heuristic
    force: bool = False
    force_cap: bool = False
    max_records: int = HARD_CAP
    repo: Path | None = None
    no_author_index: bool = False
    # PRD-v0.6 §2.1.4: page size for the records index.
    page_size: int = PAGE_SIZE

    def chosen_inline(self, n_records: int) -> bool:
        """Resolve the inline-vs-separate flag, applying the heuristic
        when neither was passed explicitly (Story 8.8)."""
        if self.inline_data is not None:
            return self.inline_data
        return n_records < INLINE_DATA_THRESHOLD


@dataclass
class ExportResult:
    """Summary returned by `HtmlExporter.run`."""

    output_dir: Path
    records_written: int
    pages_written: int
    inline_data: bool
    integrity_status: str  # "OK" | "BROKEN" | "missing"
    sections_emitted: list[str] = field(default_factory=list)


class HtmlExporter:
    """Drive the static HTML export from end to end."""

    def __init__(self, input_path: Path, options: ExportOptions) -> None:
        self.input_path = input_path
        self.options = options
        self.kind = detect_kind(input_path)
        ensure_django_configured(input_path, self.kind)
        self.adapter: Adapter = get_adapter(input_path)

    # ---- Entry point -----------------------------------------------------

    def run(self) -> ExportResult:
        opts = self.options
        out = opts.output

        if out.exists() and any(out.iterdir()) and not opts.force:
            raise SystemExit(
                f"ulog export-html: output dir {out} is non-empty; "
                "pass --force to overwrite."
            )
        out.mkdir(parents=True, exist_ok=True)

        # 1. Load all records, then apply --filter DSL predicate
        #    in-Python (the adapter Filters dataclass doesn't carry the
        #    full DSL grammar — same trade-off as the replay path).
        full = self.adapter.query(Filters(), page=1, page_size=10_000_000)
        if opts.filter_dsl:
            predicate = self._parse_filter_predicate()
            kept = [r for r in full.records if predicate(self._record_to_dict(r))]
            full = QueryResult(
                records=kept,
                total=len(kept),
                page=1,
                page_size=10_000_000,
                sector_counts=full.sector_counts,
                file_counts=full.file_counts,
                level_counts=full.level_counts,
                bound_keys=full.bound_keys,
                test_summary=full.test_summary,
            )

        n = len(full.records)
        if n > opts.max_records and not opts.force_cap:
            raise SystemExit(
                f"ulog export-html: {n:,} records exceed cap "
                f"({opts.max_records:,}); pass --force-cap to override."
            )

        # 2. Resolve inline-vs-separate.
        inline = opts.chosen_inline(n)

        # 3. Integrity freeze (Story 8.10).
        integrity = self._freeze_integrity()

        # 4. Static assets (CSS, README).
        self._copy_static_assets()

        # 5. Pages.
        pages_written = 0
        sections: list[str] = []

        # Always: index + record pages.
        pages_written += self._write_index_pages(full, inline, integrity)
        sections.append("level")
        for r in full.records:
            self._write_record_page(r, integrity)
            pages_written += 1

        if "incidents" in opts.include:
            self._write_incidents_page(full, integrity)
            pages_written += 1
            sections.append("incidents")

        if "multi-track" in opts.include:
            self._write_multi_track_page(integrity)
            pages_written += 1
            sections.append("multi-track")

        if "integrity" in opts.include:
            self._write_integrity_page(integrity, n_records=n)
            pages_written += 1
            sections.append("integrity")

        if "docs" in opts.include:
            self._write_docs_pages(integrity)
            sections.append("docs")

        # 6. README at root (Story 8.11).
        self._write_readme(inline=inline, n_records=n)
        pages_written += 1

        return ExportResult(
            output_dir=out,
            records_written=n,
            pages_written=pages_written,
            inline_data=inline,
            integrity_status=integrity.get("status", "missing"),
            sections_emitted=sections,
        )

    # ---- Filter / DSL ----------------------------------------------------

    def _parse_filter_predicate(self) -> Any:
        from ulog._filter_dsl import FilterParseError, parse

        try:
            return parse(self.options.filter_dsl).to_predicate()
        except FilterParseError as e:
            raise SystemExit(f"ulog export-html: invalid --filter: {e}") from e

    # ---- Integrity (Story 8.10) -----------------------------------------

    def _freeze_integrity(self) -> dict[str, Any]:
        """Snapshot the verify_state sidecar at export time."""
        from ulog._verify_state import read_verify_state

        state = read_verify_state(self.input_path)
        if state is None:
            return {"status": "missing"}
        # Add a frozen export timestamp so the badge tooltip shows
        # when the snapshot was taken (per FR143).
        out = dict(state)
        out["frozen_at"] = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")
        return out

    # ---- Static assets ---------------------------------------------------

    def _copy_static_assets(self) -> None:
        """Copy `static/ulog/` from the live viewer to the export.

        Falls back to a minimal embedded CSS when the static dir is
        absent — keeps the export self-contained even pre-Tailwind-build.
        """
        out_static = self.options.output / "static"
        out_static.mkdir(parents=True, exist_ok=True)
        # Locate the live viewer's static directory.
        src = Path(__file__).resolve().parent.parent / "static" / "ulog"
        if src.is_dir():
            shutil.copytree(src, out_static / "ulog", dirs_exist_ok=True)
        # Minimal theme CSS in case Tailwind hasn't been built yet
        # (Story 8.1 / Decision D3 acceleration).
        css = self.options.output / "static" / f"ulog-{self.options.theme}.css"
        if not css.exists():
            css.write_text(_MINIMAL_CSS_FALLBACK, encoding="utf-8")

    # ---- Index pages (Story 8.4) -----------------------------------------

    def _write_index_pages(
        self, result: QueryResult, inline: bool, integrity: dict[str, Any]
    ) -> int:
        """Paginate index.html at `PAGE_SIZE` records per page."""
        records = list(result.records)
        size = self.options.page_size
        pages = max(1, (len(records) + size - 1) // size)
        for p in range(pages):
            page_records = records[p * size : (p + 1) * size]
            ctx = self._base_context(integrity)
            ctx.update(
                {
                    "records": page_records,
                    "total": len(records),
                    "page": p + 1,
                    "total_pages": pages,
                    "sectors": sorted(result.sector_counts.items(), key=lambda kv: kv[0]),
                    "files": sorted(result.file_counts.items(), key=lambda kv: -kv[1]),
                    "level_summary": [
                        (lv, result.level_counts.get(lv, 0))
                        for lv in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
                    ],
                    "bound_keys": result.bound_keys,
                    "test_summary": result.test_summary,
                    "filters": Filters(),
                    "qs": "",
                    "qs_minus_test_id": "",
                    "record_authors": {},
                    "authors_summary": None,
                    "is_static_export": True,
                    "static_page_prefix": "" if p == 0 else f"page-{p+1}-",
                    "next_page_href": f"page-{p+2}.html" if p + 1 < pages else None,
                    "prev_page_href": (
                        "index.html" if p == 1 else f"page-{p}.html" if p > 1 else None
                    ),
                }
            )
            if inline:
                ctx["inline_records_json"] = json.dumps(
                    [self._record_to_dict(r) for r in page_records],
                    default=str,
                )
            else:
                # Write a sidecar JSON for this page.
                data_dir = self.options.output / "data"
                data_dir.mkdir(parents=True, exist_ok=True)
                (data_dir / f"records-page-{p+1}.json").write_text(
                    json.dumps(
                        [self._record_to_dict(r) for r in page_records],
                        default=str,
                    ),
                    encoding="utf-8",
                )
                ctx["records_data_url"] = f"data/records-page-{p+1}.json"
            html = self._render_list_html(ctx)
            name = "index.html" if p == 0 else f"page-{p+1}.html"
            (self.options.output / name).write_text(html, encoding="utf-8")
        return pages

    # ---- Record pages ----------------------------------------------------

    def _write_record_page(self, record: Any, integrity: dict[str, Any]) -> None:
        ctx = self._base_context(integrity)
        ctx.update(
            {
                "record": record,
                "test_id": record.context.get("test_id"),
                "test_summary_row": None,
                "test_record_count": 0,
                "author": None,
                "author_short_sha": "",
                "author_relative_date": "",
                "issue_url": None,
                "resolves_target": None,
                "resolved_by": [],
                "is_static_export": True,
            }
        )
        out_dir = self.options.output / "r"
        out_dir.mkdir(parents=True, exist_ok=True)
        html = self._render_detail_html(ctx)
        (out_dir / f"{record.id}.html").write_text(html, encoding="utf-8")

    # ---- Section pages ---------------------------------------------------

    def _write_incidents_page(self, result: QueryResult, integrity: dict[str, Any]) -> None:
        ctx = self._base_context(integrity)
        ctx.update(
            {
                "page_title": "Incidents",
                "section_heading": "Incidents",
                "section_body_html": "<p class='text-slate-500'>"
                "Incident lifecycle requires a chain-integrity SQLite DB. "
                "Open the live viewer for interactive triage.</p>",
            }
        )
        html = self._render_section_html(ctx)
        (self.options.output / "incidents.html").write_text(html, encoding="utf-8")

    def _write_multi_track_page(self, integrity: dict[str, Any]) -> None:
        ctx = self._base_context(integrity)
        ctx.update(
            {
                "page_title": "Multi-track",
                "section_heading": "Multi-track",
                "section_body_html": "<p class='text-slate-500'>"
                "Multi-track view is interactive (requires the live viewer). "
                "This frozen export shows the navigation entry for completeness.</p>",
            }
        )
        html = self._render_section_html(ctx)
        (self.options.output / "multi-track.html").write_text(html, encoding="utf-8")

    def _write_integrity_page(self, integrity: dict[str, Any], n_records: int) -> None:
        status = integrity.get("status", "missing")
        if status == "OK":
            heading = f"Integrity ✓ verified up to #{integrity.get('verified_up_to_chain_pos', '?')}"
            body = (
                "<p class='text-emerald-700'>"
                f"Verified up to <code>#{integrity.get('verified_up_to_chain_pos', '?')}</code> "
                f"at <code>{integrity.get('last_check_ts', '?')}</code>.</p>"
                f"<p class='text-slate-500 text-sm'>Snapshotted at export time: "
                f"<code>{integrity.get('frozen_at', '?')}</code>.</p>"
            )
        elif status == "BROKEN":
            heading = f"Integrity ✗ BROKEN at #{integrity.get('broken_at', '?')}"
            body = (
                "<p class='text-red-700'>"
                f"Chain BROKEN at <code>#{integrity.get('broken_at', '?')}</code>. "
                "Run <code>ulog repair --confirm</code> against the live DB to resolve.</p>"
            )
        else:
            heading = "Integrity: never verified"
            body = (
                "<p class='text-slate-500'>"
                "No verify_state.json sidecar found. Run <code>ulog verify &lt;db&gt;</code> "
                "before exporting to surface the chain status here.</p>"
            )
        ctx = self._base_context(integrity)
        ctx.update(
            {
                "page_title": "Integrity",
                "section_heading": heading,
                "section_body_html": body
                + f"<p class='text-xs text-slate-400 mt-3'>{n_records:,} records exported.</p>",
            }
        )
        html = self._render_section_html(ctx)
        (self.options.output / "integrity.html").write_text(html, encoding="utf-8")

    def _write_docs_pages(self, integrity: dict[str, Any]) -> None:
        """Mirror the in-app /docs/ pages — markdown rendered to HTML."""
        docs_src = Path(__file__).resolve().parent.parent / "docs"
        out_docs = self.options.output / "docs"
        out_docs.mkdir(parents=True, exist_ok=True)
        if not docs_src.is_dir():
            return
        for md in docs_src.glob("*.md"):
            ctx = self._base_context(integrity)
            ctx.update(
                {
                    "page_title": md.stem,
                    "section_heading": md.stem.replace("-", " ").title(),
                    "section_body_html": f"<pre>{_html_escape(md.read_text(encoding='utf-8'))}</pre>",
                }
            )
            html = self._render_section_html(ctx)
            (out_docs / f"{md.stem}.html").write_text(html, encoding="utf-8")

    # ---- README (Story 8.11) ---------------------------------------------

    def _write_readme(self, *, inline: bool, n_records: int) -> None:
        ulog_version = _read_ulog_version()
        readme = _README_TEMPLATE.format(
            ulog_version=ulog_version,
            export_format_version="0.6.0",
            n_records=f"{n_records:,}",
            inline_mode="inline-data" if inline else "separate-data",
            fetch_warning=(
                "Single-folder portable — every record JSON is embedded in the page."
                if inline
                else "Records live under <code>data/*.json</code>. Opening "
                "<code>index.html</code> via <code>file://</code> may fail because "
                "browsers block <code>fetch()</code> for local files. Workaround:"
                "<pre>python3 -m http.server -d &lt;export-dir&gt; 8000</pre>"
            ),
            theme=self.options.theme,
            generated_at=_dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        )
        (self.options.output / "README.html").write_text(readme, encoding="utf-8")

    # ---- Rendering -------------------------------------------------------

    def _base_context(self, integrity: dict[str, Any]) -> dict[str, Any]:
        return {
            "logs_path": str(self.input_path),
            "theme": self.options.theme,
            "is_static_export": True,
            "integrity": integrity,
        }

    def _render_list_html(self, ctx: dict[str, Any]) -> str:
        """Render the records-index page (static-export variant).

        v0.6 ships the in-house fallback renderer that produces a fully
        self-contained page (no CDN dep, no JS). Story 8.1 (Tailwind
        standalone CLI build) will let us re-use the live viewer's
        templates verbatim by linking the pre-built CSS instead of the
        CDN; until then, we render with the fallback to keep the export
        offline-clean.
        """
        return _fallback_list_html(ctx)

    def _render_detail_html(self, ctx: dict[str, Any]) -> str:
        return _fallback_detail_html(ctx)

    def _render_section_html(self, ctx: dict[str, Any]) -> str:
        return _fallback_section_html(ctx)

    @staticmethod
    def _record_to_dict(r: Any) -> dict[str, Any]:
        return {
            "id": r.id,
            "chain_pos": r.chain_pos,
            "ts": r.ts,
            "level": r.level,
            "logger": r.logger,
            "msg": r.msg,
            "file": r.file,
            "line": r.line,
            "context": dict(r.context),
        }


# ---- Helpers / fallbacks ---------------------------------------------------


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _read_ulog_version() -> str:
    try:
        import ulog

        return str(getattr(ulog, "__version__", "?"))
    except Exception:
        return "?"


_MINIMAL_CSS_FALLBACK = """\
/* Minimal CSS so the export is readable pre-Tailwind-build. */
body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 1rem; }
code, pre { font-family: ui-monospace, Menlo, monospace; }
table { border-collapse: collapse; width: 100%; }
th, td { padding: 4px 8px; border-bottom: 1px solid #e5e7eb; text-align: left; }
.level-ERROR { color: #b91c1c; font-weight: 600; }
.level-WARNING { color: #b45309; }
.level-CRITICAL { color: #fff; background: #b91c1c; padding: 2px 6px; border-radius: 4px; }
.integrity-OK { background: #d1fae5; color: #065f46; padding: 2px 8px; border-radius: 999px; }
.integrity-BROKEN { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 999px; }
.integrity-missing { background: #e5e7eb; color: #475569; padding: 2px 8px; border-radius: 999px; }
nav a { margin-right: 1rem; }
"""


def _badge_html(integrity: dict[str, Any]) -> str:
    status = integrity.get("status", "missing")
    if status == "OK":
        return (
            f'<span class="integrity-OK">Integrity ✓ #{integrity.get("verified_up_to_chain_pos", "?")}</span>'
        )
    if status == "BROKEN":
        return (
            f'<span class="integrity-BROKEN">Integrity ✗ BROKEN at #{integrity.get("broken_at", "?")}</span>'
        )
    return '<span class="integrity-missing">Integrity: never verified</span>'


def _fallback_list_html(ctx: dict[str, Any]) -> str:
    """Minimal in-house renderer; survives without the Django template."""
    records: list[Any] = ctx.get("records", [])
    integrity = ctx.get("integrity", {})
    badge = _badge_html(integrity)
    rows = []
    for r in records:
        msg = _html_escape(r.msg)
        rows.append(
            f"<tr><td>{r.ts}</td><td class='level-{r.level}'>{r.level}</td>"
            f"<td>{_html_escape(r.logger)}</td>"
            f"<td>{_html_escape(r.file)}:{r.line}</td>"
            f"<td><a href='r/{r.id}.html'>{msg}</a></td></tr>"
        )
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<title>ULog export — {ctx.get('total', 0)} records</title>"
        f"<link rel='stylesheet' href='static/ulog-{ctx.get('theme', 'light')}.css'>"
        "</head><body>"
        f"<header><nav><a href='index.html'>Records</a>"
        "<a href='incidents.html'>Incidents</a>"
        "<a href='multi-track.html'>Multi-track</a>"
        "<a href='integrity.html'>Integrity</a></nav>"
        f"{badge}</header>"
        f"<h1>{ctx.get('total', 0):,} records</h1>"
        "<table><thead><tr><th>TS</th><th>Level</th><th>Logger</th>"
        "<th>File</th><th>Message</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</body></html>"
    )


def _fallback_detail_html(ctx: dict[str, Any]) -> str:
    r = ctx["record"]
    integrity = ctx.get("integrity", {})
    badge = _badge_html(integrity)
    ctx_pairs = "".join(
        f"<dt>{_html_escape(k)}</dt><dd>{_html_escape(str(v))}</dd>"
        for k, v in r.context.items()
    )
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>Record #{r.id}</title>"
        f"<link rel='stylesheet' href='../static/ulog-{ctx.get('theme', 'light')}.css'>"
        "</head><body>"
        "<header><nav><a href='../index.html'>← Back to records</a></nav>"
        f"{badge}</header>"
        f"<h1>Record #{r.id} ({r.level})</h1>"
        f"<p><strong>ts:</strong> {r.ts}</p>"
        f"<p><strong>logger:</strong> {_html_escape(r.logger)}</p>"
        f"<p><strong>file:</strong> {_html_escape(r.file)}:{r.line}</p>"
        f"<h2>Message</h2><pre>{_html_escape(r.msg)}</pre>"
        f"{'<h2>Context</h2><dl>' + ctx_pairs + '</dl>' if ctx_pairs else ''}"
        "</body></html>"
    )


def _fallback_section_html(ctx: dict[str, Any]) -> str:
    integrity = ctx.get("integrity", {})
    badge = _badge_html(integrity)
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{_html_escape(str(ctx.get('page_title', 'ULog')))}</title>"
        f"<link rel='stylesheet' href='static/ulog-{ctx.get('theme', 'light')}.css'>"
        "</head><body>"
        "<header><nav><a href='index.html'>Records</a>"
        "<a href='incidents.html'>Incidents</a>"
        "<a href='multi-track.html'>Multi-track</a>"
        "<a href='integrity.html'>Integrity</a></nav>"
        f"{badge}</header>"
        f"<h1>{_html_escape(str(ctx.get('section_heading', '')))}</h1>"
        f"{ctx.get('section_body_html', '')}"
        "</body></html>"
    )


_README_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ULog export — README</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
    code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }}
    pre {{ background: #f3f4f6; padding: 8px; border-radius: 4px; overflow-x: auto; }}
    .meta {{ color: #475569; font-size: 0.875rem; margin-top: 2rem; }}
  </style>
</head>
<body>
  <h1>ULog static export</h1>
  <p>{n_records} records — exported {generated_at}</p>

  <h2>How to open</h2>
  <p>Start with <a href="index.html"><code>index.html</code></a>. Every other
  page is reachable from the navigation.</p>

  <h2>Data layout</h2>
  <p>This export is in <strong>{inline_mode}</strong> mode. {fetch_warning}</p>

  <h2>Metadata</h2>
  <ul>
    <li>ulog version: <code>{ulog_version}</code></li>
    <li>Export format version: <code>{export_format_version}</code></li>
    <li>Theme: <code>{theme}</code></li>
  </ul>

  <p class="meta">Generated by <code>ulog export-html</code>. See
  <code>STABILITY.md</code> at the ulog repo root for the long-term
  contract.</p>
</body>
</html>
"""


def cli_main(argv: list[str] | None = None) -> int:
    """`ulog export-html` entry point (Story 8.2)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="ulog export-html",
        description="Render a stored log file to a self-contained directory of HTML.",
    )
    parser.add_argument("input", type=Path, help="Path to the log file (.sqlite/.jsonl/.csv).")
    parser.add_argument("--output", type=Path, required=True, help="Output directory.")
    parser.add_argument("--filter", dest="filter_dsl", default="", help="DSL filter expression.")
    parser.add_argument(
        "--include",
        default="",
        help=(
            "Comma-separated section names to include. "
            f"Recognised: {', '.join(SECTIONS)}. Default: all."
        ),
    )
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--inline-data", action="store_true", dest="inline_data")
    grp.add_argument("--separate-data", action="store_true", dest="separate_data")
    parser.add_argument("--force", action="store_true", help="Overwrite non-empty output dir.")
    parser.add_argument("--force-cap", action="store_true", help="Bypass the 1M-record cap.")
    parser.add_argument(
        "--max-records",
        type=int,
        default=HARD_CAP,
        help=f"Refuse to export more records than this (default {HARD_CAP:,}).",
    )
    parser.add_argument("--repo", type=Path, default=None, help="Git repo for AuthorIndex.")
    parser.add_argument("--no-author-index", action="store_true")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"ulog export-html: input not found: {args.input}", file=sys.stderr)
        return 2

    include = (
        frozenset(s.strip() for s in args.include.split(",") if s.strip())
        if args.include
        else DEFAULT_INCLUDE
    )
    unknown = include - frozenset(SECTIONS)
    if unknown:
        print(
            f"ulog export-html: unknown --include section(s): {sorted(unknown)}",
            file=sys.stderr,
        )
        return 2

    if args.inline_data:
        inline: bool | None = True
    elif args.separate_data:
        inline = False
    else:
        inline = None

    options = ExportOptions(
        output=args.output,
        filter_dsl=args.filter_dsl,
        include=include,
        theme=args.theme,
        inline_data=inline,
        force=args.force,
        force_cap=args.force_cap,
        max_records=args.max_records,
        repo=args.repo,
        no_author_index=args.no_author_index,
    )
    exporter = HtmlExporter(args.input, options)
    try:
        result = exporter.run()
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    print(
        f"ulog export-html: wrote {result.records_written:,} records "
        f"across {result.pages_written:,} pages → {result.output_dir}",
        file=sys.stderr,
    )
    return 0
