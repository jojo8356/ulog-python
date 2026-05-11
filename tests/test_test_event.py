"""Tests for ulog.testing.test_event (Story 1.9 / PRD-v0.3 §5.2)."""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
from pathlib import Path

import pytest

import ulog
from ulog.testing import test_event


@pytest.fixture(autouse=True)
def _isolate():
    """Strip _ulog_managed handlers and clear bound context between tests
    (mirrors tests/test_setup.py and tests/test_web.py patterns).

    Clears bound state at SETUP too, so an OUTER pytest plugin run with
    `--ulog-db` (which binds test_id for each outer test via
    pytest_runtest_protocol) does not leak its bind into these tests'
    assertions on test_event scoping."""
    ulog.clear()
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


@pytest.fixture
def configured_db(tmp_path) -> Path:
    """Configure ulog with SQL handler at tmp_path / 'tev.sqlite' and
    return the DB path. `sql_batch_size=1` ensures records flush
    immediately for in-process test inspection."""
    db = tmp_path / "tev.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    return db


def _read_records(db: Path) -> list[dict]:
    """Read all records from the SQLite log DB in id (= insertion) order."""
    conn = sqlite3.connect(str(db))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM logs ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# ============================================================================
# AC1-AC6 — test_event lifecycle behavior
# ============================================================================


def test_test_event_explicit_outcome_emits_three_records(configured_db):
    """AC1 — explicit ev.outcome → started + app log + outcome (3 records,
    same shape as pytest plugin)."""
    log = ulog.get_logger("myapp")
    with test_event("custom_test_42") as ev:
        log.info("step 1")
        ev.outcome("passed", duration_s=0.42)
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    assert len(records) == 3, [r["msg"] for r in records]
    assert records[0]["msg"] == "test started"
    assert records[0]["logger"] == "ulog.test"
    assert records[1]["msg"] == "step 1"
    assert records[1]["logger"] == "myapp"
    assert records[2]["msg"] == "test passed"
    assert records[2]["logger"] == "ulog.test"

    # All carry the same test_id via Story 1.4 propagation
    for r in records:
        ctx = json.loads(r["context"])
        assert ctx["test_id"] == "custom_test_42", r

    # Outcome record's specific fields
    ctx_outcome = json.loads(records[2]["context"])
    assert ctx_outcome["outcome"] == "passed"
    assert ctx_outcome["duration_s"] == 0.42
    assert ctx_outcome["phase"] == "call"


def test_test_event_no_outcome_no_exception_auto_passed(configured_db):
    """AC2 — clean exit without ev.outcome → 2 records (started + auto-passed)
    with measured duration_s >= 0."""
    with test_event("happy_path"):
        pass  # no body, no explicit outcome
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    assert len(records) == 2
    assert records[0]["msg"] == "test started"
    assert records[1]["msg"] == "test passed"
    ctx = json.loads(records[1]["context"])
    assert ctx["outcome"] == "passed"
    assert ctx["phase"] == "call"
    # `time.perf_counter()` resolution can be ~16ms on Windows; >= 0 is the
    # only safe assertion across platforms (review patch: don't use > 0).
    assert ctx["duration_s"] >= 0.0


def test_test_event_exception_emits_errored_and_raises(configured_db):
    """AC3 — block raises ValueError → 3 records (started + errored + traceback)
    AND the exception propagates out of the context manager."""
    with pytest.raises(ValueError, match="boom"), test_event("oh_no"):
        raise ValueError("boom")
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    assert len(records) == 3, [r["msg"] for r in records]

    # Started + errored outcome
    assert records[0]["msg"] == "test started"
    assert records[1]["msg"] == "test errored"
    assert records[1]["level"] == "ERROR"
    ctx_outcome = json.loads(records[1]["context"])
    assert ctx_outcome["outcome"] == "errored"

    # Traceback ERROR record
    assert records[2]["level"] == "ERROR"
    assert "ValueError" in records[2]["msg"]
    ctx_tb = json.loads(records[2]["context"])
    assert ctx_tb["exc"]["type"] == "ValueError"
    assert ctx_tb["exc"]["msg"] == "boom"
    assert isinstance(ctx_tb["exc"]["tb"], list)
    assert len(ctx_tb["exc"]["tb"]) > 0
    # Each tb line is a single-line string (no embedded \n) — Story 1.9
    # flattens multi-line frame entries from traceback.format_exception
    for line in ctx_tb["exc"]["tb"]:
        assert "\n" not in line, f"tb line not flattened: {line!r}"


def test_test_event_explicit_outcome_short_circuits_auto_emit(configured_db):
    """AC4 — explicit ev.outcome wins; auto-emit does NOT fire on clean exit."""
    with test_event("explicit") as ev:
        ev.outcome("failed", duration_s=0.1)
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    # 2 records: started + the explicit failed outcome (no auto-passed)
    assert len(records) == 2, [r["msg"] for r in records]
    assert records[1]["msg"] == "test failed"
    ctx = json.loads(records[1]["context"])
    assert ctx["outcome"] == "failed"
    assert ctx["duration_s"] == 0.1


def test_test_event_supports_all_four_outcome_strings(configured_db):
    """AC5 — passed/failed/skipped/errored all round-trip through ev.outcome."""
    for outcome in ("passed", "failed", "skipped", "errored"):
        with test_event(f"t_{outcome}") as ev:
            ev.outcome(outcome, duration_s=0.01)
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    # 4 tests x 2 records (started + outcome) = 8
    assert len(records) == 8
    outcome_records = [
        r for r in records if r["msg"].startswith("test ") and r["msg"] != "test started"
    ]
    assert len(outcome_records) == 4
    seen = {json.loads(r["context"])["outcome"] for r in outcome_records}
    assert seen == {"passed", "failed", "skipped", "errored"}


def test_test_event_propagates_test_id_to_app_records(configured_db):
    """AC6 — app records emitted INSIDE the context inherit test_id; records
    AFTER the context exit do NOT (Story 1.4 contract verified for the
    programmatic API too)."""
    log = ulog.get_logger("myapp")
    with test_event("scope_test"):
        log.info("inside")
    log.info("outside")
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    inside_recs = [r for r in records if r["msg"] == "inside"]
    outside_recs = [r for r in records if r["msg"] == "outside"]
    assert len(inside_recs) == 1
    assert len(outside_recs) == 1

    inside_ctx = json.loads(inside_recs[0]["context"])
    assert inside_ctx.get("test_id") == "scope_test"

    # Tightened: collapse SQL NULL / JSON "null" / dict-without-key into
    # one boolean check (review patch P4) — no nested-pass branches that
    # could mask a regression.
    raw_outside = outside_recs[0]["context"]
    if raw_outside is None:
        outside_ctx = None
    else:
        parsed = json.loads(raw_outside) if isinstance(raw_outside, str) else raw_outside
        outside_ctx = parsed
    has_test_id_post_context = (
        outside_ctx is not None and isinstance(outside_ctx, dict) and "test_id" in outside_ctx
    )
    assert not has_test_id_post_context, (
        f"AC6: post-context emit must not carry test_id; got {outside_ctx!r}"
    )


def test_test_event_outcome_record_level_matches_outcome(configured_db):
    """AC5 corollary — failed/errored emit at ERROR level; passed/skipped at INFO
    (matches Story 1.2's level mapping)."""
    with test_event("t_pass") as ev:
        ev.outcome("passed", duration_s=0.01)
    with test_event("t_fail") as ev:
        ev.outcome("failed", duration_s=0.01)
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    by_msg = {r["msg"]: r["level"] for r in records}
    assert by_msg["test passed"] == "INFO"
    assert by_msg["test failed"] == "ERROR"


# ============================================================================
# AC7-AC8 — stable-signature stubs
# ============================================================================


def test_replay_records_importable_and_stub_raises():
    """AC7 — replay_records is importable but raises NotImplementedError
    when called (full impl in v0.5 / Story 4.9)."""
    from ulog.testing import replay_records

    assert callable(replay_records)
    # Match on "Story 4.9" — more stable than "v0.5" (versioning may evolve).
    with pytest.raises(NotImplementedError, match=r"Story 4\.9"):
        replay_records([])


def test_test_session_importable_and_constructible():
    """AC7 — TestSession is importable as a class and can be constructed
    (placeholder fields; v0.5 may extend)."""
    from ulog.testing import TestSession

    assert isinstance(TestSession, type)
    s = TestSession(name="x")
    assert s.name == "x"
    assert s.records == []


def test_testing_module_all_lists_three_exports():
    """AC8 — ulog.testing.__all__ contains exactly the three locked names."""
    import ulog.testing as t

    # Python's default sorted() is case-sensitive: uppercase 'T' < lowercase
    # 'r'/'t' by ASCII, so TestSession sorts first.
    assert sorted(t.__all__) == ["TestSession", "replay_records", "test_event"]


# ============================================================================
# Regression tests (review patches P5/P6/P8)
# ============================================================================


def test_test_event_explicit_outcome_then_exception_no_double_outcome(configured_db):
    """AC4 §2 (review patch P5) — when the user calls ev.outcome() AND the
    block then raises, the explicit outcome wins (no auto-`errored` record)
    AND the traceback ERROR is still emitted. Total: started + explicit
    outcome + traceback ERROR = 3 records."""
    with pytest.raises(ValueError, match="boom"), test_event("explicit_then_raise") as ev:
        ev.outcome("passed", duration_s=0.05)
        raise ValueError("boom")
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    assert len(records) == 3, [r["msg"] for r in records]
    assert records[0]["msg"] == "test started"
    # Explicit user-emitted outcome (passed, INFO) — NOT errored
    assert records[1]["msg"] == "test passed"
    assert records[1]["level"] == "INFO"
    # Traceback ERROR record always emitted on exception
    assert records[2]["level"] == "ERROR"
    ctx_tb = json.loads(records[2]["context"])
    assert ctx_tb["exc"]["type"] == "ValueError"


def test_test_event_nested_blocks_restore_outer_test_id(configured_db):
    """Review patch P6 — nested test_event blocks correctly restore the
    outer test_id on inner exit (uses ulog.context() / ContextVar token,
    not bind/unbind which would destroy the outer key)."""
    log = ulog.get_logger("myapp")
    with test_event("outer"):
        log.info("in outer before inner")
        with test_event("inner"):
            log.info("in inner")
        # AFTER inner exits, the OUTER test_id should be restored
        log.info("in outer after inner")
    log.info("after both")
    for h in logging.getLogger().handlers:
        h.flush()

    records = _read_records(configured_db)
    by_msg = {}
    for r in records:
        ctx_raw = r["context"]
        if ctx_raw is None:
            ctx = None
        else:
            ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
        by_msg[r["msg"]] = ctx

    # The two outer-scope app records carry "outer"
    assert by_msg["in outer before inner"]["test_id"] == "outer"
    assert by_msg["in outer after inner"]["test_id"] == "outer", (
        f"AC review patch P6: outer test_id must be restored after inner exit; "
        f"got {by_msg['in outer after inner']!r}"
    )

    # The inner-scope app record carries "inner"
    assert by_msg["in inner"]["test_id"] == "inner"

    # The post-both app record carries no test_id
    after = by_msg["after both"]
    has_tid = after is not None and isinstance(after, dict) and "test_id" in after
    assert not has_tid, f"post-context emit must not carry test_id; got {after!r}"


def test_test_event_empty_name_raises(configured_db):
    """Review patch P8 — empty test_id is rejected at entry (rather than
    storing a meaningless empty-string value in records)."""
    with pytest.raises(ValueError, match="non-empty"), test_event(""):
        pass
