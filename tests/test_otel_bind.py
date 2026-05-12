"""Tests for OTel auto-bind (Story 6.1).

# noqa: SIM112 — W3C Trace Context spec specifies LOWERCASE `traceparent`;
# the lib reads both cases. Tests intentionally probe both lowercase + uppercase.
"""

# ruff: noqa: SIM112

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path

import pytest

import ulog
from ulog._otel import (
    clear_trace_context,
    current_trace_context,
    set_trace_context,
)


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    clear_trace_context()
    # Snapshot + clear env for clean isolation.
    saved = {k: os.environ.pop(k, None) for k in ("traceparent", "TRACEPARENT")}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    clear_trace_context()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()


# ---- contextvar / env resolution ----------------------------------------


def test_no_otel_context_returns_none():
    assert current_trace_context() is None


def test_contextvar_set_returns_dict():
    set_trace_context("abc123", "def456")
    assert current_trace_context() == {"trace_id": "abc123", "span_id": "def456"}


def test_traceparent_env_parsed_when_contextvar_unset():
    os.environ["traceparent"] = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    ctx = current_trace_context()
    assert ctx is not None
    assert ctx["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert ctx["span_id"] == "00f067aa0ba902b7"


def test_uppercase_traceparent_env_also_works():
    os.environ["TRACEPARENT"] = "00-abcdef0123456789abcdef0123456789-fedcba9876543210-00"
    ctx = current_trace_context()
    assert ctx is not None
    assert ctx["trace_id"] == "abcdef0123456789abcdef0123456789"


def test_contextvar_wins_over_traceparent():
    """Contextvar (user-set) takes precedence over the env."""
    os.environ["traceparent"] = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    set_trace_context("from-contextvar", "span-cv")
    ctx = current_trace_context()
    assert ctx == {"trace_id": "from-contextvar", "span_id": "span-cv"}


def test_invalid_traceparent_silent_no_op():
    """Malformed traceparent → no warning, return None."""
    os.environ["traceparent"] = "garbage-not-a-real-traceparent"
    assert current_trace_context() is None


def test_empty_traceparent_returns_none():
    os.environ["traceparent"] = ""
    assert current_trace_context() is None


# ---- emit-side attachment -----------------------------------------------


def test_record_emitted_with_otel_context_includes_trace_id(tmp_path):
    from sqlalchemy import create_engine, text

    db = tmp_path / "otel.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    set_trace_context("aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb")
    ulog.get_logger().info("with otel")
    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        ctx_str = conn.execute(text("SELECT context FROM logs WHERE msg='with otel'")).scalar()
    engine.dispose()
    ctx = json.loads(ctx_str) if isinstance(ctx_str, str) else ctx_str
    assert ctx is not None
    assert ctx["trace_id"] == "aaaaaaaaaaaaaaaa"
    assert ctx["span_id"] == "bbbbbbbbbbbbbbbb"


def test_record_emitted_without_otel_context_has_no_trace_id(tmp_path):
    from sqlalchemy import create_engine, text

    db = tmp_path / "plain.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    ulog.get_logger().info("plain")
    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        ctx_raw = conn.execute(text("SELECT context FROM logs WHERE msg='plain'")).scalar()
    engine.dispose()
    if ctx_raw is None:
        return  # NULL context → no trace_id (correct)
    ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
    assert ctx is None or "trace_id" not in ctx


def test_user_bind_overrides_otel_trace_id(tmp_path):
    """A `ulog.bind(trace_id='manual')` call wins over the auto-binder."""
    from sqlalchemy import create_engine, text

    db = tmp_path / "override.sqlite"
    url = f"sqlite:///{db}"
    ulog.setup(handlers=["sql"], sql_url=url, sql_batch_size=1)
    set_trace_context("auto-bound", "auto-span")
    ulog.bind(trace_id="manual-override")
    ulog.get_logger().info("override")
    for h in logging.getLogger().handlers:
        h.flush()

    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        ctx_raw = conn.execute(text("SELECT context FROM logs WHERE msg='override'")).scalar()
    engine.dispose()
    ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
    assert ctx["trace_id"] == "manual-override"
    # span_id still auto-bound (only trace_id was manually overridden).
    assert ctx["span_id"] == "auto-span"


# ---- NFR-DEP-50 grep regression -----------------------------------------


def test_help_does_not_mention_otel():
    """Story 6.10 — `ulog --help` doesn't mention OTel/opentelemetry
    anywhere (the auto-bind is invisible when no OTel context exists)."""
    import io
    from contextlib import redirect_stdout

    from ulog._cli import main

    buf = io.StringIO()
    with contextlib.suppress(SystemExit), redirect_stdout(buf):
        main(["--help"])
    out = buf.getvalue().lower()
    assert "otel" not in out
    assert "opentelemetry" not in out


def test_no_opentelemetry_import_anywhere():
    """ULog must NEVER `import opentelemetry`. Stdlib only.

    Greps only actual code lines (leading whitespace + `import` or
    `from` statement) — not docstring mentions.
    """
    import subprocess

    ulog_dir = Path(__file__).parent.parent / "ulog"
    result = subprocess.run(
        [
            "grep",
            "-rE",
            "--include=*.py",
            r"^\s*(import opentelemetry|from opentelemetry)",
            str(ulog_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"FOUND opentelemetry import — NFR-DEP-50 violated:\n{result.stdout}"
    )
