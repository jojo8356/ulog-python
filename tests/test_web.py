"""Tests for the v0.2 Django inspection UI.

Covers the adapter layer (storage-agnostic shape) + the Django views
(list, detail, docs) via the test client. Each test creates a tiny
SQLite fixture in tmp_path so tests are hermetic.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path

import pytest

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    """Clear bound state at SETUP and teardown.

    Setup-side clear stops the outer pytest plugin's test_id bind
    (active under `--ulog-db`) from polluting records emitted by
    sqlite_fixture and breaking tests that assert on records WITHOUT
    test_id.
    """
    ulog.clear()
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


@pytest.fixture
def sqlite_fixture(_isolate, tmp_path) -> Path:
    """Build a small SQLite fixture covering the filter axes.

    Depends on _isolate so the outer plugin's test_id bind is wiped
    before any record is emitted into the fixture DB.
    """
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    ulog.get_logger("myapp.web").info("user on /home")
    ulog.get_logger("myapp.audio.renderer").info("rendering")
    ulog.get_logger("myapp.audio.renderer").warning("lameenc drift")
    ulog.get_logger("myapp.audio.engine").error("ROM not found")
    ulog.bind(rom_sha="abc123", engine="famitracker")
    ulog.get_logger("myapp.audio.renderer").info("rendered", extra={"frames": 600})
    for h in logging.getLogger().handlers:
        h.flush()
    return db


# ---- Adapter unit tests --------------------------------------------------


def test_sqlite_adapter_total_and_filters(sqlite_fixture):
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    res = ad.query(Filters())
    assert res.total == 5
    # Level filter
    res = ad.query(Filters(levels=["ERROR"]))
    assert res.total == 1
    assert res.records[0].msg == "ROM not found"
    # Sector filter (logger prefix)
    res = ad.query(Filters(loggers=["myapp.audio"]))
    assert res.total == 4
    # File filter
    res = ad.query(Filters(files=[res.records[0].file]))
    assert res.total >= 1
    # Search
    res = ad.query(Filters(search="rendering"))
    assert res.total == 1
    # Bound
    res = ad.query(Filters(bound={"rom_sha": "abc123"}))
    assert res.total == 1


def test_sqlite_adapter_sector_counts(sqlite_fixture):
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    res = ad.query(Filters())
    assert res.sector_counts["myapp"] == 5
    assert res.sector_counts["myapp.audio"] == 4
    assert res.sector_counts["myapp.audio.renderer"] == 3
    assert res.sector_counts["myapp.audio.engine"] == 1
    assert res.sector_counts["myapp.web"] == 1


def test_sqlite_adapter_get_returns_record(sqlite_fixture):
    from ulog.web.viewer.adapters import SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    rec = ad.get(1)
    assert rec is not None
    assert rec.id == 1
    assert ad.get(99999) is None


# ---- v0.2.1 ghost counts -------------------------------------------------


def test_level_counts_unaffected_by_level_filter(sqlite_fixture):
    """v0.2.1 ghost-count: ticking a level filter must NOT zero out
    the other levels' counts. Each level row should show the count
    that filter would yield, regardless of what's currently ticked
    on the level axis."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    # No filter → all 5 records, INFO/WARNING/ERROR all visible
    res_unfiltered = ad.query(Filters())
    assert res_unfiltered.level_counts.get("INFO", 0) == 3
    assert res_unfiltered.level_counts.get("WARNING", 0) == 1
    assert res_unfiltered.level_counts.get("ERROR", 0) == 1

    # Tick INFO only → records list shrinks to 3, but level_counts
    # for WARNING / ERROR must STILL show 1 each (ghost count).
    res_info = ad.query(Filters(levels=["INFO"]))
    assert res_info.total == 3
    assert res_info.level_counts.get("INFO", 0) == 3
    assert res_info.level_counts.get("WARNING", 0) == 1, (
        "WARNING count collapsed under self-axis filter — ghost-count "
        "behavior broken (PRD-v0.2.1 regression)"
    )
    assert res_info.level_counts.get("ERROR", 0) == 1


def test_sector_counts_unaffected_by_sector_filter(sqlite_fixture):
    """v0.2.1 ghost-count: same shape for the sector axis. Ticking a
    sector must keep the other sectors' counts visible."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    # Unfiltered baseline counts
    res_unfiltered = ad.query(Filters())
    assert res_unfiltered.sector_counts.get("myapp.audio.engine") == 1
    assert res_unfiltered.sector_counts.get("myapp.web") == 1

    # Tick myapp.audio.engine → records list shrinks to 1, but sector
    # counts for myapp.web must STILL show 1 (ghost count).
    res_engine = ad.query(Filters(loggers=["myapp.audio.engine"]))
    assert res_engine.total == 1
    assert res_engine.sector_counts.get("myapp.audio.engine") == 1
    assert res_engine.sector_counts.get("myapp.web") == 1, (
        "myapp.web sector count collapsed when myapp.audio.engine is "
        "filter-selected — ghost-count behavior broken"
    )


def test_file_counts_unaffected_by_file_filter(sqlite_fixture):
    """v0.2.1 ghost-count: same shape for the file axis."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    res_unfiltered = ad.query(Filters())
    files_in_data = list(res_unfiltered.file_counts.keys())
    assert len(files_in_data) >= 1
    # Tick one file → other files' counts must persist
    one_file = files_in_data[0]
    res_filtered = ad.query(Filters(files=[one_file]))
    assert res_filtered.file_counts == res_unfiltered.file_counts, (
        "Per-file counts changed when a file filter was applied — "
        "ghost-count behavior broken on the file axis"
    )


def test_jsonl_adapter_ghost_counts(tmp_path):
    """Same ghost-count contract for the in-memory JSONL adapter."""
    from ulog.web.viewer.adapters import Filters, JSONLAdapter

    path = tmp_path / "logs.jsonl"
    ulog.setup(handlers=["json"], json_path=str(path))
    ulog.get_logger("a").info("one")
    ulog.get_logger("a").error("two")
    ulog.get_logger("b").info("three")
    for h in logging.getLogger().handlers:
        h.flush()

    ad = JSONLAdapter(path)
    res = ad.query(Filters(levels=["INFO"]))
    assert res.total == 2  # 2 INFO records
    assert res.level_counts.get("INFO") == 2
    # Ghost: ERROR row must still show its count (1)
    assert res.level_counts.get("ERROR") == 1, "JSONL adapter ghost-count broken on the level axis"


def test_jsonl_adapter_round_trip(tmp_path):
    """Build a JSONL via JSONLineHandler then read it back."""
    from ulog.web.viewer.adapters import Filters, JSONLAdapter

    path = tmp_path / "logs.jsonl"
    ulog.setup(handlers=["json"], json_path=str(path))
    ulog.get_logger("svc").info("hi")
    ulog.get_logger("svc").error("bye")
    for h in logging.getLogger().handlers:
        h.flush()

    ad = JSONLAdapter(path)
    res = ad.query(Filters())
    assert res.total == 2
    assert res.records[0].level in {"INFO", "ERROR"}
    res = ad.query(Filters(levels=["ERROR"]))
    assert res.total == 1
    assert res.records[0].msg == "bye"


def test_csv_adapter_round_trip(tmp_path):
    from ulog.web.viewer.adapters import CSVAdapter, Filters

    path = tmp_path / "logs.csv"
    ulog.setup(handlers=["csv"], csv_path=str(path))
    ulog.get_logger("svc").info("hi")
    ulog.get_logger("svc").error("bye")
    for h in logging.getLogger().handlers:
        h.flush()

    ad = CSVAdapter(path)
    res = ad.query(Filters())
    assert res.total == 2
    res = ad.query(Filters(levels=["ERROR"]))
    assert res.total == 1


def test_detect_kind():
    from ulog.web.viewer.adapters import detect_kind

    assert detect_kind(Path("foo.sqlite")) == "sqlite"
    assert detect_kind(Path("foo.db")) == "sqlite"
    assert detect_kind(Path("foo.jsonl")) == "jsonl"
    assert detect_kind(Path("foo.ndjson")) == "jsonl"
    assert detect_kind(Path("foo.csv")) == "csv"
    with pytest.raises(ValueError, match="unknown"):
        detect_kind(Path("foo.log"))


# ---- Django view tests ---------------------------------------------------


def _make_django_client(db_path: Path):
    """Configure Django settings + return a test client pointing at db_path."""
    os.environ["DJANGO_SETTINGS_MODULE"] = "ulog.web.settings"
    os.environ["ULOG_LOGS_PATH"] = str(db_path)
    os.environ["ULOG_LOGS_KIND"] = "sqlite"
    os.environ["ULOG_DEBUG"] = "0"

    import django
    from django.apps import apps as django_apps

    if not django_apps.ready:
        django.setup()
    # `settings.ULOG_LOGS_PATH` is resolved at module load (env-var read once),
    # so subsequent test fixtures with different `tmp_path` values would still
    # point at the original DB without this explicit update. Force-sync from
    # the env var we just set so each test sees its own fixture DB.
    from django.conf import settings as _dj_settings

    _dj_settings.ULOG_LOGS_PATH = str(db_path)
    _dj_settings.ULOG_LOGS_KIND = "sqlite"
    # Reset module-level adapter cache (tests reuse fixtures)
    from ulog.web.viewer import views as _views

    _views._adapter = None

    from django.test import Client

    return Client()


def test_list_view_returns_200_and_includes_records(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "ULog" in body
    assert "ROM not found" in body
    assert "myapp.audio.renderer" in body


def test_list_view_filter_by_level(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/?level=ERROR")
    body = resp.content.decode()
    assert "ROM not found" in body
    # The "user on /home" INFO record should NOT appear in ERROR-only filter
    assert "user on /home" not in body


def test_list_view_filter_by_sector(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/?logger=myapp.audio.engine")
    body = resp.content.decode()
    assert "ROM not found" in body
    assert "user on /home" not in body
    assert "rendering" not in body


def test_list_view_search(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/?q=rendering")
    body = resp.content.decode()
    assert "rendering" in body
    assert "user on /home" not in body


def test_detail_view(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/r/1/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "user on /home" in body or "rendering" in body


def test_detail_404(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/r/99999/")
    assert resp.status_code == 404


def test_api_records_returns_json(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/api/records/")
    assert resp.status_code == 200
    payload = json.loads(resp.content.decode())
    assert "records" in payload
    assert "total" in payload
    assert payload["total"] == 5
    assert "level_counts" in payload


def test_docs_index(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Quickstart" in body
    assert "Storage" in body or "storage" in body


def test_docs_page_renders_markdown(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/quickstart/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "<h1" in body  # rendered heading
    assert "ulog-web" in body
    # Code-block class from our minimal markdown renderer
    assert "<pre" in body
    assert "<code" in body


def test_docs_unknown_page_404(sqlite_fixture):
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/no-such-page/")
    assert resp.status_code == 404


# ============================================================================
# Story 1.6 — Tests sidebar (FR62-64)
# ============================================================================
#
# These tests build a SQLite log file containing plugin outcome records
# (logger='ulog.test' + context.outcome / duration_s / test_id), then verify
# the adapter aggregation, the view filter wiring, and the rendered template.


def _make_test_records_db(tmp_path: Path) -> Path:
    """Build a SQLite fixture with mixed plugin records covering AC scenarios:
    - 2 passing tests in test_a.py (fast + slow)
    - 1 failing test in test_a.py
    - 1 skipped test in test_b.py
    - 1 errored test (fixture failure) in test_b.py
    Plus a few `myapp` application records for compose-with-existing-filters tests.
    """

    db = tmp_path / "tests.sqlite"
    # Bootstrap a real SQLite via ulog.setup so the schema is correct.
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("ulog.test")
    app = ulog.get_logger("myapp")

    def emit_test(test_id: str, outcome: str, duration_s: float):
        # Emit started + outcome record matching Story 1.2's _emit_outcome_records
        ulog.bind(test_id=test_id)
        log.info("test started")
        level = logging.ERROR if outcome in ("failed", "errored") else logging.INFO
        log.log(
            level,
            f"test {outcome}",
            extra={
                "outcome": outcome,
                "duration_s": duration_s,
                "phase": "call",
            },
        )
        ulog.unbind("test_id")

    emit_test("tests/test_a.py::test_fast", "passed", 0.024)
    emit_test("tests/test_a.py::test_slow", "passed", 12.5)
    emit_test("tests/test_a.py::test_broken", "failed", 0.005)
    emit_test("tests/test_b.py::test_skip_me", "skipped", 0.0)
    emit_test("tests/test_b.py::test_setup_fail", "errored", 0.0001)

    # Application records (no test_id binding — these emit AFTER unbind)
    app.info("app log 1")
    app.warning("app log 2")

    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_test_summary_groups_by_file_and_sorts_alphabetically(tmp_path):
    """AC1, AC7 — test_summary returns rows grouped by file with alphabetical
    sort (file first, then name within file)."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_db(tmp_path)
    ad = SQLiteAdapter(db)
    res = ad.query(Filters())

    # 5 distinct test_ids → 5 summary rows
    assert len(res.test_summary) == 5, [r.test_id for r in res.test_summary]
    # Files alphabetical: test_a.py before test_b.py
    files_seen = [r.file for r in res.test_summary]
    assert files_seen == sorted(files_seen)
    # Within test_a.py, names alphabetical: test_broken < test_fast < test_slow
    a_names = [r.name for r in res.test_summary if r.file == "tests/test_a.py"]
    assert a_names == sorted(a_names)


def test_test_summary_empty_when_no_plugin_records(sqlite_fixture):
    """AC2 — fixture has only myapp records, no ulog.test → test_summary is []."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    ad = SQLiteAdapter(sqlite_fixture)
    res = ad.query(Filters())
    assert res.test_summary == []


def test_test_summary_picks_outcome_record_not_started(tmp_path):
    """AC6 — adapter aggregates BODY-VERDICT records only, ignoring `test started`
    records (which lack the outcome key)."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_db(tmp_path)
    ad = SQLiteAdapter(db)
    res = ad.query(Filters())

    # The fixture emits 2 records per test (started + outcome) for 5 tests = 10
    # records under logger='ulog.test'. Summary should dedupe to 5 rows by
    # picking only those with non-null context.outcome.
    assert len(res.test_summary) == 5
    # All 5 rows should have a non-empty outcome string
    for row in res.test_summary:
        assert row.outcome in ("passed", "failed", "skipped", "errored")


def test_test_summary_handles_all_four_outcomes(tmp_path):
    """All four outcomes (passed/failed/skipped/errored) round-trip correctly
    through the adapter."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_db(tmp_path)
    ad = SQLiteAdapter(db)
    res = ad.query(Filters())
    outcomes = {r.outcome for r in res.test_summary}
    assert outcomes == {"passed", "failed", "skipped", "errored"}


def test_failed_only_filter_via_query_param(tmp_path):
    """AC3 / FR63 — `?failed_only=1` filters records to outcome IN (failed, errored).

    Verifies via the adapter directly (records list) AND the rendered HTML
    (sidebar still shows ALL tests because the sidebar is unfiltered by design;
    the records list is what `failed_only` restricts). Review patch P4
    tightens the original loose `or` assertion that could pass vacuously.
    """
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_db(tmp_path)

    # Adapter-level: records list strictly restricted to failed/errored outcomes
    ad = SQLiteAdapter(db)
    res = ad.query(Filters(failed_only=True))
    assert res.total == 2, f"expected 2 records (failed + errored); got {res.total}"
    outcomes_seen = {r.context.get("outcome") for r in res.records}
    assert outcomes_seen == {"failed", "errored"}, outcomes_seen

    # View-level: HTTP request with the query param. Sidebar still shows all 5
    # tests (unfiltered summary); records list shows only the 2 failed/errored.
    client = _make_django_client(db)
    resp = client.get("/?failed_only=1")
    assert resp.status_code == 200
    body = resp.content.decode()
    # Sidebar shows ALL test names (not affected by failed_only)
    assert "test_broken" in body
    assert "test_setup_fail" in body


def test_existing_filters_compose_with_failed_only(tmp_path):
    """AC9 — `failed_only` ANDs with existing filters (level / logger).

    Compose `?failed_only=1&level=ERROR&logger=ulog.test` and verify the
    intersection: records must satisfy ALL three constraints simultaneously.
    """
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_db(tmp_path)
    ad = SQLiteAdapter(db)
    # All three filters: failed_only + level=ERROR + logger=ulog.test
    res = ad.query(
        Filters(
            failed_only=True,
            levels=["ERROR"],
            loggers=["ulog.test"],
        )
    )
    # Of the 5 tests in the fixture, 2 have failed/errored outcome AND emit
    # at level ERROR (failed + errored) — both are also on logger 'ulog.test'.
    assert res.total == 2, f"expected 2 records; got {res.total}"
    for r in res.records:
        assert r.level == "ERROR"
        assert r.logger == "ulog.test"
        assert r.context.get("outcome") in ("failed", "errored")


def test_slowest_only_orders_by_duration_desc(tmp_path):
    """AC4 / FR64 — `?slowest_only=1` orders by duration_s DESC and caps at 10."""
    from ulog.web.viewer.adapters import SLOWEST_TOP_N, Filters, SQLiteAdapter

    # Build a fixture with 12 outcome records of varying duration; expect
    # SLOWEST_TOP_N=10 returned in DESC order.
    db = tmp_path / "many.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("ulog.test")
    durations = [0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5]
    for i, d in enumerate(durations):
        ulog.bind(test_id=f"tests/test_x.py::test_n{i:02d}")
        log.info("test started")
        log.info("test passed", extra={"outcome": "passed", "duration_s": d, "phase": "call"})
        ulog.unbind("test_id")
    for h in logging.getLogger().handlers:
        h.flush()

    ad = SQLiteAdapter(db)
    res = ad.query(Filters(slowest_only=True))
    # Capped at SLOWEST_TOP_N
    assert len(res.records) == SLOWEST_TOP_N
    # Returned in DESC order — first record should be the slowest (5.5s)
    first_ctx = res.records[0].context
    assert float(first_ctx["duration_s"]) == 5.5
    # Top 10 by DESC of [0.1, 0.5, 1.0, 1.5, ..., 5.5] drops the bottom 2
    # (0.1 and 0.5). The 10th slowest is 1.0s.
    last_ctx = res.records[-1].context
    assert float(last_ctx["duration_s"]) == 1.0


def test_failed_and_slowest_combine(tmp_path):
    """AC5 — both flags AND together: top-10 of failed-or-errored tests."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = tmp_path / "mix.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("ulog.test")

    # 5 failed slow + 5 passed fast + 5 failed fast → expect 10 failed (5 slow + 5 fast)
    def emit(tid, outcome, dur):
        ulog.bind(test_id=tid)
        log.info("test started")
        level = logging.ERROR if outcome in ("failed", "errored") else logging.INFO
        log.log(
            level,
            f"test {outcome}",
            extra={
                "outcome": outcome,
                "duration_s": dur,
                "phase": "call",
            },
        )
        ulog.unbind("test_id")

    for i in range(5):
        emit(f"tests/t.py::failed_slow_{i}", "failed", 5.0 + i)
    for i in range(5):
        emit(f"tests/t.py::passed_fast_{i}", "passed", 0.01)
    for i in range(5):
        emit(f"tests/t.py::failed_fast_{i}", "failed", 0.005)
    for h in logging.getLogger().handlers:
        h.flush()

    ad = SQLiteAdapter(db)
    res = ad.query(Filters(failed_only=True, slowest_only=True))
    # Intersection: 10 failed records (5 slow + 5 fast), capped at 10
    assert len(res.records) == 10
    # All returned records have outcome failed/errored
    for r in res.records:
        assert r.context["outcome"] in ("failed", "errored")
    # Slowest first: top record is failed_slow_4 (duration 9.0)
    assert float(res.records[0].context["duration_s"]) == 9.0


def test_tests_sidebar_renders_when_records_exist(tmp_path):
    """AC1 — TESTS sidebar section appears when test records are present."""
    db = _make_test_records_db(tmp_path)
    client = _make_django_client(db)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode()
    # The section heading is wrapped in <span>Tests</span> per the template.
    assert "<span>Tests</span>" in body
    # At least one outcome glyph should appear (we have passed and failed in the fixture)
    assert "✓" in body or "✗" in body


def test_tests_sidebar_hidden_when_no_test_records(sqlite_fixture):
    """AC2 — TESTS sidebar is NOT rendered when no ulog.test records exist."""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.content.decode()
    # The fixture has only myapp records → section heading must be absent.
    assert "<span>Tests</span>" not in body


def test_duration_format_milliseconds_and_seconds(tmp_path):
    """AC8 — duration display uses ms for fast tests, s with one decimal for slow."""
    db = _make_test_records_db(tmp_path)
    client = _make_django_client(db)
    resp = client.get("/")
    body = resp.content.decode()
    # test_fast = 0.024 → "24ms"
    assert "24ms" in body
    # test_slow = 12.5 → "12.5s"
    assert "12.5s" in body
    # test_setup_fail = 0.0001 → "<1ms"
    assert "&lt;1ms" in body or "<1ms" in body


# ============================================================================
# Story 1.7 — Click test name to filter records by test_id (FR65)
# ============================================================================
#
# These tests verify the `?test_id=...` URL filter at three layers:
#   - Adapter: SQLiteAdapter._base_filters and _filter_and_paginate.keep
#     both restrict records to context.test_id == filter value
#   - View: _parse_filters decodes the query param; list_view exposes
#     `qs_minus_test_id` for the template
#   - Template: TESTS sidebar test name wrapped in <a href> with active-row
#     marker, with other filters preserved (page=N is dropped on purpose)


def _make_test_records_with_app_logs(tmp_path: Path) -> Path:
    """Build a fixture where each test ALSO emits an application log record
    bound to the same test_id (Story 1.4 propagation). Story 1.7's filter
    must return BOTH plugin records AND propagated app records — this fixture
    lets us assert that property."""
    db = tmp_path / "with_app.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    plugin = ulog.get_logger("ulog.test")
    app = ulog.get_logger("myapp")

    def emit(test_id: str, outcome: str):
        ulog.bind(test_id=test_id)
        plugin.info("test started")
        app.info(f"app log for {test_id}")  # Story 1.4 propagation: gets test_id
        # Plugin emits failed/errored outcomes at ERROR level (Story 1.2 contract)
        level = logging.ERROR if outcome in ("failed", "errored") else logging.INFO
        plugin.log(
            level,
            f"test {outcome}",
            extra={
                "outcome": outcome,
                "duration_s": 0.01,
                "phase": "call",
            },
        )
        ulog.unbind("test_id")

    emit("tests/test_a.py::test_one", "passed")
    emit("tests/test_a.py::test_two", "failed")
    emit("tests/test_b.py::test_three", "passed")
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_test_id_filter_restricts_to_one_test(tmp_path):
    """AC1, AC5 — `Filters(test_id=...)` returns ALL records (plugin + app)
    bound to that test_id and ONLY those records."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_with_app_logs(tmp_path)
    ad = SQLiteAdapter(db)
    res = ad.query(Filters(test_id="tests/test_a.py::test_one"))

    # 3 records expected: started + app log + passed (all carry test_id)
    assert res.total == 3, [r.msg for r in res.records]
    for r in res.records:
        assert r.context.get("test_id") == "tests/test_a.py::test_one"
    # Verify both plugin and app records are present
    loggers_seen = {r.logger for r in res.records}
    assert loggers_seen == {"ulog.test", "myapp"}, loggers_seen


def test_test_id_filter_via_query_param(tmp_path):
    """AC1, AC7 — `?test_id=<encoded>` HTTP request filters records list."""
    from urllib.parse import quote

    db = _make_test_records_with_app_logs(tmp_path)
    client = _make_django_client(db)
    encoded = quote("tests/test_a.py::test_one", safe="")
    resp = client.get(f"/?test_id={encoded}")
    assert resp.status_code == 200
    body = resp.content.decode()
    # The test's records should be present; the OTHER tests' messages absent.
    assert "app log for tests/test_a.py::test_one" in body
    assert "app log for tests/test_a.py::test_two" not in body
    assert "app log for tests/test_b.py::test_three" not in body


def test_test_id_filter_empty_value_no_filter(tmp_path):
    """AC3 — `?test_id=` (empty value) is treated as "no filter applied"."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_with_app_logs(tmp_path)
    ad = SQLiteAdapter(db)
    res_filtered = ad.query(Filters(test_id=""))
    res_unfiltered = ad.query(Filters())
    assert res_filtered.total == res_unfiltered.total


def test_test_id_filter_unknown_returns_zero_records(tmp_path):
    """AC3 — unknown test_id returns 0 records, NOT a 500 error."""
    db = _make_test_records_with_app_logs(tmp_path)
    client = _make_django_client(db)
    resp = client.get("/?test_id=tests/nope.py::missing")
    assert resp.status_code == 200
    body = resp.content.decode()
    # No app log records should appear (no test matches)
    assert "app log for tests/test_a" not in body
    assert "app log for tests/test_b" not in body


def test_test_id_filter_composes_with_failed_only_and_level(tmp_path):
    """AC4 — `?test_id=X&failed_only=1&level=ERROR` ANDs all three filters."""
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_with_app_logs(tmp_path)
    ad = SQLiteAdapter(db)
    # test_two is the failing one; outcome record is at ERROR
    res = ad.query(
        Filters(
            test_id="tests/test_a.py::test_two",
            failed_only=True,
            levels=["ERROR"],
        )
    )
    # Only the outcome ERROR record matches all 3 filters
    assert res.total == 1, f"got {res.total} records"
    r = res.records[0]
    assert r.context.get("test_id") == "tests/test_a.py::test_two"
    assert r.context.get("outcome") == "failed"
    assert r.level == "ERROR"


def test_test_id_filter_active_row_visually_distinguished(tmp_path):
    """AC6 — when a test_id filter is active, the matching sidebar row gets
    `data-active-test="true"`. The Tailwind classes for visual styling are
    NOT part of the contract (formatters/linters can reorder them)."""
    from urllib.parse import quote

    db = _make_test_records_with_app_logs(tmp_path)
    client = _make_django_client(db)
    encoded = quote("tests/test_a.py::test_one", safe="")
    resp = client.get(f"/?test_id={encoded}")
    body = resp.content.decode()
    assert 'data-active-test="true"' in body, (
        'AC6: active sidebar row must carry data-active-test="true"'
    )


def test_test_id_filter_anchor_preserves_other_filters(tmp_path):
    """AC7 — clicking a sidebar test from a session with other filters
    active preserves those filters in the resulting URL."""
    import html
    import re
    from urllib.parse import parse_qs, urlparse

    db = _make_test_records_with_app_logs(tmp_path)
    client = _make_django_client(db)
    # Open the page with multiple filters already active
    resp = client.get("/?level=ERROR&logger=ulog.test&failed_only=1")
    body = resp.content.decode()
    # Find any sidebar anchor for a test row. Django auto-escapes `&` as
    # `&amp;` in HTML attributes — html.unescape decodes it back so urlparse
    # sees real `&` separators.
    matches = re.findall(r'href="(\?test_id=[^"]+)"', body)
    assert matches, "expected at least one sidebar test_id anchor"
    href = html.unescape(matches[0])
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    assert "test_id" in qs
    assert qs.get("level") == ["ERROR"], qs
    assert qs.get("logger") == ["ulog.test"], qs
    assert qs.get("failed_only") == ["1"], qs


def test_test_id_filter_anchor_drops_page_param(tmp_path):
    """AC7 / VS-step C2 — sidebar anchors must NOT preserve `?page=N`.
    Clicking a test from page 5 should reset to page 1, not land on a stale
    page-5 view of the (typically smaller) filtered set."""
    import html
    import re
    from urllib.parse import parse_qs, urlparse

    db = _make_test_records_with_app_logs(tmp_path)
    client = _make_django_client(db)
    resp = client.get("/?page=5")
    body = resp.content.decode()
    matches = re.findall(r'href="(\?test_id=[^"]+)"', body)
    assert matches
    parsed = urlparse(html.unescape(matches[0]))
    qs = parse_qs(parsed.query)
    assert "page" not in qs, f"AC7: sidebar anchor must drop ?page; got qs={qs}"


def test_test_id_filter_parametrized_id_url_encoded(tmp_path):
    """E3 — parametrize IDs like `test_p[True-1]` contain `[` and `]`;
    Django's |urlencode must percent-encode them as %5B and %5D."""
    db = tmp_path / "param.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("ulog.test")

    ulog.bind(test_id="tests/test_p.py::test_param[True-1]")
    log.info("test started")
    log.info(
        "test passed",
        extra={
            "outcome": "passed",
            "duration_s": 0.01,
            "phase": "call",
        },
    )
    ulog.unbind("test_id")
    for h in logging.getLogger().handlers:
        h.flush()

    client = _make_django_client(db)
    resp = client.get("/")
    body = resp.content.decode()
    # The sidebar anchor must encode `[` as %5B and `]` as %5D
    assert "%5BTrue-1%5D" in body or "%5Btrue-1%5D" in body.lower(), (
        "parametrize bracket IDs must be percent-encoded in the anchor href"
    )


def test_test_id_does_not_poison_ghost_counts(tmp_path):
    """Story 1.7 review patch P1 — when test_id filter is active, the per-axis
    ghost counts (level/logger/file) must NOT be scoped to that test only.
    Per PRD-v0.2.1 the ghost-count UX shows "what would I get if I ALSO ticked
    another value on this axis" — a poisoning test_id would silently break it.
    """
    from ulog.web.viewer.adapters import Filters, SQLiteAdapter

    db = _make_test_records_with_app_logs(tmp_path)
    ad = SQLiteAdapter(db)

    # Baseline: no test_id filter → level/logger/file counts cover ALL records
    res_unfiltered = ad.query(Filters())

    # With test_id active: ghost counts must STILL match the unfiltered baseline
    # (each axis ghost-count strips test_id along with its own axis).
    res_with_test_id = ad.query(Filters(test_id="tests/test_a.py::test_one"))

    assert res_with_test_id.level_counts == res_unfiltered.level_counts, (
        f"level ghost-counts poisoned by test_id; "
        f"baseline={res_unfiltered.level_counts!r}, "
        f"with_test_id={res_with_test_id.level_counts!r}"
    )
    assert res_with_test_id.sector_counts == res_unfiltered.sector_counts, (
        "sector ghost-counts poisoned by test_id"
    )
    assert res_with_test_id.file_counts == res_unfiltered.file_counts, (
        "file ghost-counts poisoned by test_id"
    )


# ============================================================================
# Story 1.8 — Detail-view Test context panel (FR66)
# ============================================================================
#
# Tests verify the panel at three layers:
#   - Adapter helpers: count_records_for_test_id + get_test_summary_row
#   - View: detail_view passes test_id / test_summary_row / test_record_count to ctx
#   - Template: detail.html renders the panel when test_id is set, hides otherwise


def test_count_records_for_test_id(tmp_path):
    """AC5 — count_records_for_test_id returns the exact count of records
    bound to that test_id (plugin + propagated app records)."""
    from ulog.web.viewer.adapters import SQLiteAdapter

    db = _make_test_records_with_app_logs(tmp_path)
    ad = SQLiteAdapter(db)
    # Each test in _make_test_records_with_app_logs emits exactly 3 records:
    # plugin started + app log + plugin outcome.
    assert ad.count_records_for_test_id("tests/test_a.py::test_one") == 3
    assert ad.count_records_for_test_id("tests/test_a.py::test_two") == 3
    assert ad.count_records_for_test_id("nonexistent::test_id") == 0
    assert ad.count_records_for_test_id("") == 0


def test_get_test_summary_row_returns_correct_outcome(tmp_path):
    """AC6 — get_test_summary_row returns the TestSummaryRow whose outcome
    matches the test (passed for test_one, failed for test_two)."""
    from ulog.web.viewer.adapters import SQLiteAdapter

    db = _make_test_records_with_app_logs(tmp_path)
    ad = SQLiteAdapter(db)
    row_passed = ad.get_test_summary_row("tests/test_a.py::test_one")
    assert row_passed is not None
    assert row_passed.outcome == "passed"
    row_failed = ad.get_test_summary_row("tests/test_a.py::test_two")
    assert row_failed is not None
    assert row_failed.outcome == "failed"


def test_get_test_summary_row_unknown_returns_none(tmp_path):
    """get_test_summary_row returns None for unknown test_ids (defensive)."""
    from ulog.web.viewer.adapters import SQLiteAdapter

    db = _make_test_records_with_app_logs(tmp_path)
    ad = SQLiteAdapter(db)
    assert ad.get_test_summary_row("does/not/exist::missing") is None
    assert ad.get_test_summary_row("") is None


def _find_first_record_id_for_test_id(db: Path, test_id: str) -> int:
    """Helper: read SQLite DB, return the id of the first record with the
    matching context.test_id. Used to construct detail-view URLs."""
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id FROM logs WHERE json_extract(context, '$.test_id') = ? "
            "ORDER BY id ASC LIMIT 1",
            (test_id,),
        )
        row = cur.fetchone()
        return int(row["id"]) if row else -1
    finally:
        conn.close()


def test_detail_view_renders_test_context_panel_when_record_has_test_id(tmp_path):
    """AC1, AC6 — detail view renders the panel with outcome badge when the
    record has a test_id."""
    db = _make_test_records_with_app_logs(tmp_path)
    record_id = _find_first_record_id_for_test_id(db, "tests/test_a.py::test_one")
    assert record_id > 0

    client = _make_django_client(db)
    resp = client.get(f"/r/{record_id}/")
    assert resp.status_code == 200
    body = resp.content.decode()
    # Section heading
    assert "<span>Test context</span>" in body, body[:500]
    # Outcome glyph (test_one passed)
    assert "✓" in body
    # Test_id rendered
    assert "tests/test_a.py::test_one" in body
    # Both jump-links present
    assert "view all records for this test" in body
    assert "errors+warnings only" in body


def test_detail_view_hides_test_context_panel_when_record_has_no_test_id(
    sqlite_fixture,
):
    """AC2 — for a non-test record (myapp logger, no test_id binding), the
    panel does NOT render."""
    # The sqlite_fixture has only myapp records, no ulog.test plugin records.
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/r/1/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "<span>Test context</span>" not in body


def test_detail_view_test_context_link_uses_test_id_filter(tmp_path):
    """AC3 — 'view all records' anchor href is `/?test_id=<urlencoded>`."""
    import html
    import re
    from urllib.parse import parse_qs, urlparse

    db = _make_test_records_with_app_logs(tmp_path)
    record_id = _find_first_record_id_for_test_id(db, "tests/test_a.py::test_one")
    client = _make_django_client(db)
    resp = client.get(f"/r/{record_id}/")
    body = resp.content.decode()

    # Find the "view all records" anchor — match the href of any anchor whose
    # text contains the link label
    pattern = r'href="([^"]+)"[^>]*>\s*\n?\s*view all records for this test'
    matches = re.findall(pattern, body)
    assert matches, "expected 'view all records' anchor in body"
    href = html.unescape(matches[0])
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    assert qs.get("test_id") == ["tests/test_a.py::test_one"], qs


def test_detail_view_errors_warnings_link_combines_filters(tmp_path):
    """AC4 — 'errors+warnings only' anchor combines test_id with level=ERROR
    AND level=WARNING (multi-value level filter)."""
    import html
    import re
    from urllib.parse import parse_qs, urlparse

    db = _make_test_records_with_app_logs(tmp_path)
    record_id = _find_first_record_id_for_test_id(db, "tests/test_a.py::test_one")
    client = _make_django_client(db)
    resp = client.get(f"/r/{record_id}/")
    body = resp.content.decode()

    pattern = r'href="([^"]+)"[^>]*>\s*\n?\s*errors\+warnings only'
    matches = re.findall(pattern, body)
    assert matches, "expected 'errors+warnings only' anchor"
    href = html.unescape(matches[0])
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    assert qs.get("test_id") == ["tests/test_a.py::test_one"]
    # Set comparison — order of `level=ERROR&level=WARNING` in the rendered
    # href is fixed by the template, but order-independent assertions are
    # more robust against future template tweaks (review patch P3).
    assert set(qs.get("level", [])) == {"ERROR", "WARNING"}, qs


def test_detail_view_panel_renders_for_plugin_outcome_record(tmp_path):
    """AC7 — opening the detail of a PLUGIN outcome record (the 'test passed'
    record itself) still renders the panel — with consistent fields, since
    that record is the source of truth for the outcome."""
    import sqlite3

    db = _make_test_records_with_app_logs(tmp_path)
    # Find the plugin outcome record (logger='ulog.test' AND msg='test passed')
    conn = sqlite3.connect(str(db))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id FROM logs "
            "WHERE logger='ulog.test' AND msg='test passed' "
            "AND json_extract(context, '$.test_id') = ? "
            "LIMIT 1",
            ("tests/test_a.py::test_one",),
        )
        row = cur.fetchone()
        assert row is not None
        record_id = int(row["id"])
    finally:
        conn.close()

    client = _make_django_client(db)
    resp = client.get(f"/r/{record_id}/")
    assert resp.status_code == 200
    body = resp.content.decode()
    # Panel still renders for plugin records
    assert "<span>Test context</span>" in body
    # Phase line should appear (outcome records have context.phase)
    assert "phase: call" in body


def test_detail_view_total_records_count_matches_test_id_records(tmp_path):
    """AC5 — rendered HTML shows the correct count: 3 records for test_one
    (plugin started + app log + plugin outcome per fixture)."""
    db = _make_test_records_with_app_logs(tmp_path)
    record_id = _find_first_record_id_for_test_id(db, "tests/test_a.py::test_one")
    client = _make_django_client(db)
    resp = client.get(f"/r/{record_id}/")
    body = resp.content.decode()
    assert "3 records" in body, (
        f"expected '3 records' in detail page body; got snippet: {body[2000:3000]}"
    )


# ============================================================================
# Story 1.11 — Doc page /docs/test-integration/ (NFR-DOC-10)
# ============================================================================


def test_test_integration_doc_page_renders(sqlite_fixture):
    """AC1, AC3 — page renders with 200 + structural elements + required sections."""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/test-integration/")
    assert resp.status_code == 200
    body = resp.content.decode()
    # AC3: structural elements
    assert "<h1" in body
    assert "<h2" in body
    assert "<pre" in body
    assert "<code" in body
    # AC1: required sections
    assert "Install" in body
    assert "CLI flags" in body
    assert "Test event schema" in body
    assert "worked example" in body or "Find failed tests" in body


def test_test_integration_doc_page_listed_in_index(sqlite_fixture):
    """AC2 — /docs/ index lists the new page with a clickable link."""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Test integration" in body
    assert "/docs/test-integration/" in body


def test_test_integration_doc_page_includes_conftest_example(sqlite_fixture):
    """AC4 — canonical conftest recipe (verbatim per PRD-v0.3 §5.1)."""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/test-integration/")
    body = resp.content.decode()
    assert "ulog.setup(" in body
    # The in-house renderer HTML-escapes single quotes; check both forms
    # to be robust against the escaping convention.
    assert (
        "handlers=[&#x27;sql&#x27;]" in body
        or "handlers=[&#39;sql&#39;]" in body
        or "handlers=['sql']" in body
    )
    assert "sql_url=" in body


def test_test_integration_doc_page_includes_summary_line_example(sqlite_fixture):
    """AC5 — exact-format summary line from PRD §2.1.6 / Story 1.5."""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/test-integration/")
    body = resp.content.decode()
    assert "ulog: 412 tests, 409 passed, 3 failed, 0 skipped" in body
    assert "ulog-web" in body


def test_test_integration_doc_page_includes_test_event_example(sqlite_fixture):
    """AC6 — programmatic API example present."""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/test-integration/")
    body = resp.content.decode()
    assert "from ulog.testing import test_event" in body
    assert "with test_event(" in body
    assert "ev.outcome(" in body


def test_test_integration_unknown_subpage_404(sqlite_fixture):
    """The page slug is 'test-integration'; anything else 404s."""
    client = _make_django_client(sqlite_fixture)
    resp = client.get("/docs/test-integration-WRONG/")
    assert resp.status_code == 404
