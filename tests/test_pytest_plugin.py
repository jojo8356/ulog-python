"""Tests for ulog.testing.pytest_plugin (Stories 1.1 + 1.2).

Story 1.1: FR51-53 (auto-discovery + gating) and FR67-69 (CLI flag registration).
Story 1.2: FR54-58 (test event recording — start/outcome/finish + traceback).

Uses pytest's built-in ``pytester`` fixture (ships with pytest 7.0+, no new
dep) to run pytest-in-pytest scenarios.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

# pytester relies on pytest collecting `pytester` as a plugin.
# Activating it for this module is the canonical pattern.
pytest_plugins = ["pytester"]


@pytest.fixture(autouse=True)
def _isolate_logging():
    """Strip _ulog_managed handlers between tests (mirrors tests/test_setup.py)."""
    yield
    for name in (None, "test", "test.sub", "myapp", "qlnes", "ulog.test"):
        logger = logging.getLogger(name)
        for h in list(logger.handlers):
            if getattr(h, "_ulog_managed", False):
                logger.removeHandler(h)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def test_plugin_is_registered(pytester: pytest.Pytester) -> None:
    """AC1 — pytest --trace-config lists the ulog plugin."""
    pytester.makepyfile("def test_x(): pass")
    result = pytester.runpytest("--trace-config")
    # Match the actual plugin module path (more specific than "*ulog*", which
    # could spuriously match unrelated mentions of the string "ulog").
    result.stdout.fnmatch_lines(["*ulog.testing.pytest_plugin*"])


def test_gate_off_by_default(pytester: pytest.Pytester) -> None:
    """AC2 — gate is False with no host setup and no --ulog-db."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert getattr(pytestconfig, '_ulog_enabled', None) is False
        """
    )
    result = pytester.runpytest()
    assert result.ret == 0


def test_gate_on_with_ulog_db(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC2 inverse — --ulog-db sets gate True."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is True
        """
    )
    db = tmp_path / "x.sqlite"
    result = pytester.runpytest("--ulog-db", str(db))
    assert result.ret == 0


def test_gate_on_with_host_setup(pytester: pytest.Pytester) -> None:
    """AC2 inverse — host conftest setup() sets gate True.

    Verifies that ``@pytest.hookimpl(trylast=True)`` correctly schedules
    our pytest_configure AFTER the user's conftest pytest_configure.
    """
    pytester.makeconftest(
        """
        import ulog
        def pytest_configure(config):
            ulog.setup()  # idempotent — installs _ulog_managed handler
        """
    )
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is True
        """
    )
    result = pytester.runpytest()
    assert result.ret == 0


def test_ulog_disable_overrides(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC3 — --ulog-disable short-circuits even when other gating triggers fire."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is False
        """
    )
    db = tmp_path / "x.sqlite"
    result = pytester.runpytest("--ulog-db", str(db), "--ulog-disable")
    assert result.ret == 0


def test_three_flags_in_help(pytester: pytest.Pytester) -> None:
    """AC4 — the three flags appear in pytest --help."""
    result = pytester.runpytest("--help")
    output = result.stdout.str() + result.stderr.str()
    assert "--ulog-db" in output
    assert "--ulog-disable" in output
    assert "--ulog-summary" in output


# ============================================================================
# Story 1.2 — Test event recording (FR54-58)
# ============================================================================


def _read_test_records(db_path: Path) -> list[dict]:
    """Read ``ulog.test`` records from a SQLite log DB. Returns list of dicts
    in id (= insertion) order. Used by Story 1.2 tests to inspect the records
    emitted by the plugin's hooks."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM logs WHERE logger='ulog.test' ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _read_app_records(db_path: Path, logger_name: str) -> list[dict]:
    """Read records filtered by exact logger name from a SQLite log DB.

    Story 1.4 (FR60/61) needs to assert that APPLICATION records — those
    produced by ``logging.getLogger("myapp").info(...)`` from inside a test —
    carry the bound ``test_id``. ``_read_test_records`` filters for
    ``logger='ulog.test'`` (the plugin's own records); this helper takes the
    logger name as a parameter so callers can target any specific logger.
    Passing ``"ulog.test"`` here would return plugin records — there's no
    built-in plugin/non-plugin distinction (review patch P3).

    Exact match only — uses ``WHERE logger = ?``. For hierarchical filtering
    (catching ``"myapp"`` AND ``"myapp.submodule"`` together) a future helper
    would need ``WHERE logger LIKE ?`` with ``"myapp.%"``. None of Story 1.4's
    seven tests need that — they all emit through a single logger name.

    Returns ``[]`` if the ``logs`` table doesn't exist yet (the SQL handler
    creates the schema lazily on first emit; tests that exercise the
    "no records emitted" path would otherwise hit ``OperationalError``).
    Review patch P5.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT * FROM logs WHERE logger = ? ORDER BY id ASC",
                (logger_name,),
            )
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.OperationalError as e:
            # "no such table: logs" → schema never created (zero emits).
            # Distinguish from other operational errors so genuine bugs surface.
            if "no such table" in str(e):
                return []
            raise
    finally:
        conn.close()


def _conftest_with_setup(db_path: Path) -> str:
    """Standard host conftest that activates the plugin via SQL handler setup.

    ``sql_batch_size=1`` is critical here: ``pytester.runpytest()`` runs
    in-process so the SQL handler's atexit flush never fires before the
    outer test reads the DB. Setting batch_size=1 makes every emit flush
    immediately, surfacing all records to the DB synchronously.

    A pytest_unconfigure hook also explicitly closes/flushes any
    _ulog_managed handlers as a belt-and-braces measure for any future
    handler that does not flush per-emit.
    """
    # Use as_posix() so the embedded path uses forward slashes — required for
    # the SQLAlchemy URL on Windows (review finding M1).
    posix_path = db_path.as_posix()
    return f"""
        import logging
        import ulog
        def pytest_configure(config):
            ulog.setup(handlers=['sql'], sql_url='sqlite:///{posix_path}', sql_batch_size=1)
        def pytest_unconfigure(config):
            for h in list(logging.getLogger().handlers):
                if getattr(h, '_ulog_managed', False):
                    try:
                        h.flush()
                        h.close()
                    except Exception:
                        pass
                    logging.getLogger().removeHandler(h)
    """


def _conftest_unconfigure_flush_only() -> str:
    """Conftest body for tests that exercise the plugin's --ulog-db auto-setup
    path: NO host pytest_configure call (so the plugin's own auto-setup is
    what wires up the SQL handler), but a pytest_unconfigure that flushes
    any _ulog_managed handlers before the outer test reads back the DB.

    Used by Story 1.5 tests that exercise FR67 auto-setup (Tasks 4.2, 5.2).
    Distinct from `_conftest_with_setup` which simulates a host that already
    configured ulog (where auto-setup MUST NOT fire).
    """
    return """
        import logging
        def pytest_unconfigure(config):
            for h in list(logging.getLogger().handlers):
                if getattr(h, '_ulog_managed', False):
                    try:
                        h.flush()
                        h.close()
                    except Exception:
                        pass
                    logging.getLogger().removeHandler(h)
    """


def test_passing_test_emits_two_records(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC1, AC5 — pass → 2 records (started + passed) with phase=call, duration_s>=0."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest()
    assert result.ret == 0

    records = _read_test_records(db)
    assert len(records) == 2, f"expected 2 records, got {len(records)}: {records}"
    assert records[0]["msg"] == "test started"
    assert records[1]["msg"] == "test passed"

    ctx = json.loads(records[1]["context"])
    assert ctx["outcome"] == "passed"
    assert ctx["phase"] == "call"
    assert ctx["duration_s"] >= 0.0
    assert ctx["test_id"].endswith("::test_pass")


def test_failing_test_emits_three_records(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC2 — fail → 3 records: started, outcome (level=ERROR), traceback ERROR."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        def test_fail():
            assert 1 == 2
        """
    )
    result = pytester.runpytest()
    assert result.ret != 0  # pytest reports test failure

    records = _read_test_records(db)
    assert len(records) == 3, f"expected 3 records, got {len(records)}: {records}"
    assert records[0]["msg"] == "test started"
    assert records[0]["level"] == "INFO"

    # Outcome record
    assert records[1]["msg"] == "test failed"
    assert records[1]["level"] == "ERROR"
    ctx_outcome = json.loads(records[1]["context"])
    assert ctx_outcome["outcome"] == "failed"
    assert ctx_outcome["phase"] == "call"

    # Traceback record (separate ERROR with exc.tb)
    assert records[2]["level"] == "ERROR"
    assert "AssertionError" in records[2]["msg"]
    ctx_tb = json.loads(records[2]["context"])
    assert ctx_tb["exc"]["type"] == "AssertionError"
    assert ctx_tb["exc"]["msg"]
    assert isinstance(ctx_tb["exc"]["tb"], list)
    assert len(ctx_tb["exc"]["tb"]) > 0


def test_outcome_record_has_phase_field(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC3 — outcome record always carries context.phase."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    pytester.runpytest()

    records = _read_test_records(db)
    ctx = json.loads(records[1]["context"])
    assert "phase" in ctx
    assert ctx["phase"] in ("setup", "call", "teardown")


def test_teardown_failure_separate_record(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC4 — teardown failure → outcome=passed (body verdict) + separate ERROR with phase=teardown."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def boom_in_teardown():
            yield "ok"
            raise RuntimeError("teardown explodes")

        def test_body_passes(boom_in_teardown):
            assert boom_in_teardown == "ok"
        """
    )
    pytester.runpytest()  # ret != 0 because teardown failed; we don't care about pytest's exit code

    records = _read_test_records(db)
    assert len(records) == 3, f"expected 3 records, got {len(records)}: {records}"

    # Body outcome stays "passed" — teardown failure does not flip it
    ctx_outcome = json.loads(records[1]["context"])
    assert ctx_outcome["outcome"] == "passed", "teardown failure must not flip body outcome (AC4)"
    assert ctx_outcome["phase"] == "call"

    # Separate ERROR with phase=teardown
    assert records[2]["level"] == "ERROR"
    assert "teardown failed" in records[2]["msg"]
    ctx_td = json.loads(records[2]["context"])
    assert ctx_td["phase"] == "teardown"
    # `excinfo.type.__name__` is the canonical source — exact match expected
    # (review finding L3: previous loose `or "Exception" in ...` masked regressions).
    assert ctx_td["exc"]["type"] == "RuntimeError"


def test_skipped_test(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """Skipped test → 2 records, outcome=skipped, level=INFO (not ERROR)."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import pytest
        def test_skip():
            pytest.skip("not in scope")
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    assert len(records) == 2
    assert records[1]["msg"] == "test skipped"
    assert records[1]["level"] == "INFO"
    ctx = json.loads(records[1]["context"])
    assert ctx["outcome"] == "skipped"


def test_records_carry_test_id(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC6 — every record's context.test_id equals item.nodeid."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        def test_one(): assert True
        def test_two(): assert True
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    test_ids_seen: set[str] = set()
    for rec in records:
        ctx = json.loads(rec["context"])
        assert "test_id" in ctx
        test_ids_seen.add(ctx["test_id"])

    # Both tests' nodeids should appear
    assert any(tid.endswith("::test_one") for tid in test_ids_seen)
    assert any(tid.endswith("::test_two") for tid in test_ids_seen)


def test_records_use_ulog_test_logger(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC8 — all plugin records use logger='ulog.test'."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    pytester.runpytest()

    records = _read_test_records(db)
    assert len(records) == 2  # passing test → exactly started + outcome
    for rec in records:
        assert rec["logger"] == "ulog.test"


def test_setup_failure_emits_errored(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC3 sub-case + `errored` outcome path — setup failure → outcome=errored, phase=setup,
    plus a separate ERROR record carrying the fixture's exception."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def boom_in_setup():
            raise RuntimeError("setup explodes")

        def test_body_never_runs(boom_in_setup):
            assert False, "should never reach this"
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    assert len(records) == 3, f"expected 3 records, got {len(records)}: {records}"

    ctx_outcome = json.loads(records[1]["context"])
    assert ctx_outcome["outcome"] == "errored"
    assert ctx_outcome["phase"] == "setup"
    assert records[1]["level"] == "ERROR"

    # Traceback record carries the fixture's RuntimeError
    assert records[2]["level"] == "ERROR"
    ctx_tb = json.loads(records[2]["context"])
    assert ctx_tb["exc"]["type"] == "RuntimeError"


def test_duration_reflects_sleep(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC5 — `time.sleep(0.05)` body → outcome record's duration_s ≥ 0.05.

    Verifies that the duration is genuinely a sum-of-phases wall-time
    measurement, not a hardcoded 0.0 floor. A regression that computed only
    `report.call.duration` would still pass `>= 0.0` but would fail this
    bounded check.
    """
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import time
        def test_slow():
            time.sleep(0.05)
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    assert len(records) == 2
    ctx = json.loads(records[1]["context"])
    assert ctx["duration_s"] >= 0.05, (
        f"duration_s should reflect the sleep; got {ctx['duration_s']}"
    )


def test_disabled_plugin_emits_nothing(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC7 — with --ulog-disable, zero records emitted to ulog.test logger."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    pytester.runpytest("--ulog-disable")

    # `ulog.setup()` creates the SQLAlchemy engine but the SQLite schema is
    # lazy-created on first `emit()`. With `--ulog-disable`, our hooks never
    # call emit, so no schema → no DB file. Both outcomes (no DB / empty DB)
    # satisfy AC7. The explicit `else: []` makes the assertion non-vacuous —
    # if the file exists, records MUST be empty (review finding L4 / Edge C).
    records = _read_test_records(db) if db.exists() else []
    assert records == [], f"--ulog-disable must suppress all ulog.test records; got {records}"


# ============================================================================
# Story 1.3 — Test ID stability (FR55)
# ============================================================================


def test_test_id_format_non_parametrized(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC1 — non-parametrized test_id is the literal pytest nodeid:
    ``"<file>.py::test_name"``, no bracket suffix, no path mangling.

    Pytester's ``makepyfile`` (no path arg) writes to
    ``pytester.path / "test_<calling_test_name>.py"``, so the nodeid path
    component is the calling test function's name with ``.py`` appended.
    """
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_bar(): assert True")
    pytester.runpytest()

    records = _read_test_records(db)
    # Story 1.2 contract: passing test → exactly 2 records (started + passed).
    # Anchored explicitly so a future lifecycle-hook regression (extra emit,
    # missed emit) trips this assertion, not a downstream test (review patch P1).
    assert len(records) == 2, f"Story 1.2 contract: 2 records per passing test; got {len(records)}"
    test_ids = {json.loads(r["context"])["test_id"] for r in records}
    assert len(test_ids) == 1
    (tid,) = test_ids
    # Primary assertion: literal nodeid (locks "no rootdir prefix, forward slashes only")
    assert tid == "test_test_id_format_non_parametrized.py::test_bar", (
        f"expected literal pytester nodeid; got {tid!r}"
    )
    # Defensive: no bracket, no backslash
    assert "[" not in tid
    assert "\\" not in tid


def test_test_id_format_parametrized_simple(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC2, AC4 — parametrized variants get distinct, well-formed test_ids."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("n", [1, 2])
        def test_param(n):
            assert n in (1, 2)
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    # 2 variants x 2 records (started + passed) = 4
    assert len(records) == 4, f"expected 4 records, got {len(records)}"
    distinct_ids = {json.loads(r["context"])["test_id"] for r in records}
    assert len(distinct_ids) == 2, f"expected 2 distinct test_ids, got {distinct_ids}"
    assert any(tid.endswith("::test_param[1]") for tid in distinct_ids)
    assert any(tid.endswith("::test_param[2]") for tid in distinct_ids)
    # Per-variant record count: each variant must produce its own started+outcome
    # pair — anchors against partial-emit regressions where one variant emits
    # 3 records and another emits 1 (review patch P3).
    counts_by_id: dict[str, int] = {}
    for rec in records:
        tid = json.loads(rec["context"])["test_id"]
        counts_by_id[tid] = counts_by_id.get(tid, 0) + 1
    assert all(c == 2 for c in counts_by_id.values()), (
        f"each variant must produce exactly 2 records; got {counts_by_id}"
    )


def test_test_id_format_parametrized_multi_param(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC2 — multi-parameter parametrize uses dash-joined parametrize IDs."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("flag,n", [(True, 1), (False, 2)])
        def test_multi(flag, n):
            pass
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    # Anchor total: 2 variants x 2 records (started + passed) = 4. Catches
    # partial-emit regressions where uniqueness alone would silently pass
    # (review patch P2 — Story 1.4 CR; pattern from Story 1.3 P3/P4/P6).
    assert len(records) == 4, (
        f"expected 4 records (2 variants x 2 records each); got {len(records)}"
    )
    distinct_ids = {json.loads(r["context"])["test_id"] for r in records}
    assert len(distinct_ids) == 2
    assert any(tid.endswith("::test_multi[True-1]") for tid in distinct_ids)
    assert any(tid.endswith("::test_multi[False-2]") for tid in distinct_ids)


def test_test_id_format_parametrized_custom_ids(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC6 — custom ``ids=`` (list, multi-param, callable) all flow through verbatim."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("v", [1, 2], ids=["alpha", "beta"])
        def test_named(v):
            pass

        @pytest.mark.parametrize("a,b", [(1, 2), (3, 4)], ids=["first", "second"])
        def test_grouped(a, b):
            pass

        @pytest.mark.parametrize("x", [1, 2], ids=lambda v: f"id_{v}")
        def test_callable_ids(x):
            pass
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    # Total record count anchors the math: 3 functions x 2 variants x 2 records = 12.
    # Without this, an extra spurious emit or a record that happens to dedupe to
    # an existing test_id would silently pass the distinct-set check (review patch P4).
    assert len(records) == 12, (
        f"expected 12 records (3 functions x 2 variants x 2 records each); got {len(records)}"
    )
    distinct_ids = {json.loads(r["context"])["test_id"] for r in records}
    # 6 variants total → 6 distinct ids
    assert len(distinct_ids) == 6, f"expected 6 distinct ids, got {distinct_ids}"
    for suffix in (
        "::test_named[alpha]",
        "::test_named[beta]",
        "::test_grouped[first]",
        "::test_grouped[second]",
        "::test_callable_ids[id_1]",
        "::test_callable_ids[id_2]",
    ):
        assert any(tid.endswith(suffix) for tid in distinct_ids), (
            f"missing variant ending with {suffix!r}; got {distinct_ids}"
        )


def test_test_id_format_class_method(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC5 — class-method tests preserve the class segment in nodeid."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        class TestThing:
            def test_method(self):
                assert True
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    distinct_ids = {json.loads(r["context"])["test_id"] for r in records}
    assert len(distinct_ids) == 1
    (tid,) = distinct_ids
    assert tid.endswith("::TestThing::test_method"), f"expected class-method nodeid; got {tid!r}"
    # The endswith check above already verifies the class segment is present.
    # Earlier draft also asserted `tid.count("::") == 2` — dropped because it
    # adds brittleness on platforms or collectors where path components could
    # legally contain "::" (review patch P7).


def test_test_id_stable_across_runs(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC3 — same test source produces the SAME literal test_id values, every time.

    Pytest's nodeid format is deterministic by construction: given the same
    source file at the same path inside the same rootdir, every pytest run
    produces byte-identical nodeids. We lock that contract by asserting
    against the EXACT expected strings — if pytest ever changes its nodeid
    format (or our plugin starts post-processing it), this test trips.

    A two-process variant (running pytester twice and diffing) was tried
    and dropped: both invocations share the outer Python process, so what
    they actually exercise is intra-process re-collection — not "stability
    across separate sessions". Literal-equality against the documented
    nodeid form is the stronger guarantee.
    """
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import pytest

        def test_plain():
            pass

        @pytest.mark.parametrize("n", [1, 2])
        def test_p(n):
            pass
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    distinct_ids = sorted({json.loads(r["context"])["test_id"] for r in records})

    # Pytester writes the source file to `pytester.path / "test_<calling>.py"`
    # so the nodeid path component is the calling test function's name.
    expected = sorted(
        [
            "test_test_id_stable_across_runs.py::test_plain",
            "test_test_id_stable_across_runs.py::test_p[1]",
            "test_test_id_stable_across_runs.py::test_p[2]",
        ]
    )
    assert distinct_ids == expected, (
        f"test_id values must match the documented pytest nodeid form;\n"
        f"  expected: {expected}\n"
        f"  got:      {distinct_ids}"
    )


def test_test_id_unique_per_parametrize_variant(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC4 — N parametrize variants produce N distinct test_ids."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
        def test_many(n):
            pass
        """
    )
    pytester.runpytest()

    records = _read_test_records(db)
    # Anchor the total: 5 variants x 2 records each = 10. Catches partial-emit
    # regressions that uniqueness alone would miss (review patch P6).
    assert len(records) == 10, (
        f"expected 10 records (5 variants x 2 records each); got {len(records)}"
    )
    distinct_ids = {json.loads(r["context"])["test_id"] for r in records}
    assert len(distinct_ids) == 5, (
        f"expected 5 distinct test_ids (one per variant); got {distinct_ids}"
    )


class _FakeItem:
    """Minimal item-like object exposing only ``.nodeid`` for the unit test
    of ``_make_test_id``. The class-level ``nodeid: str`` annotation is
    documentation — Python doesn't enforce it without ``__slots__`` or
    ``@dataclass``, but it makes the structural shape readable to humans
    and to mypy (Story 1.3 review patch P5; refined in Story 1.4 review)."""

    nodeid: str

    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid


def test_make_test_id_helper_is_importable_and_returns_nodeid() -> None:
    """AC7 — ``_make_test_id`` is the single named entry point for FR55.

    Stories 1.4 / 1.9 / 4.3 will import this helper; lock the import path
    and behavior here so a future rename trips this test loudly.
    """
    from ulog.testing.pytest_plugin import _make_test_id

    fake = _FakeItem("tests/test_x.py::test_y[True-1]")
    # The strict pytest.Item typing is the documented contract; at runtime
    # the helper accepts any object with a `.nodeid: str` attribute.
    assert _make_test_id(fake) == "tests/test_x.py::test_y[True-1]"  # type: ignore[arg-type]

    plain = _FakeItem("tests/path.py::test_simple")
    assert _make_test_id(plain) == "tests/path.py::test_simple"  # type: ignore[arg-type]


# ============================================================================
# Story 1.4 — Bound-context propagation of test_id (FR59-61)
# ============================================================================
#
# Story 1.2 ships the bind/unbind machinery (`pytest_runtest_protocol`'s
# hookwrapper calls `ulog.bind(test_id=...)` before yield + `ulog.unbind(...)`
# in the finally block). The SQL handler's `_record_to_row` reads
# `dict(get_bound())` for every record. Story 1.4 verifies that propagation
# works end-to-end: APPLICATION records emitted from test bodies, fixtures
# (setup + teardown), and parametrized variants all inherit the right test_id;
# records emitted post-session don't carry a stale test_id.


def test_app_log_during_test_inherits_test_id(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC1, FR60 — `logging.getLogger("myapp").info(...)` during the test body
    produces a record whose `context.test_id` matches the test's nodeid."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        import logging

        log = logging.getLogger("myapp")

        def test_render():
            log.info("rendering rom")
    """)
    pytester.runpytest()

    app_records = _read_app_records(db, "myapp")
    assert len(app_records) == 1
    ctx = json.loads(app_records[0]["context"])
    # Anchor on the .py boundary so a future refactor that wraps this in a
    # class (which would prepend `::ClassName::` to the nodeid) trips loudly
    # rather than passing on the bare suffix match (review patch P1).
    assert ctx["test_id"].endswith(".py::test_render"), ctx["test_id"]
    assert app_records[0]["msg"] == "rendering rom"

    # Sanity-check: app record's context.test_id matches the value bound by the
    # plugin's protocol hookwrapper (visible in the plugin's own ulog.test
    # records). Both reads come from the same `_bound` ContextVar via
    # `get_bound()`, so this is a regression sentinel — catches any future
    # change where `_record_to_row` injects a different test_id source.
    plugin_records = _read_test_records(db)
    plugin_test_ids = {json.loads(r["context"])["test_id"] for r in plugin_records}
    assert ctx["test_id"] in plugin_test_ids


def test_app_log_in_two_tests_carries_each_tests_id(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC5 — two tests running sequentially: each app record's test_id matches
    its own emitting test, with no cross-contamination."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        import logging

        log = logging.getLogger("myapp")

        def test_alpha():
            log.info("from-alpha")

        def test_beta():
            log.info("from-beta")
    """)
    pytester.runpytest()

    app_records = _read_app_records(db, "myapp")
    assert len(app_records) == 2

    # Lookup by message — order-independent (the assertions don't care which
    # test ran first; only that each test's record carries its own test_id).
    # Review patch P7: corrected an earlier comment that erroneously claimed
    # this test "assumes test_alpha runs before test_beta".
    by_msg = {r["msg"]: json.loads(r["context"])["test_id"] for r in app_records}
    assert by_msg["from-alpha"].endswith("::test_alpha"), by_msg
    assert by_msg["from-beta"].endswith("::test_beta"), by_msg
    # Cross-contamination check: explicitly verify neither carries the other's id.
    # If `unbind` between tests regressed (e.g. became a no-op), test_beta's
    # bind would accumulate test_alpha's value — but since test_id is a single
    # string field, the LATER bind wins and `from-alpha` would carry test_beta's
    # id. Asserting the by_msg mapping above already catches that. The assertions
    # below make the contract explicit for future readers.
    assert "::test_beta" not in by_msg["from-alpha"]
    assert "::test_alpha" not in by_msg["from-beta"]


def test_app_log_in_parametrized_variants(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC6 — each parametrized variant's app records inherit the variant-specific
    test_id (e.g. `::test_p[1]` vs `::test_p[2]`)."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        import logging
        import pytest

        log = logging.getLogger("myapp")

        @pytest.mark.parametrize("n", [1, 2])
        def test_p(n):
            log.info(f"n={n}")
    """)
    pytester.runpytest()

    app_records = _read_app_records(db, "myapp")
    assert len(app_records) == 2

    by_msg = {r["msg"]: json.loads(r["context"])["test_id"] for r in app_records}
    assert by_msg["n=1"].endswith("::test_p[1]"), by_msg
    assert by_msg["n=2"].endswith("::test_p[2]"), by_msg


def test_fixture_setup_log_inherits_test_id(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC2, FR61 — a fixture's setup body emitting log.info(...) produces a
    record whose `context.test_id` matches the consuming test's nodeid."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        import logging
        import pytest

        log = logging.getLogger("myapp")

        @pytest.fixture
        def fx():
            log.info("fixture setup")
            return "ok"

        def test_uses_fx(fx):
            assert fx == "ok"
    """)
    pytester.runpytest()

    app_records = _read_app_records(db, "myapp")
    assert len(app_records) == 1
    assert app_records[0]["msg"] == "fixture setup"
    ctx = json.loads(app_records[0]["context"])
    assert ctx["test_id"].endswith("::test_uses_fx")


def test_fixture_teardown_log_inherits_test_id(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC3, FR61 — a yield-form fixture's post-yield teardown body emitting
    log.info(...) produces a record whose `context.test_id` matches the
    consuming test's nodeid (i.e., the bind window covers teardown)."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        import logging
        import pytest

        log = logging.getLogger("myapp")

        @pytest.fixture
        def fx():
            yield "ok"
            log.info("fixture teardown")

        def test_uses_fx(fx):
            assert fx == "ok"
    """)
    pytester.runpytest()

    app_records = _read_app_records(db, "myapp")
    assert len(app_records) == 1
    assert app_records[0]["msg"] == "fixture teardown"
    ctx = json.loads(app_records[0]["context"])
    assert ctx["test_id"].endswith("::test_uses_fx")


def test_class_scoped_fixture_propagation(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC7 — class-scoped fixture: setup record gets FIRST test's id (setup runs
    inside test_one's protocol bind window); teardown record gets LAST test's id
    (class-finalizer scheduled inside test_two's protocol bind window)."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        import logging
        import pytest

        log = logging.getLogger("myapp")

        class TestX:
            @pytest.fixture(scope="class")
            def fx(self):
                log.info("class-fx setup")
                yield
                log.info("class-fx teardown")

            def test_one(self, fx):
                log.info("body-one")

            def test_two(self, fx):
                log.info("body-two")
    """)
    pytester.runpytest()

    app_records = _read_app_records(db, "myapp")
    # 4 expected: class-fx setup + body-one + body-two + class-fx teardown
    assert len(app_records) == 4, f"got {[r['msg'] for r in app_records]}"

    # Records are read in insertion order. Whichever body runs FIRST is in
    # the slot right after setup; whichever runs LAST is in the slot right
    # before teardown. We derive "first" and "last" from actual order rather
    # than hard-coding `test_one`/`test_two` — this keeps the test stable
    # under pytest-randomly or any future plugin that shuffles intra-class
    # collection order (review patch P6).
    msgs = [r["msg"] for r in app_records]
    test_ids = [json.loads(r["context"])["test_id"] for r in app_records]
    diag = f"msgs={msgs!r} test_ids={test_ids!r}"

    assert msgs[0] == "class-fx setup", diag
    assert msgs[1].startswith("body-"), diag
    assert msgs[2].startswith("body-"), diag
    assert msgs[3] == "class-fx teardown", diag

    # The two body records carry their own item's id (AC1); they must differ.
    assert test_ids[1] != test_ids[2], diag

    # Class-fx setup carries the FIRST-running test's id (the item whose
    # protocol triggered the fixture's setup phase).
    assert test_ids[0] == test_ids[1], (
        f"AC7: class-fx setup must carry first-running test's id; {diag}"
    )
    # Class-fx teardown carries the LAST-running test's id (pytest schedules
    # the class finalizer inside the last item's protocol bind window).
    assert test_ids[3] == test_ids[2], (
        f"AC7: class-fx teardown must carry last-running test's id; {diag}"
    )

    # Sanity: both ids name methods of TestX (defensive against a future
    # refactor that produces unexpected nodeid forms).
    for tid in (test_ids[1], test_ids[2]):
        assert "::TestX::test_one" in tid or "::TestX::test_two" in tid, diag


def test_test_id_unbound_after_session(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC4, FR59 — a record emitted from `pytest_unconfigure` (post-session,
    outside any item's protocol bind window) does not carry test_id.

    pytester.makeconftest REPLACES the conftest, so this test inlines a
    complete custom conftest rather than trying to extend `_conftest_with_setup`.
    The standard helper closes its handlers from inside `pytest_unconfigure`
    BEFORE we'd want to emit, so we hand-roll the body to put the emit FIRST.
    """
    db = tmp_path / "logs.sqlite"
    posix_path = db.as_posix()
    # CRITICAL ORDERING: pytest_unconfigure must EMIT then CLOSE, not the
    # reverse. With sql_batch_size=1 the emit flushes immediately, but if a
    # future change reorders this body the test silently passes with zero
    # records and AC4 is no longer being verified. The
    # `assert len(app_records) == 1` below anchors that the emit happened.
    # `tryfirst=True` schedules our pytest_unconfigure BEFORE other plugins'
    # unconfigures, so a third-party plugin (e.g. pytest-cov) tearing down
    # logging via `logging.shutdown()` can't swallow our post-session emit
    # (review patch P8).
    pytester.makeconftest(f"""
import logging
import pytest
import ulog

def pytest_configure(config):
    ulog.setup(handlers=['sql'], sql_url='sqlite:///{posix_path}', sql_batch_size=1)

@pytest.hookimpl(tryfirst=True)
def pytest_unconfigure(config):
    # CRITICAL: emit FIRST, close SECOND. By this point each test's
    # pytest_runtest_protocol finally-block has already unbound test_id.
    logging.getLogger("myapp").info("post-session emit")
    for h in list(logging.getLogger().handlers):
        if getattr(h, '_ulog_managed', False):
            try:
                h.flush()
                h.close()
            except Exception:
                pass
            logging.getLogger().removeHandler(h)
""")
    pytester.makepyfile("def test_dummy(): assert True")
    pytester.runpytest()

    app_records = _read_app_records(db, "myapp")
    assert len(app_records) == 1, (
        f"AC4 anchor: post-session emit must produce exactly 1 record; got {len(app_records)}"
    )
    assert app_records[0]["msg"] == "post-session emit"

    # context may be None / SQL NULL / JSON "null" (empty bound dict per
    # sql.py:208 → `bound or None` → stored as NULL → re-read as either Python
    # None or JSON-loads-to-None) or a dict without test_id — every "absent"
    # form satisfies AC4 / FR59.
    raw_ctx = app_records[0]["context"]
    if raw_ctx is None:
        return  # SQL NULL → unbind worked
    parsed = json.loads(raw_ctx) if isinstance(raw_ctx, str) else raw_ctx
    if parsed is None:
        return  # JSON "null" → also unbind worked
    assert "test_id" not in parsed, (
        f"FR59: post-session emit must not carry test_id; got {parsed!r}"
    )


# ============================================================================
# Story 1.5 — Pytest CLI flags (FR67-69)
# ============================================================================
#
# Story 1.1 already registered --ulog-db / --ulog-disable / --ulog-summary in
# pytest_addoption. Story 1.2 already implements --ulog-disable's gate effect.
# Story 1.5 adds the production behavior:
#   * FR67: --ulog-db PATH triggers ulog.setup auto-call when no host setup;
#           does NOT override existing host setup.
#   * FR69: pytest_terminal_summary prints a one-line session summary.
#   * -q (verbose<0) suppresses the summary line.


def test_ulog_db_auto_configures_setup_when_host_unconfigured(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC1 / FR67 — `--ulog-db PATH` triggers auto-setup when no host conftest
    called ulog.setup. Records emitted by tests land in PATH (auto-setup wired
    up the SQL handler)."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_unconfigure_flush_only())
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest("--ulog-db", str(db))
    assert result.ret == 0

    records = _read_test_records(db)
    # If auto-setup didn't fire, no SQL handler would be attached and
    # records would be 0 — anchoring catches the regression loudly.
    assert len(records) == 2, (
        f"FR67: --ulog-db must auto-configure setup; got {len(records)} records"
    )
    assert records[0]["msg"] == "test started"
    assert records[1]["msg"] == "test passed"


def test_ulog_db_does_not_override_host_setup(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC2 / FR67 — when host conftest already configured ulog.setup,
    `--ulog-db PATH_B` does NOT redirect: records land where the host
    configured them, not at PATH_B."""
    host_db = tmp_path / "host.sqlite"
    cli_db = tmp_path / "cli.sqlite"
    pytester.makeconftest(_conftest_with_setup(host_db))
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest("--ulog-db", str(cli_db))
    assert result.ret == 0

    host_records = _read_test_records(host_db)
    assert len(host_records) == 2, "host setup must keep its destination"

    # cli_db either doesn't exist OR exists but is empty (no `logs` table
    # — _read_test_records' P5-style guard would handle that).
    cli_records = _read_test_records(cli_db) if cli_db.exists() else []
    assert cli_records == [], (
        f"AC2: --ulog-db must not redirect when host setup exists; got cli records: {cli_records}"
    )


def test_summary_line_default_on(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC4 / FR69 — `--ulog-summary` defaults to ON; one-line summary appears
    on session end with the 3-bucket counts."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        def test_a(): assert True
        def test_b(): assert True
        def test_c(): assert False
    """)
    result = pytester.runpytest()
    output = result.stdout.str() + result.stderr.str()
    # Tighten to the full literal ulog line — bare substrings like
    # "2 passed" / "1 failed" also appear in pytest's own summary, so a
    # regression that killed our line entirely would still pass them
    # (review patch P3). The full literal is unique to our hook.
    assert "ulog: 3 tests, 2 passed, 1 failed, 0 skipped" in output, output


def test_summary_line_includes_db_path_when_cli_passed(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC7 — `--ulog-db PATH` (no host setup → auto-setup fires) makes the
    summary line include `→ ulog-web PATH`. Records actually land at PATH
    so the suffix accurately points the user there."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_unconfigure_flush_only())
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest("--ulog-db", str(db))
    output = result.stdout.str() + result.stderr.str()
    assert "ulog: 1 tests, 1 passed" in output
    assert f"→ ulog-web {db} to triage" in output, output


def test_summary_line_omits_db_path_when_host_configured(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC7 inverse — when host configured setup AND `--ulog-db PATH_B` is
    also passed, records went to host's path (AC2). The summary line OMITS
    the `→ ulog-web` suffix to avoid misleading the user about where records
    actually landed."""
    host_db = tmp_path / "host.sqlite"
    cli_db = tmp_path / "cli.sqlite"
    pytester.makeconftest(_conftest_with_setup(host_db))
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest("--ulog-db", str(cli_db))
    output = result.stdout.str() + result.stderr.str()
    # Positive: the ulog summary line IS present (so we're testing real
    # suffix omission, not vacuous suppression of the entire line — review
    # patch P4).
    assert "ulog: 1 tests, 1 passed, 0 failed, 0 skipped" in output, output
    # Negative: NO ulog-web suffix — we don't know the host's path and
    # showing the CLI path would lie.
    assert "→ ulog-web" not in output, (
        f"AC7: must omit `→ ulog-web` when host configured (records went to "
        f"host path, not CLI path); got: {output!r}"
    )


def test_quiet_mode_suppresses_summary(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC5 / FR69 — `pytest -q` (verbose<0) suppresses the summary line."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest("-q")
    output = result.stdout.str() + result.stderr.str()
    assert "ulog:" not in output, f"`-q` must suppress summary line; got output: {output!r}"


def test_disabled_plugin_suppresses_summary(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC8 — `--ulog-disable` short-circuits the summary line via the gate."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest("--ulog-disable")
    output = result.stdout.str() + result.stderr.str()
    assert "ulog:" not in output


def test_summary_counts_match_outcomes(pytester: pytest.Pytester, tmp_path: Path) -> None:
    """AC6 — summary counts match the outcomes _emit_outcome_records produced
    (2 passed, 1 failed, 1 skipped → exact rendered counts)."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        import pytest
        def test_p1(): assert True
        def test_p2(): assert True
        def test_f(): assert False
        def test_s(): pytest.skip("not in scope")
    """)
    result = pytester.runpytest()
    output = result.stdout.str() + result.stderr.str()
    assert "ulog: 4 tests, 2 passed, 1 failed, 1 skipped" in output, output


def test_summary_errored_counts_as_failed_for_display(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC4 corollary / AC6 — fixture errors increment the internal `errored`
    counter but display under `failed` (PRD-v0.3 §2.1.6 shows 3 buckets,
    not 4). Verifies the errored→failed display collapse."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("""
        import pytest

        @pytest.fixture
        def boom():
            raise RuntimeError("setup explodes")

        def test_p(): assert True
        def test_e(boom): pass
    """)
    result = pytester.runpytest()
    output = result.stdout.str() + result.stderr.str()
    # 1 passed + 1 errored → displayed as "1 passed, 1 failed, 0 skipped"
    assert "ulog: 2 tests, 1 passed, 1 failed, 0 skipped" in output, output


# ============================================================================
# Story 1.10 — xdist + Windows + NFS edge cases (NFR-PORT-10)
# ============================================================================


def test_xdist_active_detects_worker_env(monkeypatch):
    """AC7 — `_xdist_active()` returns True when xdist env vars are set."""
    from ulog.testing.pytest_plugin import _xdist_active

    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.delenv("PYTEST_XDIST_TESTRUNUID", raising=False)
    assert _xdist_active() is False

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    assert _xdist_active() is True
    monkeypatch.delenv("PYTEST_XDIST_WORKER")

    monkeypatch.setenv("PYTEST_XDIST_TESTRUNUID", "abc123")
    assert _xdist_active() is True


def test_is_network_fs_returns_false_for_local_paths(tmp_path):
    """`_is_network_fs` returns False for clearly-local paths on Linux/macOS.
    Skipped on Windows where conservative fallback is the documented behavior."""
    from ulog.testing.pytest_plugin import _is_network_fs

    if sys.platform == "win32":
        pytest.skip("Windows path returns conservative True per AC4")
    assert _is_network_fs(str(tmp_path)) is False


def test_swap_sql_for_jsonl_replaces_handler(tmp_path, capsys):
    """AC1 / AC4 — `_swap_sql_for_jsonl` detaches the SQL handler and installs
    a JSONL handler at the same path stem; warning text appears on stderr."""
    import ulog
    from ulog.handlers.json_line import JSONLineHandler
    from ulog.handlers.sql import SQLHandler
    from ulog.testing.pytest_plugin import _swap_sql_for_jsonl

    db = tmp_path / "x.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    assert any(isinstance(h, SQLHandler) for h in logging.getLogger().handlers)

    _swap_sql_for_jsonl("test")

    # SQL handler detached, JSONL attached
    handlers = logging.getLogger().handlers
    assert not any(isinstance(h, SQLHandler) for h in handlers)
    assert any(isinstance(h, JSONLineHandler) for h in handlers)

    # JSONL path is at the same stem with `.jsonl` extension
    expected_jsonl = tmp_path / "x.jsonl"
    # The handler stores its target — verify by emitting a record and
    # confirming the file is created.
    log = ulog.get_logger("ulog.test")
    log.info("after swap")
    for h in logging.getLogger().handlers:
        if hasattr(h, "flush"):
            h.flush()
    assert expected_jsonl.exists(), f"expected JSONL at {expected_jsonl}"

    # Warning text on stderr
    captured = capsys.readouterr()
    assert "ulog: test" in captured.err
    assert "JSONL" in captured.err
    assert str(expected_jsonl) in captured.err


def test_pytest_configure_no_op_when_not_xdist(
    pytester: pytest.Pytester, tmp_path: Path, monkeypatch
):
    """AC3 — without xdist env vars, no swap occurs and no warning is emitted."""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.delenv("PYTEST_XDIST_TESTRUNUID", raising=False)

    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest()
    output = result.stdout.str() + result.stderr.str()
    # No xdist warning text should appear
    assert "xdist+" not in output, output
    assert "WAL mode" not in output, output


def test_apply_xdist_storage_strategy_disabled_plugin_no_op(monkeypatch):
    """AC5 — when the plugin gate is OFF, _apply_xdist_storage_strategy does
    nothing even with xdist active."""
    from ulog.testing.pytest_plugin import _apply_xdist_storage_strategy

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")

    # Build a minimal Config-like object with `_ulog_enabled=False`
    class FakeConfig:
        _ulog_enabled = False

    fake_config = FakeConfig()

    # Should not raise; nothing observable to assert beyond "no exception"
    _apply_xdist_storage_strategy(fake_config)  # type: ignore[arg-type]


def test_swap_sql_for_jsonl_preserves_record_schema(tmp_path):
    """AC6 — after the swap, records emitted via the JSONL handler have the
    same shape (logger / level / msg / context) as before."""
    import ulog
    from ulog.testing.pytest_plugin import _swap_sql_for_jsonl

    db = tmp_path / "x.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    _swap_sql_for_jsonl("test")

    log = ulog.get_logger("myapp")
    ulog.bind(test_id="t1")
    log.info("after swap", extra={"k": "v"})
    ulog.unbind("test_id")
    for h in logging.getLogger().handlers:
        if hasattr(h, "flush"):
            h.flush()

    jsonl_path = tmp_path / "x.jsonl"
    assert jsonl_path.exists()
    lines = jsonl_path.read_text().strip().splitlines()
    assert len(lines) >= 1
    record = json.loads(lines[-1])
    # Schema check: standard fields present. Note that the JSON formatter
    # MERGES bound contextvars at the TOP LEVEL of the record (not under a
    # "context" sub-key like the SQL handler), so `test_id` is checked
    # directly on the record root.
    assert record["logger"] == "myapp"
    assert record["level"] == "INFO"
    assert record["msg"] == "after swap"
    assert record.get("test_id") == "t1"


def test_pytest_configure_swaps_for_jsonl_on_xdist_nfs(
    pytester: pytest.Pytester, tmp_path: Path, monkeypatch
):
    """AC1 — xdist + simulated NFS detection → SQL→JSONL swap."""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    # Patch _is_network_fs to return True regardless of actual filesystem
    import ulog.testing.pytest_plugin as plugin_mod

    monkeypatch.setattr(plugin_mod, "_is_network_fs", lambda p: True)
    # On Windows, _apply_xdist_storage_strategy hits the win32 branch first
    # (before _is_network_fs is even called). Patch sys.platform too.
    monkeypatch.setattr(plugin_mod.sys, "platform", "linux")

    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest()
    output = result.stdout.str() + result.stderr.str()

    assert "xdist+NFS" in output, output
    # The JSONL file at the same stem should exist after the swap
    jsonl_path = tmp_path / "logs.jsonl"
    assert jsonl_path.exists(), f"expected JSONL fallback at {jsonl_path}"


def test_pytest_configure_enables_wal_on_xdist_local(
    pytester: pytest.Pytester, tmp_path: Path, monkeypatch
):
    """AC2 — xdist + local FS → PRAGMA journal_mode=WAL persists."""
    import sqlite3 as _sqlite

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    import ulog.testing.pytest_plugin as plugin_mod

    monkeypatch.setattr(plugin_mod, "_is_network_fs", lambda p: False)
    monkeypatch.setattr(plugin_mod.sys, "platform", "linux")  # avoid Windows branch

    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    # Emit at least one record so WAL is materialized on disk
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest()
    assert result.ret == 0
    assert db.exists(), "DB should exist after the test session"

    # Inspect journal_mode via a fresh sqlite3 connection
    conn = _sqlite.connect(str(db))
    try:
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal", f"expected wal mode; got {mode!r}"


def test_pytest_configure_falls_back_when_wal_fails(tmp_path, monkeypatch, capsys):
    """AC2 second clause — if PRAGMA journal_mode=WAL raises, the JSONL
    fallback fires with 'WAL mode unavailable' warning."""
    import ulog
    import ulog.testing.pytest_plugin as plugin_mod
    from ulog.handlers.sql import SQLHandler

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    monkeypatch.setattr(plugin_mod, "_is_network_fs", lambda p: False)
    monkeypatch.setattr(plugin_mod.sys, "platform", "linux")

    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)

    # Patch the SQL handler's engine.connect to raise
    sql_handler = next(h for h in logging.getLogger().handlers if isinstance(h, SQLHandler))
    original_engine = sql_handler._engine

    class FakeEngine:
        def connect(self):
            raise RuntimeError("simulated PRAGMA failure")

        # Provide dispose so close() doesn't crash later
        def dispose(self):
            original_engine.dispose()

    sql_handler._engine = FakeEngine()  # type: ignore[assignment]

    # Build a minimal Config-like object
    class FakeConfig:
        _ulog_enabled = True

    plugin_mod._apply_xdist_storage_strategy(FakeConfig())  # type: ignore[arg-type]

    captured = capsys.readouterr()
    assert "WAL mode unavailable" in captured.err, captured.err
    # JSONL fallback should be in place
    tmp_path / "logs.jsonl"
    # The file may not exist yet (no record emitted) but the handler IS attached
    from ulog.handlers.json_line import JSONLineHandler

    assert any(isinstance(h, JSONLineHandler) for h in logging.getLogger().handlers)
