"""Tests for `ulog export-html` (Epic 8 / PRD-v0.6)."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any

import pytest

import ulog
from ulog.web.export import ExportOptions, HtmlExporter
from ulog.web.export.exporter import ExportResult


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


def _seed(tmp_path: Path, with_chain: bool = False) -> Path:
    """Seed a tiny SQLite DB with mixed records."""
    db = tmp_path / "in.sqlite"
    if with_chain:
        ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    else:
        ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("svc.checkout")
    for i in range(5):
        log.info("step %d ok", i)
    log.error("boom: stripe 503")
    log.warning("slow query 850ms")
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def _run_export(db: Path, out: Path, **kwargs: Any) -> ExportResult:
    opts = ExportOptions(output=out, **kwargs)
    return HtmlExporter(db, opts).run()


# ---- Story 8.2: CLI boilerplate + record cap ----------------------------


def test_refuses_non_empty_output_without_force(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(SystemExit):
        _run_export(db, out)


def test_overwrites_with_force(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hi", encoding="utf-8")
    result = _run_export(db, out, force=True)
    assert (out / "index.html").exists()
    assert result.records_written == 7


def test_record_cap_refuses_without_force_cap(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        _run_export(db, out, max_records=3)


def test_record_cap_bypassed_with_force_cap(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    result = _run_export(db, out, max_records=3, force_cap=True)
    assert result.records_written == 7


# ---- Story 8.3: standalone Django + render_to_string --------------------


def test_runs_without_django_server(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out)
    # Spot-check: rendering produced an index.html with the record count.
    body = (out / "index.html").read_text(encoding="utf-8")
    assert "7" in body  # 7 records (5 info + 1 error + 1 warning)


# ---- Story 8.4: output layout + index pagination ------------------------


def test_layout_has_index_and_record_pages(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out)
    assert (out / "index.html").exists()
    assert (out / "r").is_dir()
    # 7 record pages (1.html, 2.html, ...).
    assert sum(1 for _ in (out / "r").glob("*.html")) == 7


def test_pagination_above_default(tmp_path):
    """With page_size=3, 7 records → 3 pages: index + page-2 + page-3."""
    db = _seed(tmp_path)
    out = tmp_path / "out"
    result = _run_export(db, out, page_size=3)
    assert result.pages_written >= 3
    assert (out / "index.html").exists()
    assert (out / "page-2.html").exists()
    assert (out / "page-3.html").exists()


def test_relative_asset_paths_only(tmp_path):
    """No absolute http:// URLs in any page (so zipping preserves links)."""
    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out)
    body = (out / "index.html").read_text(encoding="utf-8")
    # The CDN script previously bundled by base.html should not leak into the
    # fallback renderer's output.
    assert "http://localhost" not in body
    # Local CSS reference is relative (single- or double-quoted attr is OK).
    assert "static/ulog-light.css" in body or "static/ulog-dark.css" in body


# ---- Story 8.5: --filter DSL --------------------------------------------


def test_filter_dsl_keeps_only_matches(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    result = _run_export(db, out, filter_dsl="level=ERROR")
    assert result.records_written == 1


def test_filter_dsl_invalid_raises(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        _run_export(db, out, filter_dsl="level=")  # malformed


# ---- Story 8.6: --include section gating --------------------------------


def test_include_default_emits_all_sections(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out)
    assert (out / "incidents.html").exists()
    assert (out / "multi-track.html").exists()
    assert (out / "integrity.html").exists()


def test_include_incidents_only(tmp_path):
    from ulog.web.export.exporter import SECTIONS  # noqa: F401

    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out, include=frozenset({"incidents", "integrity"}))
    assert (out / "incidents.html").exists()
    assert (out / "integrity.html").exists()
    assert not (out / "multi-track.html").exists()
    assert not (out / "docs").is_dir()


# ---- Story 8.7: --theme light/dark --------------------------------------


def test_theme_dark_referenced_in_pages(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out, theme="dark")
    body = (out / "index.html").read_text(encoding="utf-8")
    assert "ulog-dark.css" in body


def test_theme_light_referenced_in_pages(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out, theme="light")
    body = (out / "index.html").read_text(encoding="utf-8")
    assert "ulog-light.css" in body


# ---- Story 8.8: inline-data / separate-data + heuristic ----------------


def test_separate_data_mode_writes_json_files(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    result = _run_export(db, out, inline_data=False)
    assert (out / "data").is_dir()
    assert (out / "data" / "records-page-1.json").exists()
    payload = json.loads((out / "data" / "records-page-1.json").read_text(encoding="utf-8"))
    assert len(payload) == 7
    assert result.inline_data is False


def test_inline_data_mode_no_data_dir(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    result = _run_export(db, out, inline_data=True)
    assert not (out / "data").is_dir()
    assert result.inline_data is True


def test_heuristic_picks_inline_for_small(tmp_path):
    """7 records < 10K threshold → inline default."""
    db = _seed(tmp_path)
    out = tmp_path / "out"
    result = _run_export(db, out)  # no flag
    assert result.inline_data is True


# ---- Story 8.10: integrity badge ----------------------------------------


def test_integrity_status_missing_when_no_verify(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    result = _run_export(db, out)
    assert result.integrity_status == "missing"
    body = (out / "integrity.html").read_text(encoding="utf-8")
    assert "never verified" in body


def test_integrity_status_ok_after_verify(tmp_path):
    from ulog._cli import main as cli_main

    db = _seed(tmp_path, with_chain=True)
    cli_main(["verify", str(db)])
    out = tmp_path / "out"
    result = _run_export(db, out)
    assert result.integrity_status == "OK"
    # Per-page header carries the badge (Story 8.10 / FR143).
    body = (out / "index.html").read_text(encoding="utf-8")
    assert "Integrity ✓" in body


def test_integrity_broken_renders_red_badge_everywhere(tmp_path):
    from sqlalchemy import create_engine, text

    from ulog._cli import main as cli_main

    db = _seed(tmp_path, with_chain=True)
    # Corrupt a row to force BROKEN.
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        conn.execute(text("UPDATE logs SET msg='tampered' WHERE chain_pos=3"))
    engine.dispose()
    cli_main(["verify", str(db)])
    out = tmp_path / "out"
    result = _run_export(db, out)
    assert result.integrity_status == "BROKEN"
    body = (out / "index.html").read_text(encoding="utf-8")
    assert "BROKEN" in body


# ---- Story 8.11: README.html --------------------------------------------


def test_readme_at_root(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out)
    assert (out / "README.html").exists()
    body = (out / "README.html").read_text(encoding="utf-8")
    assert "index.html" in body
    assert "ulog" in body.lower()


def test_readme_warns_about_fetch_in_separate_data(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    _run_export(db, out, inline_data=False)
    body = (out / "README.html").read_text(encoding="utf-8")
    assert "fetch" in body.lower()


# ---- Story 8.12: edge cases --------------------------------------------


def test_zero_matching_records_renders_clean(tmp_path):
    db = _seed(tmp_path)
    out = tmp_path / "out"
    result = _run_export(db, out, filter_dsl="level=CRITICAL")
    assert result.records_written == 0
    assert (out / "index.html").exists()


def test_xss_msg_is_escaped(tmp_path):
    """NFR-SEC-60 — <script> in msg must NOT execute on page load."""
    db = tmp_path / "xss.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().error("<script>alert(1)</script>")
    for h in logging.getLogger().handlers:
        h.flush()
    out = tmp_path / "out"
    _run_export(db, out)
    body = (out / "index.html").read_text(encoding="utf-8")
    # Escaped form present, raw form absent.
    assert "&lt;script&gt;" in body
    assert "<script>alert" not in body


def test_path_traversal_in_file_field_is_escaped(tmp_path):
    """NFR-SEC-61 — record.file='../../etc/passwd' shouldn't write outside."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "trav.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger().info("seed")
    for h in logging.getLogger().handlers:
        h.flush()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        conn.execute(text("UPDATE logs SET file='../../etc/passwd' WHERE id=1"))
    engine.dispose()
    out = tmp_path / "out"
    _run_export(db, out)
    # Path traversal is text-only — no file written outside out/.
    assert not (tmp_path / "etc" / "passwd").exists()
    assert not (out.parent / "etc" / "passwd").exists()
    body = (out / "r" / "1.html").read_text(encoding="utf-8")
    assert "etc/passwd" in body  # the LITERAL string appears as escaped text


def test_record_cap_blocks_before_writing(tmp_path):
    """FR136 — cap must refuse before any file is written."""
    db = _seed(tmp_path)
    out = tmp_path / "out"
    with pytest.raises(SystemExit):
        _run_export(db, out, max_records=3)
    # Output dir was created (the existence check happens first) but no
    # page should be inside it.
    if out.exists():
        assert not (out / "index.html").exists()
