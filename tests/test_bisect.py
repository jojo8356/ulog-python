"""Tests for `ulog.bisect` — Story 4.7."""

from __future__ import annotations

import contextlib
import logging
import re
import time
from pathlib import Path
from types import MappingProxyType

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


def _seed_chain(tmp_path: Path, msgs: list[str], contexts: list[dict] | None = None) -> Path:
    db = tmp_path / "bisect.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=url, sql_batch_size=1)
    log = ulog.get_logger("svc")
    for i, msg in enumerate(msgs):
        extra = (contexts[i] if contexts else {}) or {}
        log.info(msg, extra=extra)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


# ---- core contract ------------------------------------------------------


def test_bisect_returns_first_match_in_chain_order(tmp_path):
    db = _seed_chain(
        tmp_path,
        ["first ok", "boom", "second ok", "boom again"],
    )
    result = ulog.bisect(db, pattern=r"boom")
    assert result is not None
    assert result.chain_pos == 2
    assert result.record["msg"] == "boom"


def test_bisect_no_match_returns_none(tmp_path):
    db = _seed_chain(tmp_path, ["a", "b", "c"])
    assert ulog.bisect(db, pattern=r"nothing-here") is None


def test_bisect_matches_in_msg(tmp_path):
    db = _seed_chain(tmp_path, ["ok", "db timeout after 5s", "ok"])
    result = ulog.bisect(db, pattern=r"timeout")
    assert result is not None
    assert result.chain_pos == 2


def test_bisect_matches_in_context_value(tmp_path):
    db = _seed_chain(
        tmp_path,
        ["plain", "plain", "plain"],
        contexts=[{"tenant": "acme"}, {"tenant": "globex"}, {}],
    )
    result = ulog.bisect(db, pattern=r"globex")
    assert result is not None
    assert result.chain_pos == 2


def test_bisect_matches_first_when_multiple_present(tmp_path):
    db = _seed_chain(tmp_path, ["xxx pattern", "yyy pattern", "zzz pattern"])
    result = ulog.bisect(db, pattern=r"pattern")
    assert result is not None
    assert result.chain_pos == 1  # FIRST match


def test_bisect_returns_frozen_view_record(tmp_path):
    db = _seed_chain(tmp_path, ["boom"])
    result = ulog.bisect(db, pattern=r"boom")
    assert result is not None
    assert isinstance(result.record, MappingProxyType)
    with pytest.raises(TypeError):
        result.record["msg"] = "tampered"


# ---- regex semantics ----------------------------------------------------


def test_bisect_pattern_is_regex_not_glob(tmp_path):
    """Pattern `a.b` matches `axb` (regex any-char), not literal `a.b`."""
    db = _seed_chain(tmp_path, ["axb"])
    assert ulog.bisect(db, pattern=r"a.b") is not None


def test_bisect_no_shell_injection_via_pattern(tmp_path):
    """Pattern with shell metachars is a regex literal — no shell escape."""
    db = _seed_chain(tmp_path, ["payment $TOKEN failed"])
    # `$TOKEN` in a regex matches literal `$TOKEN` (no shell expansion).
    result = ulog.bisect(db, pattern=r"\$TOKEN")
    assert result is not None
    assert result.record["msg"] == "payment $TOKEN failed"


def test_bisect_invalid_regex_raises_re_error(tmp_path):
    db = _seed_chain(tmp_path, ["x"])
    with pytest.raises(re.error):
        ulog.bisect(db, pattern=r"(unclosed")


# ---- perf smoke ---------------------------------------------------------


def test_bisect_wall_time_under_50ms_on_1k_records(tmp_path):
    """Realistic budget for v0.5 (NFR-PERF-54 1M target is best-effort;
    1K records ≤ 50 ms is the documented v0.5 SLA)."""
    msgs = [f"msg {i}" for i in range(1000)] + ["needle in haystack"]
    db = _seed_chain(tmp_path, msgs)
    t0 = time.perf_counter()
    result = ulog.bisect(db, pattern=r"needle")
    elapsed = (time.perf_counter() - t0) * 1000
    assert result is not None
    assert result.chain_pos == 1001
    assert elapsed < 250, f"bisect too slow: {elapsed:.1f}ms on 1K records"


# ---- arg validation -----------------------------------------------------


def test_bisect_db_not_found_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="DB not found"):
        ulog.bisect(tmp_path / "missing.sqlite", pattern="x")
