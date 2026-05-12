"""Tests for `ulog._filter_dsl` — Story 4.4."""

from __future__ import annotations

import contextlib
import datetime
import logging
from pathlib import Path

import pytest

import ulog
from ulog._filter_dsl import FilterParseError, parse


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


# ---- tokenizer / parser smoke -------------------------------------------


def test_parses_simple_equality():
    expr = parse("level=ERROR")
    assert expr.to_predicate()({"level": "ERROR"}) is True
    assert expr.to_predicate()({"level": "INFO"}) is False


def test_parses_each_operator():
    cases = [
        ("level=ERROR", {"level": "ERROR"}, True),
        ("level!=ERROR", {"level": "INFO"}, True),
        ("line>10", {"line": 20}, True),
        ("line>=10", {"line": 10}, True),
        ("line<10", {"line": 5}, True),
        ("line<=10", {"line": 10}, True),
        ("msg~timeout", {"msg": "db timeout after 5s"}, True),
        ("msg~timeout", {"msg": "ok"}, False),
    ]
    for dsl, record, expected in cases:
        result = parse(dsl).to_predicate()(record)
        assert result is expected, f"{dsl!r} on {record!r}: expected {expected}, got {result}"


def test_quoted_strings_parse_value_literally():
    """Quotes let you put spaces, special chars in values."""
    p = parse('msg="db pool exhausted"').to_predicate()
    assert p({"msg": "db pool exhausted"}) is True
    assert p({"msg": "db pool"}) is False


def test_single_and_double_quotes_both_work():
    assert parse("msg='a b'").to_predicate()({"msg": "a b"}) is True
    assert parse('msg="a b"').to_predicate()({"msg": "a b"}) is True


def test_numeric_values():
    assert parse("line=42").to_predicate()({"line": 42}) is True
    assert parse("ratio=1.5").to_predicate()({"ratio": 1.5}) is True


# ---- precedence + parens (Gap G7) ---------------------------------------


def test_and_binds_tighter_than_or():
    """level=ERROR OR level=WARN AND service=payment
    must parse as `level=ERROR OR (level=WARN AND service=payment)`."""
    p = parse("level=ERROR OR level=WARN AND service=payment").to_predicate()
    assert p({"level": "ERROR", "service": "auth"}) is True  # ERROR alone
    assert p({"level": "WARN", "service": "payment"}) is True
    assert p({"level": "WARN", "service": "auth"}) is False  # WARN alone, wrong service
    assert p({"level": "INFO", "service": "payment"}) is False


def test_parentheses_override_precedence():
    p = parse("(level=ERROR OR level=WARN) AND service=payment").to_predicate()
    assert p({"level": "ERROR", "service": "payment"}) is True
    assert p({"level": "WARN", "service": "payment"}) is True
    assert p({"level": "ERROR", "service": "auth"}) is False


def test_case_insensitive_and_or():
    assert (
        parse("level=ERROR and msg=boom").to_predicate()({"level": "ERROR", "msg": "boom"}) is True
    )
    assert parse("level=ERROR or level=INFO").to_predicate()({"level": "INFO"}) is True


def test_whitespace_tolerant():
    a = parse("level=ERROR AND service=p")
    b = parse("level = ERROR  AND   service=p")
    assert a.to_predicate()({"level": "ERROR", "service": "p"}) is True
    assert b.to_predicate()({"level": "ERROR", "service": "p"}) is True


# ---- nested-key resolution ----------------------------------------------


def test_dotted_key_resolves_nested_context():
    p = parse("context.tenant_id=acme").to_predicate()
    assert p({"context": {"tenant_id": "acme"}}) is True
    assert p({"context": {"tenant_id": "other"}}) is False
    assert p({"context": {}}) is False
    assert p({}) is False


# ---- SQL compilation -----------------------------------------------------


def test_to_sql_uses_named_bind_params():
    clause, params = parse("level=ERROR").to_sql()
    assert "level = :p0" in clause
    assert params == {"p0": "ERROR"}


def test_to_sql_increments_param_names_across_compound():
    clause, params = parse("level=ERROR AND service=payment").to_sql()
    assert params == {"p0": "ERROR", "p1": "payment"}
    assert ":p0" in clause
    assert ":p1" in clause


def test_to_sql_never_interpolates_value_literally():
    """Injection-style value lands as a bind param, NEVER in clause text."""
    clause, params = parse('level="\'; DROP TABLE logs --"').to_sql()
    assert "DROP" not in clause
    assert params["p0"] == "'; DROP TABLE logs --"


# ---- regex ---------------------------------------------------------------


def test_regex_predicate():
    """Regex patterns with special chars (\\b, \\d, etc.) must be quoted."""
    p = parse(r'msg~"\bpayment\b"').to_predicate()
    assert p({"msg": "the payment failed"}) is True
    # `\b` is a word boundary — "payments" (trailing s) blocks the
    # second boundary → no match. This is correct stdlib re behaviour.
    assert p({"msg": "payments are slow"}) is False
    assert p({"msg": "no match"}) is False
    # Bareword regex (no special chars) works unquoted too.
    p2 = parse("msg~timeout").to_predicate()
    assert p2({"msg": "db timeout"}) is True


# ---- relative dates ------------------------------------------------------


def test_relative_date_compiles_to_datetime():
    expr = parse("ts>-30min")
    assert isinstance(expr.root.value, datetime.datetime)
    # And the compiled SQL has a bind param holding the datetime.
    _clause, params = expr.to_sql()
    assert isinstance(params["p0"], datetime.datetime)


# ---- injection protection ------------------------------------------------


def test_injection_with_semicolon_raises_parse_error():
    with pytest.raises(FilterParseError):
        parse("level=ERROR; DROP TABLE logs")


def test_value_with_quote_escaping_is_safe():
    """A value like `'x' OR '1'='1` is just a string — never broken
    out into SQL."""
    p = parse("msg=\"' OR '1'='1\"").to_predicate()
    assert p({"msg": "' OR '1'='1"}) is True
    assert p({"msg": "not it"}) is False


# ---- error paths ---------------------------------------------------------


def test_empty_string_raises():
    with pytest.raises(FilterParseError, match="empty"):
        parse("")


def test_whitespace_only_raises():
    with pytest.raises(FilterParseError, match="empty"):
        parse("   ")


def test_unbalanced_paren_raises():
    with pytest.raises(FilterParseError):
        parse("(level=ERROR")


def test_missing_value_raises():
    with pytest.raises(FilterParseError):
        parse("level=")


def test_trailing_garbage_raises():
    with pytest.raises(FilterParseError, match="unexpected"):
        parse("level=ERROR garbage")


# ---- replay integration --------------------------------------------------


def _seed_chain(tmp_path: Path, n: int = 5) -> Path:
    db = tmp_path / "dsl.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url=url, sql_batch_size=1)
    levels = ["INFO", "ERROR", "INFO", "WARNING", "ERROR"]
    for i in range(n):
        log = ulog.get_logger("svc" if i < 3 else "auth")
        getattr(log, levels[i].lower())("rec %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


def test_replay_with_where_dsl_filters_correctly(tmp_path):
    db = _seed_chain(tmp_path, n=5)
    msgs = []
    n = ulog.replay(db, where_dsl="level=ERROR", on=lambda r: msgs.append(r["msg"]))
    assert n == 2


def test_replay_with_where_dsl_mutex_with_where_raises(tmp_path):
    db = _seed_chain(tmp_path, n=1)
    with pytest.raises(ValueError, match="at most one"):
        ulog.replay(
            db,
            where="level='ERROR'",
            where_dsl="level=ERROR",
            on=lambda r: None,
        )


def test_replay_with_where_dsl_compound_filter(tmp_path):
    db = _seed_chain(tmp_path, n=5)
    seen = []
    n = ulog.replay(
        db,
        where_dsl="level=ERROR AND logger=auth",
        on=lambda r: seen.append(r["chain_pos"]),
    )
    # Records seeded: i=0..4 with levels INFO/ERROR/INFO/WARNING/ERROR
    # logger="svc" for i<3 else "auth". So (level=ERROR AND logger=auth)
    # matches only i=4 (chain_pos=5).
    assert n == 1
    assert seen == [5]
