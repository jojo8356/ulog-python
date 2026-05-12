"""Tests for `ulog.correlate` — Story 4.5."""

from __future__ import annotations

import contextlib
import logging
import math
import time
from pathlib import Path

import pytest

import ulog


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


def _seed_db(tmp_path: Path, profile: dict[str, int]) -> Path:
    """Seed a DB with records of varying level/logger + context tenant.

    profile dict: {(level, logger, tenant): count}
    """
    from sqlalchemy import create_engine, text

    db = tmp_path / "corr.sqlite"
    url = f"sqlite:///{db}"
    # Use non-chain mode for simpler seeding (raw inserts).
    from ulog.handlers.sql import SQLHandler

    h = SQLHandler(url=url, batch_size=1)
    h._ensure_schema()
    h.close()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        for (level, logger_name, tenant), n in profile.items():
            for i in range(n):
                conn.execute(
                    text(
                        "INSERT INTO logs "
                        "(ts, level, logger, msg, file, line, context) VALUES "
                        "('2026-05-12','" + level + "','" + logger_name + "',"
                        "'m" + str(i) + "', 'f.py', 1, "
                        "json_object('tenant', :tenant))"
                    ),
                    {"tenant": tenant},
                )
    engine.dispose()
    return db


# ---- happy path ---------------------------------------------------------


def test_correlate_returns_top_over_sorted_by_lift_desc(tmp_path):
    """Filter level=ERROR; tenant=A appears in 100% of ERRORs and 0% of
    non-ERRORs → infinite lift at the top."""
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "svc", "A"): 10,
            ("ERROR", "svc", "B"): 10,
            ("INFO", "svc", "B"): 30,
            ("INFO", "svc", "C"): 40,
        },
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    assert report.filter_count == 20
    assert report.baseline_count == 70
    # tenant=A is uniquely in the ERROR group → infinite lift (or top).
    tenants_top = [r for r in report.top_over if r.tag == "context.tenant" and r.value == "A"]
    assert tenants_top, report.top_over
    # The lift values are non-increasing.
    lifts = [r.lift for r in report.top_over]
    assert lifts == sorted(lifts, reverse=True)


def test_correlate_returns_bottom_under_sorted_by_lift_asc(tmp_path):
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "svc", "A"): 10,
            ("INFO", "svc", "A"): 10,
            ("INFO", "svc", "B"): 90,
        },
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    lifts = [r.lift for r in report.bottom_under]
    assert lifts == sorted(lifts)


def test_correlate_self_tautology_excluded(tmp_path):
    """Filter `level=ERROR` → the `tag=level, value=ERROR` row must NOT
    appear in the report (uninformative)."""
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "svc", "A"): 10,
            ("INFO", "svc", "B"): 30,
        },
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    for r in (*report.top_over, *report.bottom_under):
        assert not (r.tag == "level" and r.value == "ERROR"), report


def test_correlate_with_where_dsl_filter(tmp_path):
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "auth", "A"): 5,
            ("ERROR", "svc", "B"): 15,
            ("INFO", "auth", "A"): 80,
        },
    )
    report = ulog.correlate(db, where_dsl="level=ERROR AND logger=auth")
    assert report.filter_count == 5
    assert report.baseline_count == 95


def test_correlate_returns_in_filter_and_in_baseline_counts(tmp_path):
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "svc", "A"): 10,
            ("INFO", "svc", "A"): 90,
        },
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    tenant_a = next(r for r in report.top_over if r.tag == "context.tenant" and r.value == "A")
    assert tenant_a.in_filter == 10
    assert tenant_a.in_baseline == 90


def test_correlate_unique_in_filter_yields_infinite_lift(tmp_path):
    """tenant=A only in the filter group → lift should be +inf."""
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "svc", "A"): 10,
            ("INFO", "svc", "B"): 30,
        },
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    tenant_a = next(r for r in report.top_over if r.tag == "context.tenant" and r.value == "A")
    assert math.isinf(tenant_a.lift)


def test_correlate_on_empty_filter_returns_empty_report(tmp_path):
    """Filter matches 0 records → empty top_over + bottom_under."""
    db = _seed_db(tmp_path, {("INFO", "svc", "A"): 5})
    report = ulog.correlate(db, where_dsl="level=ERROR")
    assert report.filter_count == 0
    assert report.top_over == ()
    assert report.bottom_under == ()


def test_correlate_context_keys_surface_as_dotted_tags(tmp_path):
    db = _seed_db(
        tmp_path,
        {("ERROR", "svc", "A"): 5, ("INFO", "svc", "B"): 5},
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    tags = {r.tag for r in (*report.top_over, *report.bottom_under)}
    assert "context.tenant" in tags


def test_correlate_no_sql_injection_via_dsl_value(tmp_path):
    """A value like `' OR '1'='1` is just a bind param, not SQL."""
    db = _seed_db(
        tmp_path,
        {("ERROR", "svc", "A"): 5, ("INFO", "svc", "B"): 5},
    )
    # The DSL filter compiles to a bind param. Even with a weird value,
    # no SQL syntax error; result is a no-match (filter_count = 0).
    report = ulog.correlate(db, where_dsl="msg=\"' OR '1'='1\"")
    assert report.filter_count == 0


def test_correlate_wall_time_under_budget_on_1k_records(tmp_path):
    """Scaled smoke for NFR-PERF-53 (full target: 1M ≤ 500ms).
    1K records ≤ 250 ms on dev laptop = safe budget proxy."""
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "svc", "A"): 100,
            ("INFO", "svc", "A"): 400,
            ("INFO", "svc", "B"): 500,
        },
    )
    t0 = time.perf_counter()
    report = ulog.correlate(db, where_dsl="level=ERROR")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert report.filter_count == 100
    assert elapsed_ms < 250, f"correlate too slow: {elapsed_ms:.1f}ms on 1K records"


# ---- mutex + arg validation ---------------------------------------------


def test_correlate_no_filter_arg_raises(tmp_path):
    db = _seed_db(tmp_path, {("INFO", "svc", "A"): 5})
    with pytest.raises(ValueError, match="exactly one"):
        ulog.correlate(db)


def test_correlate_both_filter_args_raises(tmp_path):
    db = _seed_db(tmp_path, {("INFO", "svc", "A"): 5})
    with pytest.raises(ValueError, match="exactly one"):
        ulog.correlate(db, where="level='ERROR'", where_dsl="level=ERROR")


def test_correlate_db_not_found_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="DB not found"):
        ulog.correlate(tmp_path / "missing.sqlite", where_dsl="level=ERROR")


# ---- Story 4.6 — small-sample warnings + axis-skip ----------------------


def test_small_sample_warning_when_in_filter_under_30(tmp_path):
    """tenant=A has in_filter < 30 → row gets warning='small_sample'."""
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "svc", "A"): 5,  # under 30 in the filter group
            ("INFO", "svc", "A"): 50,
            ("INFO", "svc", "B"): 100,
        },
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    tenant_a = next(r for r in report.top_over if r.tag == "context.tenant" and r.value == "A")
    assert tenant_a.warning == "small_sample"


def test_no_warning_when_in_filter_30_or_more(tmp_path):
    db = _seed_db(
        tmp_path,
        {
            ("ERROR", "svc", "A"): 50,  # >= 30
            ("INFO", "svc", "A"): 100,
            ("INFO", "svc", "B"): 100,
        },
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    tenant_a = next(r for r in report.top_over if r.tag == "context.tenant" and r.value == "A")
    assert tenant_a.warning is None


def test_axis_row_gets_axis_warning_and_excluded_from_top(tmp_path):
    """`level=ERROR` filter → row `tag=level, value=ERROR` excluded from
    top_over / bottom_under (it's the axis)."""
    db = _seed_db(
        tmp_path,
        {("ERROR", "svc", "A"): 50, ("INFO", "svc", "B"): 50},
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    for r in (*report.top_over, *report.bottom_under):
        assert not (r.tag == "level" and r.value == "ERROR")


def test_axis_row_exposed_in_axis_rows_tuple(tmp_path):
    db = _seed_db(
        tmp_path,
        {("ERROR", "svc", "A"): 50, ("INFO", "svc", "B"): 50},
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    axis = [r for r in report.axis_rows if r.tag == "level" and r.value == "ERROR"]
    assert axis
    assert axis[0].warning == "axis"


def test_axis_warning_wins_over_small_sample(tmp_path):
    """A row that is both axis AND has in_filter<30 → warning='axis'
    (axis is more actionable info to surface)."""
    db = _seed_db(
        tmp_path,
        {("ERROR", "svc", "A"): 5, ("INFO", "svc", "B"): 100},
    )
    report = ulog.correlate(db, where_dsl="level=ERROR")
    level_error = [r for r in report.axis_rows if r.tag == "level" and r.value == "ERROR"]
    assert level_error
    assert level_error[0].warning == "axis"  # not "small_sample"
