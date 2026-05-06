"""Django views for the ULog inspection UI."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render

from .adapters import Filters, get_adapter

# Module-level singleton adapter — built once on first request, reused.
_adapter = None


def _adapter_or_404():
    global _adapter
    if _adapter is None:
        path = settings.ULOG_LOGS_PATH
        if not path:
            raise Http404("No log file configured. Run `ulog-web <path>`.")
        _adapter = get_adapter(path)
    return _adapter


def _parse_filters(request) -> Filters:
    """Decode the query string into a Filters object."""
    qs = request.GET
    levels = [lv for lv in qs.getlist("level") if lv]
    loggers = [lg for lg in qs.getlist("logger") if lg]
    files = [f for f in qs.getlist("file") if f]
    bound: dict[str, str] = {}
    for raw in qs.getlist("bound"):
        if "=" in raw:
            k, _, v = raw.partition("=")
            k = k.strip()
            v = v.strip()
            if k and v:
                bound[k] = v
    return Filters(
        levels=levels,
        loggers=loggers,
        files=files,
        search=qs.get("q", "").strip(),
        bound=bound,
        ts_from=qs.get("from", "").strip(),
        ts_to=qs.get("to", "").strip(),
        # Story 1.6 (FR63 / FR64) — checkbox quick filters from the Tests sidebar.
        # Accept "1" / "true" / "on" (HTML form-checkbox conventions) as truthy.
        failed_only=qs.get("failed_only", "").strip().lower() in ("1", "true", "on"),
        slowest_only=qs.get("slowest_only", "").strip().lower() in ("1", "true", "on"),
        # Story 1.7 (FR65) — click-to-filter test_id from the TESTS sidebar.
        test_id=qs.get("test_id", "").strip(),
    )


def list_view(request):
    """Main filter + list view (FR35-FR36)."""
    adapter = _adapter_or_404()
    filters = _parse_filters(request)
    page = max(1, int(request.GET.get("page", "1") or "1"))
    result = adapter.query(filters, page=page, page_size=100)

    # Build a flat sorted sector list for the template
    sectors = sorted(result.sector_counts.items(), key=lambda kv: kv[0])
    files = sorted(result.file_counts.items(), key=lambda kv: -kv[1])
    levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    level_summary = [(lv, result.level_counts.get(lv, 0)) for lv in levels]

    total_pages = max(1, (result.total + result.page_size - 1) // result.page_size)

    # Story 1.7 — build a query-string fragment EXCLUDING `test_id` and `page`
    # so clicking a test in the TESTS sidebar (a) replaces the active test
    # rather than stacking, and (b) doesn't preserve a stale `page=N` value
    # that would land the user on an empty page of the (typically smaller)
    # filtered set.
    qs_dict = request.GET.copy()
    qs_dict.pop("test_id", None)
    qs_dict.pop("page", None)
    qs_minus_test_id_encoded = qs_dict.urlencode()
    qs_minus_test_id = (
        f"&{qs_minus_test_id_encoded}" if qs_minus_test_id_encoded else ""
    )

    ctx = {
        "logs_path": settings.ULOG_LOGS_PATH,
        "filters": filters,
        "records": result.records,
        "total": result.total,
        "page": result.page,
        "total_pages": total_pages,
        "sectors": sectors,
        "files": files,
        "level_summary": level_summary,
        "bound_keys": result.bound_keys,
        # Story 1.6 — TESTS sidebar: list of TestSummaryRow, empty if no
        # `ulog.test` records exist (template renders nothing in that case).
        "test_summary": result.test_summary,
        # Story 1.7 — query-string fragment carrying every CURRENT filter
        # except test_id and page; consumed by the sidebar's click-to-filter
        # anchor so non-test_id filters survive the click.
        "qs_minus_test_id": qs_minus_test_id,
        "qs": request.GET.urlencode(),
    }
    return render(request, "ulog/list.html", ctx)


def detail_view(request, record_id: int):
    """Full record detail page (FR37) + Story 1.8 Test context panel (FR66)."""
    adapter = _adapter_or_404()
    record = adapter.get(record_id)
    if record is None:
        raise Http404(f"record {record_id} not found")

    # Story 1.8 — if this record carries test_id, look up the matching
    # TestSummaryRow + total record count for the panel. None / 0 when no
    # test_id; template hides the panel block in that case.
    # `record.context` always exists as a dict (default_factory=dict on the
    # Record dataclass) — direct .get() call without None guard (review patch P2).
    test_id = record.context.get("test_id")
    test_summary_row = None
    test_record_count = 0
    if test_id:
        test_summary_row = adapter.get_test_summary_row(test_id)
        test_record_count = adapter.count_records_for_test_id(test_id)

    return render(
        request,
        "ulog/detail.html",
        {
            "record": record,
            "logs_path": settings.ULOG_LOGS_PATH,
            "test_id": test_id,
            "test_summary_row": test_summary_row,
            "test_record_count": test_record_count,
        },
    )


def api_records(request):
    """JSON endpoint for the JS-driven filter UI (FR34)."""
    adapter = _adapter_or_404()
    filters = _parse_filters(request)
    page = max(1, int(request.GET.get("page", "1") or "1"))
    result = adapter.query(filters, page=page, page_size=100)

    from dataclasses import asdict
    return JsonResponse({
        "records": [
            {
                "id": r.id, "ts": r.ts, "level": r.level, "logger": r.logger,
                "msg": r.msg, "file": r.file, "line": r.line,
                "context": r.context, "exc": r.exc,
            }
            for r in result.records
        ],
        "total": result.total,
        "page": result.page,
        "level_counts": result.level_counts,
        "file_counts": result.file_counts,
        "sector_counts": result.sector_counts,
        # Story 1.6 — Test sidebar data for the JS-driven UI (FR62).
        # `asdict` works on frozen dataclasses; all TestSummaryRow fields
        # are JSON-serializable primitives.
        "test_summary": [asdict(r) for r in result.test_summary],
    })


# ---- Built-in /docs (FR40) ----------------------------------------------


_DOC_PAGES: dict[str, str] = {
    "quickstart": "Quickstart",
    "storage": "Storage handlers (SQL / JSON / CSV)",
    "api": "Python API reference",
    "troubleshooting": "Troubleshooting",
    "sectors-and-files": "Sectors and files explained",
    "test-integration": "Test integration",  # Story 1.11 — v0.3
}


def docs_index(request):
    return render(
        request,
        "ulog/docs_index.html",
        {"pages": _DOC_PAGES, "logs_path": settings.ULOG_LOGS_PATH},
    )


def docs_page(request, page: str):
    if page not in _DOC_PAGES:
        raise Http404(f"unknown doc page {page!r}")
    md_path = settings.ULOG_DOCS_DIR / f"{page}.md"
    if not md_path.exists():
        raise Http404(f"doc file missing: {md_path}")
    raw = md_path.read_text(encoding="utf-8")
    html = _markdown_to_html(raw)
    return render(
        request,
        "ulog/docs_page.html",
        {
            "title": _DOC_PAGES[page],
            "page": page,
            "content_html": html,
            "all_pages": _DOC_PAGES,
            "logs_path": settings.ULOG_LOGS_PATH,
        },
    )


def _markdown_to_html(md: str) -> str:
    """Tiny markdown → HTML for docs (no external markdown lib).

    Supports: # headings, ## sub-headings, ```code blocks```, inline
    `code`, lists, paragraphs. That's enough for v0.2 doc pages.
    A future v0.3 could swap in `markdown-it-py` if richer rendering
    is needed.
    """
    out: list[str] = []
    in_code = False
    in_list = False
    code_lang = ""
    code_buf: list[str] = []

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    def flush_code():
        nonlocal in_code, code_buf, code_lang
        if in_code:
            joined = "\n".join(code_buf).rstrip("\n")
            cls = f' class="lang-{code_lang}"' if code_lang else ""
            out.append(
                f'<pre class="bg-slate-100 dark:bg-slate-800 rounded p-3 '
                f'overflow-x-auto text-sm"><code{cls}>{_html_escape(joined)}</code></pre>'
            )
            code_buf = []
            in_code = False
            code_lang = ""

    for line in md.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("```"):
            if in_code:
                flush_code()
            else:
                close_list()
                in_code = True
                code_lang = stripped[3:].strip()
            continue
        if in_code:
            code_buf.append(line)
            continue
        if stripped.startswith("# "):
            close_list()
            out.append(f'<h1 class="text-3xl font-bold mt-4 mb-2">{_html_escape(stripped[2:])}</h1>')
        elif stripped.startswith("## "):
            close_list()
            out.append(f'<h2 class="text-2xl font-semibold mt-4 mb-2">{_html_escape(stripped[3:])}</h2>')
        elif stripped.startswith("### "):
            close_list()
            out.append(f'<h3 class="text-xl font-semibold mt-3 mb-1">{_html_escape(stripped[4:])}</h3>')
        elif stripped.startswith("- "):
            if not in_list:
                out.append('<ul class="list-disc list-inside space-y-1 my-2">')
                in_list = True
            out.append(f"<li>{_inline_md(stripped[2:])}</li>")
        elif stripped == "":
            close_list()
            out.append("")
        else:
            close_list()
            out.append(f'<p class="my-2">{_inline_md(stripped)}</p>')

    flush_code()
    close_list()
    return "\n".join(out)


def _inline_md(text: str) -> str:
    """Inline `code`, **bold**, [link](url) → HTML."""
    text = _html_escape(text)
    text = re.sub(r"`([^`]+)`", r'<code class="bg-slate-100 dark:bg-slate-800 px-1 rounded">\1</code>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a class="text-blue-600 dark:text-blue-400 underline" href="\2">\1</a>',
        text,
    )
    return text


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#39;")
    )
