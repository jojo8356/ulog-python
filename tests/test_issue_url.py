"""Tests for the issue-template URL builder (Story 6.3 / FR111, NFR-SEC-51, G3)."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pytest

import ulog
from ulog._issue_template import (
    get_issue_template_url,
    render_issue_url,
    set_issue_template_url,
)


@pytest.fixture(autouse=True)
def _isolate():
    set_issue_template_url(None)
    ulog.clear()
    yield
    set_issue_template_url(None)
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


def test_setup_stores_issue_template_url():
    ulog.setup(issue_template_url="https://example.com/new?title={msg}")
    assert get_issue_template_url() == "https://example.com/new?title={msg}"


def test_render_encodes_spaces_and_quotes():
    url = render_issue_url(
        "https://e.x/new?t={msg}&l={level}",
        {"msg": 'oops "boom" & bang', "level": "ERROR"},
    )
    # Space → %20, quote → %22, ampersand → %26.
    assert "%20" in url
    assert "%22" in url
    assert "%26" in url
    # Unencoded `&` only as the original query separator.
    assert url.count("&") == 1


def test_render_unknown_placeholder_kept_intact():
    url = render_issue_url(
        "https://e.x/new?t={msg}&xxx={unknown_thing}",
        {"msg": "hi"},
    )
    assert "{unknown_thing}" in url


def test_render_missing_known_key_becomes_empty():
    url = render_issue_url(
        "https://e.x/new?t={msg}&svc={service}",
        {"msg": "hi"},
    )
    assert url == "https://e.x/new?t=hi&svc="


def test_render_body_serialized_as_json():
    url = render_issue_url(
        "https://e.x/new?body={body}",
        {"body": [{"chain_pos": 1, "msg": "a"}]},
    )
    # %22 is `"`, %3A is `:` — JSON encoded then URL-encoded.
    assert "%22chain_pos%22" in url
    assert "%22msg%22" in url


def test_body_window_picks_5_records_around_target(tmp_path: Path):
    """Story 6.3 / Gap G3 — symmetric window of 2 before + target + 2 after."""
    db = tmp_path / "w.sqlite"
    ulog.setup(
        integrity="hash-chain", handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1
    )
    for i in range(10):
        ulog.get_logger().info("rec %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)

    from ulog.web.viewer.adapters import SQLiteAdapter

    a = SQLiteAdapter(db)
    win = a.body_window(target_chain_pos=5)
    assert [r.chain_pos for r in win] == [3, 4, 5, 6, 7]


def test_body_window_shrinks_at_chain_start(tmp_path: Path):
    """At chain_pos=1, only the target + 2 after exist (no before)."""
    db = tmp_path / "w2.sqlite"
    ulog.setup(
        integrity="hash-chain", handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1
    )
    for i in range(5):
        ulog.get_logger().info("rec %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)

    from ulog.web.viewer.adapters import SQLiteAdapter

    a = SQLiteAdapter(db)
    win = a.body_window(target_chain_pos=1)
    assert [r.chain_pos for r in win] == [1, 2, 3]


def test_set_issue_template_url_rejects_non_str():
    with pytest.raises(TypeError):
        set_issue_template_url(42)  # type: ignore[arg-type]


def test_get_issue_template_url_default_is_none():
    assert get_issue_template_url() is None
