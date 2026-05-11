"""Django views for the ULog inspection UI."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from .adapters import Adapter, Filters, get_adapter

# Module-level singleton adapter — built once on first request, reused.
_adapter: Adapter | None = None


def _adapter_or_404() -> Adapter:
    global _adapter
    if _adapter is None:
        path = settings.ULOG_LOGS_PATH
        if not path:
            raise Http404("No log file configured. Run `ulog-web <path>`.")
        _adapter = get_adapter(path)
    return _adapter


def _parse_filters(request: HttpRequest) -> Filters:
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
        # Story 2.6/2.7 (FR76/FR77/FR78) — Authors sidebar multi-select.
        # `?author=foo@x&author=bar@y&show_unknown=0` — OR semantics.
        authors=[a for a in qs.getlist("author") if a],
        show_unknown=qs.get("show_unknown", "1").strip().lower() not in ("0", "false", "off"),
    )


def list_view(request: HttpRequest) -> HttpResponse:
    """Main filter + list view (FR35-FR36)."""
    from dataclasses import replace

    from .adapters import QueryResult
    from .blame import compute_authors_summary, get_global_index

    adapter = _adapter_or_404()
    filters = _parse_filters(request)
    page = max(1, int(request.GET.get("page", "1") or "1"))
    page_size = 100

    idx = get_global_index()

    # Story 2.7 — when an author filter is active (selection or
    # show_unknown=False), we post-filter records in Python because the
    # adapter doesn't know about the index. Cost: O(N) for in-memory
    # adapters; bounded for SQLite (NFR-PERF-31 ≤500ms is the budget).
    author_filter_active = (bool(filters.authors) or not filters.show_unknown) and idx is not None

    if author_filter_active:
        assert idx is not None  # narrowed by author_filter_active above
        full = adapter.query(filters, page=1, page_size=10_000_000)
        selected = set(filters.authors)
        # `Show unknown` is the master gate for null-author rows. When it's
        # off, the `<unknown>` author checkbox in the sidebar is irrelevant —
        # nullify it here so the row below doesn't reintroduce the records
        # the user just asked to hide. (The UI also auto-unchecks the
        # `<unknown>` row when Show-unknown flips off, but this backend
        # guard means a stale URL or a JS-disabled browser still behaves.)
        unknown_ticked = "<unknown>" in selected and filters.show_unknown
        kept = []
        for r in full.records:
            a = idx.author_for(r.file, r.line)
            if selected:
                if (a is not None and a.email in selected) or (a is None and unknown_ticked):
                    kept.append(r)
            else:
                # No specific authors selected — show_unknown is the only filter.
                if a is None and not filters.show_unknown:
                    continue
                kept.append(r)
        total = len(kept)
        start = (page - 1) * page_size
        result = QueryResult(
            records=kept[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
            sector_counts=full.sector_counts,
            file_counts=full.file_counts,
            level_counts=full.level_counts,
            bound_keys=full.bound_keys,
            test_summary=full.test_summary,
        )
    else:
        result = adapter.query(filters, page=page, page_size=page_size)

    # Story 2.6 — Authors sidebar with ghost counts.
    # Ghost-count rule (v0.2.1, FR79): the count next to each author is
    # what would be added if you toggled THAT author. Compute against
    # filters MINUS the author axis itself.
    authors_summary = None
    record_authors: dict[int, object] = {}
    if idx is not None:
        # ghost_filters is conceptually filters minus the author axis;
        # compute_authors_summary walks the adapter ignoring author state.
        ghost_filters = replace(filters, authors=[])  # noqa: F841
        authors_summary = compute_authors_summary(adapter, idx)
        # Per-row author resolution for the new "Author" column. Cache
        # hit rate is high because compute_authors_summary above has
        # already warmed every (file, line) pair the records reference.
        for r in result.records:
            record_authors[r.id] = idx.author_for(r.file, r.line)

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
    qs_minus_test_id = f"&{qs_minus_test_id_encoded}" if qs_minus_test_id_encoded else ""

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
        # Story 2.6 (FR76/FR79) — author sidebar data; None when indexer
        # is disabled or no .git/ — template hides the block in that case.
        "authors_summary": authors_summary,
        # Per-row author for the records-table "Author" column. Empty
        # dict when no idx (the column then renders as "—").
        "record_authors": record_authors,
        # Story 1.7 — query-string fragment carrying every CURRENT filter
        # except test_id and page; consumed by the sidebar's click-to-filter
        # anchor so non-test_id filters survive the click.
        "qs_minus_test_id": qs_minus_test_id,
        "qs": request.GET.urlencode(),
    }
    return render(request, "ulog/list.html", ctx)


def detail_view(request: HttpRequest, record_id: int) -> HttpResponse:
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

    # Story 2.8 (FR80) — author panel below Context. None when no idx
    # is active or the (file, line) doesn't resolve.
    from .blame import get_global_index

    idx = get_global_index()
    author = idx.author_for(record.file, record.line) if idx else None
    author_relative_date = _relative_date(author.ts) if author else ""

    return render(
        request,
        "ulog/detail.html",
        {
            "record": record,
            "logs_path": settings.ULOG_LOGS_PATH,
            "test_id": test_id,
            "test_summary_row": test_summary_row,
            "test_record_count": test_record_count,
            # Story 2.8 — Authored by panel data; None when unavailable.
            "author": author,
            "author_short_sha": author.sha[:7] if author else "",
            "author_relative_date": author_relative_date,
        },
    )


_SHA_RE = __import__("re").compile(r"^[0-9a-f]{4,40}$", __import__("re").IGNORECASE)


def _validate_sha(sha: str) -> bool:
    """NFR-SEC-30 — first-line defense against shell injection via the
    URL path. The Django route already restricts to <str:sha>, but we
    enforce hex-only and length 4-40 so no shell metacharacter can ever
    reach a subprocess argv list."""
    return bool(_SHA_RE.match(sha))


def qa_view(request: HttpRequest) -> HttpResponse:
    """Debug-only QA checklist page (Epic 1 + Epic 2 + perf v0.4.1).

    404 unless `settings.DEBUG` is True (i.e. user launched the viewer
    with `ulog-web --debug`). All state is client-side (localStorage)
    — no server persistence, no DB writes. The page is a dev-time tool.
    """
    if not getattr(settings, "DEBUG", False):
        raise Http404("debug-only page; relaunch with `ulog-web --debug`")
    # Load EN+FR strings for the JS-side i18n switcher.
    strings_path = Path(__file__).resolve().parent.parent / "qa_strings.json"
    try:
        qa_strings = json.loads(strings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        qa_strings = {"en": {}, "fr": {}}
    return render(
        request,
        "ulog/qa.html",
        {
            "logs_path": settings.ULOG_LOGS_PATH,
            "qa_strings_json": qa_strings,
        },
    )


def diff_view(request: HttpRequest, sha: str) -> HttpResponse:
    """Story 2.9 (FR81 / NFR-SEC-30) — render `git show <sha>` safely."""
    import subprocess

    from django.http import HttpResponse, HttpResponseBadRequest

    if not _validate_sha(sha):
        return HttpResponseBadRequest(
            f"invalid sha {sha!r}: must match [0-9a-f]{{4,40}}",
        )

    repo = os.environ.get("ULOG_AUTHOR_REPO")
    if not repo:
        return HttpResponse(
            "no --repo configured; cannot resolve diffs. "
            "Restart ulog-web with --repo PATH or auto-detect from a git tree.",
            status=503,
            content_type="text/plain",
        )

    # Step 1: rev-parse --verify confirms the commit is reachable.
    try:
        rp = subprocess.run(
            ["git", "rev-parse", "--verify", f"{sha}^{{commit}}"],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return HttpResponse(
            f"git invocation failed: {e}",
            status=503,
            content_type="text/plain",
        )
    if rp.returncode != 0:
        return HttpResponse(
            f"sha {sha} not reachable in {repo}",
            status=404,
            content_type="text/plain",
        )

    # Step 2: git show — sha is now validated AND reachable.
    show = subprocess.run(
        ["git", "show", "--patch", "--no-color", sha],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if show.returncode != 0:
        return HttpResponse(
            f"git show failed: {show.stderr}",
            status=500,
            content_type="text/plain",
        )

    return render(
        request,
        "ulog/diff.html",
        {
            "sha": sha,
            "short_sha": sha[:7],
            "diff_text": show.stdout,
        },
    )


def _relative_date(ts: int) -> str:
    """Format a unix timestamp as a relative-date string (e.g. '6 days ago').

    Story 2.8 (FR80). Stdlib only — no humanize/arrow dep (NFR-DEP-50).
    """
    import time as _time

    delta = int(_time.time()) - int(ts)
    if delta < 0:
        return "in the future"
    if delta < 60:
        return "just now"
    if delta < 3600:
        m = delta // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if delta < 86400:
        h = delta // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if delta < 86400 * 30:
        d = delta // 86400
        return f"{d} day{'s' if d != 1 else ''} ago"
    if delta < 86400 * 365:
        mo = delta // (86400 * 30)
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = delta // (86400 * 365)
    return f"{y} year{'s' if y != 1 else ''} ago"


def api_records(request: HttpRequest) -> HttpResponse:
    """JSON endpoint for the JS-driven filter UI (FR34)."""
    adapter = _adapter_or_404()
    filters = _parse_filters(request)
    page = max(1, int(request.GET.get("page", "1") or "1"))
    result = adapter.query(filters, page=page, page_size=100)

    from dataclasses import asdict

    return JsonResponse(
        {
            "records": [
                {
                    "id": r.id,
                    "ts": r.ts,
                    "level": r.level,
                    "logger": r.logger,
                    "msg": r.msg,
                    "file": r.file,
                    "line": r.line,
                    "context": r.context,
                    "exc": r.exc,
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
        }
    )


# ---- Built-in /docs (FR40) ----------------------------------------------


_DOC_PAGES: dict[str, str] = {
    "quickstart": "Quickstart",
    "storage": "Storage handlers (SQL / JSON / CSV)",
    "api": "Python API reference",
    "troubleshooting": "Troubleshooting",
    "sectors-and-files": "Sectors and files explained",
    "test-integration": "Test integration",  # Story 1.11 — v0.3
    "author-filter": "Author filter",  # Story 2.11 — v0.4
}


def docs_index(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "ulog/docs_index.html",
        {"pages": _DOC_PAGES, "logs_path": settings.ULOG_LOGS_PATH},
    )


def docs_page(request: HttpRequest, page: str) -> HttpResponse:
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

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    def flush_code() -> None:
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
            out.append(
                f'<h1 class="text-3xl font-bold mt-4 mb-2">{_html_escape(stripped[2:])}</h1>'
            )
        elif stripped.startswith("## "):
            close_list()
            out.append(
                f'<h2 class="text-2xl font-semibold mt-4 mb-2">{_html_escape(stripped[3:])}</h2>'
            )
        elif stripped.startswith("### "):
            close_list()
            out.append(
                f'<h3 class="text-xl font-semibold mt-3 mb-1">{_html_escape(stripped[4:])}</h3>'
            )
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
    text = re.sub(
        r"`([^`]+)`", r'<code class="bg-slate-100 dark:bg-slate-800 px-1 rounded">\1</code>', text
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a class="text-blue-600 dark:text-blue-400 underline" href="\2">\1</a>',
        text,
    )
    return text


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
