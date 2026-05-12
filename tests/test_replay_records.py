"""Tests for `ulog.testing.replay_records` — Story 4.9."""

from __future__ import annotations

import contextlib
import logging

import pytest

import ulog
from ulog.testing import CapturedRecord, ReplaySession, replay_records


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


def _records():
    return [
        {
            "level": "ERROR",
            "logger": "svc.checkout",
            "msg": "boom",
            "context": {"db_timeout": True, "tenant": "acme"},
        },
        {
            "level": "INFO",
            "logger": "svc.checkout",
            "msg": "ok",
            "context": {"tenant": "acme"},
        },
    ]


# ---- contextvar plumbing -------------------------------------------------


def test_replay_records_sets_is_replaying_inside_body():
    with replay_records(_records()):
        assert ulog.is_replaying() is True


def test_replay_records_resets_after_body():
    with replay_records(_records()):
        pass
    assert ulog.is_replaying() is False


def test_replay_records_resets_on_exception():
    with pytest.raises(RuntimeError, match="boom"), replay_records(_records()):
        raise RuntimeError("boom")
    assert ulog.is_replaying() is False


# ---- emission through the pipeline --------------------------------------


def test_replay_records_emits_each_record_via_logging_pipeline(tmp_path, caplog):
    """Stream handler / caplog should see N emissions."""
    with caplog.at_level(logging.INFO), replay_records(_records()):
        pass
    assert len(caplog.records) == 2
    assert caplog.records[0].levelname == "ERROR"
    assert caplog.records[0].getMessage() == "boom"
    assert caplog.records[1].levelname == "INFO"


def test_emitted_records_land_with_is_replay_1_in_sql_handler(tmp_path):
    """SQLHandler stamps is_replay=1 because _REPLAY_ACTIVE is True
    during the body (Story 4.2 wiring)."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "rec.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)

    with replay_records(_records()) as session:
        assert ulog.is_replaying()
        assert len(session.captured) == 2

    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT msg, is_replay FROM logs ORDER BY id")).all()
    engine.dispose()
    assert rows == [("boom", 1), ("ok", 1)]


# ---- session.matches contract -------------------------------------------


def test_session_matches_returns_true_when_any_record_matches():
    with replay_records(_records()) as session:
        pass
    assert session.matches(lambda r: r["level"] == "ERROR") is True
    assert session.matches(lambda r: r["msg"] == "ok") is True


def test_session_matches_returns_false_when_none_match():
    with replay_records(_records()) as session:
        pass
    assert session.matches(lambda r: r["level"] == "CRITICAL") is False


def test_session_matches_uses_extras_alias_for_context():
    """AC4 literal: `r.extras.get('db_timeout')` works as documented."""
    with replay_records(_records()) as session:
        pass
    assert session.matches(lambda r: r.extras.get("db_timeout")) is True
    assert session.matches(lambda r: r.extras.get("not_a_real_key")) is False


def test_session_captured_is_frozen_view():
    """Each captured record is a frozen view; mutation raises."""
    with replay_records(_records()) as session:
        pass
    assert isinstance(session.captured, tuple)
    assert all(isinstance(r, CapturedRecord) for r in session.captured)
    with pytest.raises(TypeError):
        session.captured[0]["msg"] = "tampered"  # type: ignore[index]


# ---- edge cases ----------------------------------------------------------


def test_replay_records_with_empty_list_yields_session_with_no_captures():
    with replay_records([]) as session:
        assert session.captured == ()
        assert session.matches(lambda r: True) is False


def test_replay_records_stub_no_longer_raises():
    """Regression on the v0.3 stub: replay_records used to raise
    NotImplementedError. Story 4.9 replaced it with the real impl."""
    # Should not raise.
    with replay_records([{"level": "INFO", "logger": "x", "msg": "y"}]) as session:
        assert isinstance(session, ReplaySession)


def test_replay_records_with_missing_keys_uses_defaults():
    """Records with no `level` / `logger` / `msg` fall back to safe defaults."""
    minimal = [{"msg": "just a msg"}, {}]
    with replay_records(minimal) as session:
        assert len(session.captured) == 2
    # No crash.
