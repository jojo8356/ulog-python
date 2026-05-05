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


def test_gate_on_with_ulog_db(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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


def test_ulog_disable_overrides(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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
        cur = conn.execute(
            "SELECT * FROM logs WHERE logger='ulog.test' ORDER BY id ASC"
        )
        return [dict(row) for row in cur.fetchall()]
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


def test_passing_test_emits_two_records(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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


def test_failing_test_emits_three_records(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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


def test_outcome_record_has_phase_field(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC3 — outcome record always carries context.phase."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    pytester.runpytest()

    records = _read_test_records(db)
    ctx = json.loads(records[1]["context"])
    assert "phase" in ctx
    assert ctx["phase"] in ("setup", "call", "teardown")


def test_teardown_failure_separate_record(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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
    assert ctx_outcome["outcome"] == "passed", (
        "teardown failure must not flip body outcome (AC4)"
    )
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


def test_records_carry_test_id(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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


def test_records_use_ulog_test_logger(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
    """AC8 — all plugin records use logger='ulog.test'."""
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(_conftest_with_setup(db))
    pytester.makepyfile("def test_pass(): assert True")
    pytester.runpytest()

    records = _read_test_records(db)
    assert len(records) == 2  # passing test → exactly started + outcome
    for rec in records:
        assert rec["logger"] == "ulog.test"


def test_setup_failure_emits_errored(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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


def test_duration_reflects_sleep(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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


def test_disabled_plugin_emits_nothing(
    pytester: pytest.Pytester, tmp_path: Path
) -> None:
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
    assert records == [], (
        f"--ulog-disable must suppress all ulog.test records; got {records}"
    )
