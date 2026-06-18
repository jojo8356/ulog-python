"""Tests for `ulog tail` (live follow CLI)."""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from pathlib import Path

import pytest

import ulog
from ulog._cli import main as cli_main


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


def _seed(tmp_path: Path, n: int = 3) -> Path:
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("svc")
    for i in range(n):
        log.info("rec %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    return db


def test_tail_missing_db_exits_2(tmp_path):
    rc = cli_main(["tail", "--db", str(tmp_path / "missing.sqlite")])
    assert rc == 2


def test_tail_invalid_filter_exits_2(tmp_path):
    db = _seed(tmp_path)
    rc = cli_main(["tail", "--db", str(db), "--filter", "level=", "--interval", "100"])
    assert rc == 2


def _run_tail_in_thread(args: list[str], stop_after_ms: int = 800) -> threading.Thread:
    """Run cli_main in a thread, then SIGINT it to mimic Ctrl-C."""
    import signal

    def _target():
        with contextlib.suppress(KeyboardInterrupt):
            cli_main(args)

    t = threading.Thread(target=_target, daemon=True)
    t.start()

    def _stop():
        time.sleep(stop_after_ms / 1000.0)
        # Send SIGINT to current process — Python wraps it as KeyboardInterrupt.
        import os as _os

        _os.kill(_os.getpid(), signal.SIGINT)

    threading.Thread(target=_stop, daemon=True).start()
    return t


def test_tail_minus_n_emits_last_lines(tmp_path, capsys):
    """--lines N prints the last N records before going live."""
    db = _seed(tmp_path, n=5)
    # Bypass the polling loop by using a tight interval + capture stdout.
    # Since the loop runs indefinitely, signal-based stop is needed —
    # but for `-n` we can just check it prints the seeded ones at start.
    # Use a short interval so the first iteration runs quickly.
    import signal as _signal

    def _abort_soon():
        time.sleep(0.4)
        import os as _os

        _os.kill(_os.getpid(), _signal.SIGINT)

    threading.Thread(target=_abort_soon, daemon=True).start()
    with contextlib.suppress(KeyboardInterrupt):
        cli_main(["tail", "--db", str(db), "-n", "2", "--interval", "100"])
    out = capsys.readouterr().out
    # Last 2 records should be printed: "rec 3" and "rec 4".
    assert "rec 3" in out
    assert "rec 4" in out


def test_tail_since_start_emits_all_existing(tmp_path, capsys):
    """--since-start prints every existing record before going live."""
    db = _seed(tmp_path, n=3)
    import signal as _signal

    def _abort_soon():
        time.sleep(0.4)
        import os as _os

        _os.kill(_os.getpid(), _signal.SIGINT)

    threading.Thread(target=_abort_soon, daemon=True).start()
    with contextlib.suppress(KeyboardInterrupt):
        cli_main(["tail", "--db", str(db), "--since-start", "--interval", "100"])
    out = capsys.readouterr().out
    for i in range(3):
        assert f"rec {i}" in out


def test_tail_levels_filter(tmp_path, capsys):
    """--levels ERROR keeps only ERROR records."""
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("svc")
    log.info("info one")
    log.error("error one")
    log.info("info two")
    for h in logging.getLogger().handlers:
        h.flush()

    import signal as _signal

    def _abort_soon():
        time.sleep(0.4)
        import os as _os

        _os.kill(_os.getpid(), _signal.SIGINT)

    threading.Thread(target=_abort_soon, daemon=True).start()
    with contextlib.suppress(KeyboardInterrupt):
        cli_main(
            ["tail", "--db", str(db), "--since-start", "--levels", "ERROR", "--interval", "100"]
        )
    out = capsys.readouterr().out
    assert "error one" in out
    assert "info one" not in out
    assert "info two" not in out


def test_tail_format_qlnes_style(tmp_path, capsys):
    """INFO records emit bare; ERROR records prefixed."""
    db = tmp_path / "logs.sqlite"
    ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{db}", sql_batch_size=1)
    log = ulog.get_logger("svc")
    log.info("bare info")
    log.error("prefixed error")
    for h in logging.getLogger().handlers:
        h.flush()

    import signal as _signal

    def _abort_soon():
        time.sleep(0.4)
        import os as _os

        _os.kill(_os.getpid(), _signal.SIGINT)

    threading.Thread(target=_abort_soon, daemon=True).start()
    with contextlib.suppress(KeyboardInterrupt):
        cli_main(["tail", "--db", str(db), "--since-start", "--interval", "100"])
    out = capsys.readouterr().out
    assert "svc  bare info" in out
    assert "svc: error: prefixed error" in out
