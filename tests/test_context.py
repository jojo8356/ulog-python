"""Tests for ulog.bind / context / unbind / clear (FR4, FR5)."""
from __future__ import annotations

import io
import json
import logging

import pytest

import ulog


@pytest.fixture(autouse=True)
def _isolate():
    """Clear bound state at SETUP and teardown.

    The setup-side clear is required so an OUTER pytest run with
    `--ulog-db` (which activates the ulog plugin and binds
    test_id=<nodeid> for each test via pytest_runtest_protocol) does
    not leak that bind into assertions on get_bound() shape.
    """
    ulog.clear()
    yield
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            logging.getLogger().removeHandler(h)


def test_bind_then_clear():
    ulog.bind(a=1, b=2)
    assert ulog.get_bound() == {"a": 1, "b": 2}
    ulog.clear()
    assert ulog.get_bound() == {}


def test_bind_merges_not_replaces():
    ulog.bind(a=1)
    ulog.bind(b=2)
    assert ulog.get_bound() == {"a": 1, "b": 2}


def test_bind_overwrites_existing_keys():
    ulog.bind(a=1)
    ulog.bind(a=999)
    assert ulog.get_bound() == {"a": 999}


def test_unbind_removes_keys():
    ulog.bind(a=1, b=2, c=3)
    ulog.unbind("a", "c")
    assert ulog.get_bound() == {"b": 2}


def test_unbind_missing_keys_is_noop():
    ulog.bind(a=1)
    ulog.unbind("nosuchkey")
    assert ulog.get_bound() == {"a": 1}


def test_context_block_scoped():
    with ulog.context(rom="alter_ego"):
        assert ulog.get_bound() == {"rom": "alter_ego"}
    assert ulog.get_bound() == {}


def test_context_restores_on_exception():
    try:
        with ulog.context(x=1):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert ulog.get_bound() == {}


def test_context_nests_correctly():
    ulog.bind(outer=1)
    with ulog.context(inner=2):
        assert ulog.get_bound() == {"outer": 1, "inner": 2}
    assert ulog.get_bound() == {"outer": 1}
    ulog.clear()


def test_get_bound_returns_a_copy():
    """Mutating the returned dict must not affect the bound state."""
    ulog.bind(a=1)
    snapshot = ulog.get_bound()
    snapshot["a"] = 999
    assert ulog.get_bound() == {"a": 1}


def test_bound_fields_appear_in_json_output():
    sink = io.StringIO()
    ulog.setup(format="json", stream=sink, color="never")
    with ulog.context(request_id="abc-123"):
        ulog.get_logger().info("step")
    payload = json.loads(sink.getvalue().strip())
    assert payload["request_id"] == "abc-123"
