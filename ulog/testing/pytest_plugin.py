"""ulog pytest plugin — auto-discovered via ``[project.entry-points.pytest11]``.

Story 1.1 owns: option registration + gating decision (``config._ulog_enabled``).
Story 1.2 owns: lifecycle hooks (``pytest_runtest_protocol`` +
``pytest_runtest_makereport``) that emit ``test started`` / ``test outcome``
records, plus a separate ERROR record on failure carrying the traceback.
Story 1.3 owns: stable test_id contract via ``_make_test_id`` (FR55).
Story 1.4 owns: propagation contract tests (FR59-61) — pure tests, no code here.
Story 1.5 owns: --ulog-db auto-setup + --ulog-summary one-line session summary
+ -q suppression (FR67/FR69).

The plugin is OFF by default unless either:
  (a) a host ``conftest.py`` has called ``ulog.setup(...)`` (i.e.
      ``ulog.is_configured()`` returns True), OR
  (b) the user passes ``--ulog-db PATH`` on the pytest CLI.

``--ulog-disable`` short-circuits the plugin even when (a) or (b) hold.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Generator

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register --ulog-db, --ulog-disable, --ulog-summary."""
    group = parser.getgroup("ulog", "ulog test integration")
    group.addoption(
        "--ulog-db",
        action="store",
        dest="ulog_db",
        default=None,
        metavar="PATH",
        help=(
            "Override the destination DB for ulog test records. "
            "Setup is auto-configured if no host setup() exists."
        ),
    )
    group.addoption(
        "--ulog-disable",
        action="store_true",
        dest="ulog_disable",
        default=False,
        help=(
            "Short-circuit the ulog pytest plugin even when host "
            "setup() exists or --ulog-db is set."
        ),
    )
    group.addoption(
        "--ulog-summary",
        action="store_true",
        dest="ulog_summary",
        default=True,
        help=(
            "Print one-line stderr summary after the session "
            "(default ON; -q suppresses)."
        ),
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    """Compute the gating decision, optionally auto-setup, and initialize the
    session counter on ``config``.

    ``trylast=True`` is critical: pytest schedules entry-point plugins'
    ``pytest_configure`` BEFORE the user's ``conftest.py`` ``pytest_configure``.
    Without it, a host that calls ``ulog.setup(...)`` in their conftest
    sees their own configure run AFTER ours, and our gate (which reads
    ``ulog.is_configured()``) would always be False — disabling the plugin
    even though the user intended to enable it.

    Story 1.5 additions:
      - FR67 auto-setup: when the gate enables AND the host did NOT already
        configure ``ulog.setup``, AND ``--ulog-db`` was passed, call
        ``ulog.setup(handlers=['sql'], sql_url=...)`` here exactly once.
      - ``_ulog_db_path`` stash: only the CLI value AND only when auto-setup
        actually fired — guarantees the summary line's ``→ ulog-web <path>``
        suffix points at where records actually went (no host-path leak).
      - ``_ulog_session_stats`` counter: 4-way (passed/failed/skipped/errored)
        for ``pytest_terminal_summary`` to render at session end.
    """
    import ulog  # lazy: only on pytest config
    ulog_db = config.getoption("ulog_db")
    host_already_configured = ulog.is_configured()
    enabled = (
        not config.getoption("ulog_disable")
        and (host_already_configured or bool(ulog_db))
    )
    auto_setup_fired = (
        enabled and not host_already_configured and bool(ulog_db)
    )
    # IMPORTANT ORDERING (review patch P1): set the gate + stash + stats dict
    # BEFORE attempting auto-setup. If `ulog.setup` raises (bad path, missing
    # SQLAlchemy, locked DB), the exception still propagates — but downstream
    # hooks see a coherent `_ulog_enabled` / `_ulog_session_stats` rather than
    # falling back to the `getattr(..., default)` form which would silently
    # disable the plugin without explanation.
    config._ulog_enabled = enabled  # type: ignore[attr-defined]
    # AC7: stash the CLI-provided path ONLY when auto-setup will be attempted.
    # If host configured (we don't know their URL) → omit the suffix later
    # rather than mislead. If gate disabled → no summary at all anyway.
    config._ulog_db_path = ulog_db if auto_setup_fired else None  # type: ignore[attr-defined]
    # FR69: 4-way internal counter; the rendered line collapses errored→failed.
    # Only initialize when the plugin is actually enabled — keeps disabled-run
    # state minimal and prevents a hypothetical future caller from finding a
    # populated dict in a disabled session (review patch P5).
    if enabled:
        config._ulog_session_stats = {  # type: ignore[attr-defined]
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errored": 0,
        }
    if auto_setup_fired:
        # FR67: wire up SQL persistence transparently. Use the user's literal
        # path string in the URL so leading "./" or absolute paths round-trip.
        ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{ulog_db}")

    # Story 1.10 — xdist + Windows + NFS handling. Runs AFTER auto-setup so
    # it sees the active SQL handler (whether host-configured or auto-set-up
    # by Story 1.5). No-op when not under xdist or when plugin is disabled.
    _apply_xdist_storage_strategy(config)


def _get_enabled(config: pytest.Config) -> bool:
    """Helper consumed by Story 1.2+ hooks. Defaults False if attr missing."""
    return bool(getattr(config, "_ulog_enabled", False))


def _make_test_id(item: pytest.Item) -> str:
    """Return the stable test_id for a pytest item per PRD-v0.3 FR55.

    The contract is whatever pytest's ``Item.nodeid`` produces under the
    project's collection layout — we don't post-process it. In practice
    that means:

      - Non-parametrized: ``"tests/path.py::test_name"``.
      - Parametrized: ``"tests/path.py::test_name[param-id]"`` — pytest's
        dash-joined parametrize ID is preserved verbatim, including
        user-supplied ``ids=[...]`` and ``ids=callable`` forms.
      - Class methods: ``"tests/path.py::TestCls::test_method[param]"``.
      - Path component is rootdir-relative and uses forward slashes on
        Linux/macOS (the supported CI surface for v0.3); Windows behavior
        is exercised separately in Story 1.10.
      - Stable across runs given the same test source.

    Implementation: ``item.nodeid``. We capture this as a single named call
    so the FR55 contract has one definition rather than a literal sprinkled
    across the protocol hook (Story 1.2), the propagation tests (Story 1.4),
    the programmatic API (Story 1.9), and the replay generator (Story 4.3).
    """
    return item.nodeid


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, None, None]:
    """Wrap test execution: bind test_id, emit started + outcome records, unbind.

    Why a hookwrapper around ``pytest_runtest_protocol`` instead of using
    ``pytest_runtest_logstart`` / ``logfinish`` directly: those hooks don't
    receive ``config``, so reading the gate ``_get_enabled(config)`` would
    require module-level state. The protocol hookwrapper gives us
    ``item.config`` and runs around the entire setup → call → teardown
    sequence, so fixtures see ``test_id`` in their context too.
    """
    if not _get_enabled(item.config):
        yield
        return

    import ulog  # lazy: only on enabled path
    test_id = _make_test_id(item)  # FR55 — see _make_test_id docstring (Story 1.3 contract)
    log = ulog.get_logger("ulog.test")

    ulog.bind(test_id=test_id)
    log.info("test started")
    try:
        yield
    finally:
        # Reports populated by the makereport hookwrapper across phases.
        # Wrap emission so a defect in the synthesis path can NEVER prevent
        # unbind/cleanup from running (review finding H1: `_emit_outcome_records`
        # raising would leave `test_id` poisoned in contextvars for the next test).
        try:
            _emit_outcome_records(item, log)
        except Exception:  # noqa: BLE001 — emit must not break the test runner
            pass
        finally:
            # Unbind LAST so the outcome records (if emitted) still carry test_id.
            ulog.unbind("test_id")
            # Drop per-test stash to avoid cross-test pollution under
            # rerun-style plugins that may invoke makereport for the same item
            # multiple times (review finding H2).
            for attr in ("_ulog_reports", "_ulog_excinfo"):
                if hasattr(item, attr):
                    delattr(item, attr)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, None, None]:
    """Capture per-phase reports onto ``item._ulog_reports``.

    Pytest invokes this hook three times per test (setup / call / teardown).
    The hookwrapper accumulates reports onto the item so the protocol
    wrapper's ``finally`` block can synthesize the outcome records.

    We also stash ``call.excinfo`` alongside each phase's report. Pytest's
    ``TestReport.longrepr.reprcrash.message`` is unreliable for extracting
    the exception type name (e.g. for plain ``assert 1 == 2`` it strips the
    ``AssertionError:`` prefix). ``call.excinfo.type.__name__`` is the
    canonical source.
    """
    if not _get_enabled(item.config):
        yield
        return

    outcome = yield
    # pytest's type stubs declare hookwrapper yield as None; runtime is _Result.
    # If another plugin's hookwrapper raised after its own yield, pluggy stores
    # the exception in `outcome` and `get_result()` re-raises it. We catch and
    # short-circuit so the offending plugin's failure doesn't cascade into our
    # capture path — losing this phase's report is preferable to crashing the
    # session (review finding H3).
    try:
        report = outcome.get_result()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return
    if not hasattr(item, "_ulog_reports"):
        item._ulog_reports = {}  # type: ignore[attr-defined]
    if not hasattr(item, "_ulog_excinfo"):
        item._ulog_excinfo = {}  # type: ignore[attr-defined]
    item._ulog_reports[report.when] = report  # type: ignore[attr-defined]
    item._ulog_excinfo[report.when] = call.excinfo  # type: ignore[attr-defined]


def _emit_outcome_records(item: pytest.Item, log: logging.Logger) -> None:
    """Synthesize the outcome record (always) + traceback ERROR (if failed)
    + teardown ERROR (if teardown failed). Called from the protocol wrapper's
    ``finally`` block."""
    reports: dict[str, pytest.TestReport] = getattr(item, "_ulog_reports", {})
    excinfos: dict[str, Any] = getattr(item, "_ulog_excinfo", {})

    # If no phase report was captured at all, the test errored before any
    # makereport fired (collection-edge or another plugin short-circuiting).
    # Surface that as `errored` rather than silently emitting `passed` with
    # zero duration (review finding M2).
    if not reports:
        # FR69: increment session counter BEFORE the log.error call (review
        # patch P2). If `log.error` itself raises (broken SQL handler, etc.),
        # the surrounding try/except in `pytest_runtest_protocol` swallows
        # the exception so unbind still runs — but the counter would
        # otherwise be skipped, undercounting the summary. Bumping first
        # keeps counts honest even in degraded states.
        _bump_session_stats(item.config, "errored")
        log.error(
            "test errored",
            extra={"outcome": "errored", "duration_s": 0.0, "phase": "setup"},
        )
        return

    final_outcome, final_phase, failure_report = _classify(reports)
    duration_s = sum(r.duration for r in reports.values())

    # FR69: increment counter on the body verdict BEFORE emit (review patch P2).
    # Not the optional traceback, not the optional teardown ERROR — those are
    # not the body's verdict.
    _bump_session_stats(item.config, final_outcome)

    level = (
        logging.ERROR if final_outcome in ("failed", "errored") else logging.INFO
    )
    log.log(
        level,
        f"test {final_outcome}",
        extra={
            "outcome": final_outcome,
            "duration_s": duration_s,
            "phase": final_phase,
        },
    )

    if failure_report is not None:
        exc = _longrepr_to_exc(
            failure_report.longrepr, excinfos.get(failure_report.when)
        )
        log.error(
            f"{exc['type']}: {exc['msg']}",
            extra={"exc": exc},
        )

    teardown = reports.get("teardown")
    if teardown is not None and teardown.outcome == "failed":
        td_exc = _longrepr_to_exc(teardown.longrepr, excinfos.get("teardown"))
        log.error(
            f"teardown failed: {td_exc['msg']}",
            extra={"phase": "teardown", "exc": td_exc},
        )
        # No counter increment here — teardown failure is orthogonal to the
        # body verdict per AC4 of Story 1.2 (body outcome stays as-classified).


def _bump_session_stats(config: pytest.Config, outcome: str) -> None:
    """Increment the FR69 session counter for ``outcome`` (Story 1.5).

    Defensive: uses ``getattr`` with a default so a hypothetical caller that
    invokes ``_emit_outcome_records`` before ``pytest_configure`` populated the
    attribute (e.g. an exotic plugin dispatch) doesn't crash."""
    stats = getattr(config, "_ulog_session_stats", None)
    if stats is not None and outcome in stats:
        stats[outcome] += 1


def _classify(
    reports: dict[str, pytest.TestReport],
) -> tuple[str, str, pytest.TestReport | None]:
    """Determine final outcome+phase ignoring teardown (handled separately).

    Returns (outcome, phase, failure_report) where:
      - outcome ∈ {"passed", "failed", "skipped", "errored"}
      - phase   ∈ {"setup", "call", "teardown"}
      - failure_report is the TestReport whose longrepr we should expose in
        the additional ERROR record, or None on pass / skip.

    Teardown failure does NOT change the body's outcome; it produces a
    separate ERROR record (see _emit_outcome_records). PRD-v0.3 FR57.
    """
    setup = reports.get("setup")
    call = reports.get("call")
    if setup is not None and setup.outcome == "failed":
        return ("errored", "setup", setup)
    if call is not None and call.outcome == "failed":
        return ("failed", "call", call)
    if setup is not None and setup.outcome == "skipped":
        return ("skipped", "setup", None)
    if call is not None and call.outcome == "skipped":
        return ("skipped", "call", None)
    return ("passed", "call", None)


def _longrepr_to_exc(
    longrepr: object, excinfo: Any = None
) -> dict[str, Any]:
    """Best-effort extraction of ``longrepr`` to the
    {type, msg, tb} JSON shape per PRD-v0.3 §2.1.2.

    Pytest's longrepr can be:
      - ``ExceptionChainRepr`` / ``ReprExceptionInfo`` (rich, has ``reprcrash``)
      - a plain string (e.g. for skip reasons)
      - None

    When ``excinfo`` is provided (a ``pytest.ExceptionInfo``), prefer it for
    the type name — ``longrepr.reprcrash.message`` strips the
    ``ExceptionType:`` prefix for plain assertions, making it unreliable.

    The contract: always return a dict with non-empty ``tb``.
    """
    # Prefer excinfo for type name — it's the canonical source.
    exc_type: str | None = None
    exc_msg: str | None = None
    if excinfo is not None:
        try:
            exc_type = excinfo.type.__name__
            exc_msg = str(excinfo.value)
        except Exception:  # noqa: BLE001
            exc_type = None
            exc_msg = None

    # Fall back to longrepr.reprcrash if excinfo unavailable or its access failed.
    if exc_type is None:
        crash = getattr(longrepr, "reprcrash", None)
        if crash is not None:
            message = str(getattr(crash, "message", ""))
            # Only treat the prefix-before-`:` as an exception type when it
            # looks like a Python identifier (ASCII letters / digits / underscore /
            # dot for qualified names). This rejects OSError-style messages like
            # `[Errno 2] No such file or directory: '/foo'` where the prefix is
            # not a type name (review finding M3).
            ct, _, cm = message.partition(":")
            ct_stripped = ct.strip()
            if ct_stripped and all(
                c.isalnum() or c in "._" for c in ct_stripped
            ):
                exc_type = ct_stripped
                exc_msg = cm.strip()
            else:
                exc_type, exc_msg = "Exception", message
        else:
            exc_type, exc_msg = "Unknown", str(longrepr)

    if exc_msg is None:
        exc_msg = ""

    # Ensure tb_lines is non-empty AND meaningful. `"".splitlines() == []` so
    # the `or` fallback would produce `[""]`; collapse that to a single
    # placeholder marker instead (review finding L5).
    tb_lines = str(longrepr).splitlines()
    if not tb_lines or tb_lines == [""]:
        tb_lines = ["<no traceback>"]
    return {"type": exc_type, "msg": exc_msg, "tb": tb_lines}


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: pytest.Config
) -> None:
    """Print a one-line ulog summary at session end (FR69, Story 1.5).

    Format (PRD-v0.3 §2.1.6):
        ulog: N tests, X passed, Y failed, Z skipped → ulog-web <db> to triage

    The internal 4-way counter (passed/failed/skipped/errored) collapses
    ``errored`` into ``failed`` for the rendered line so the user-facing
    summary matches the PRD's 3-bucket display.

    Suppressed when:
      - The plugin gate is OFF (``_get_enabled(config) is False``) — covers
        ``--ulog-disable`` and the no-host-no-cli-flag default-OFF case.
      - The user passed ``-q`` / ``--quiet`` (``verbose < 0``).
      - ``--ulog-summary`` is explicitly OFF (currently store_true → defaults
        True; the negation is unreachable today but the check is defensive
        for future option-negation flags).
      - The session ran zero items (``--collect-only`` lands here).
    """
    if not _get_enabled(config):
        return
    if config.getoption("verbose") < 0:
        return
    if not config.getoption("ulog_summary"):
        return

    stats = getattr(config, "_ulog_session_stats", None)
    if stats is None:
        return
    total = sum(stats.values())
    if total == 0:
        # Covers --collect-only AND any session where no items reached
        # _emit_outcome_records (e.g. collection error). Avoid noisy
        # "ulog: 0 tests" output.
        return

    passed = stats["passed"]
    skipped = stats["skipped"]
    # Internal counter is 4-way; rendered line is 3-way per PRD-v0.3 §2.1.6.
    failed_or_errored = stats["failed"] + stats["errored"]

    db_path = getattr(config, "_ulog_db_path", None)
    suffix = f" → ulog-web {db_path} to triage" if db_path else ""
    line = (
        f"ulog: {total} tests, {passed} passed, "
        f"{failed_or_errored} failed, {skipped} skipped{suffix}"
    )
    # write_line uses pytest's TerminalReporter `**markup` kwargs (yellow,
    # red, bold). Yellow signals "look here" without the alarm of red — fits
    # FR69's "informational summary" framing.
    terminalreporter.write_line(line, yellow=bool(failed_or_errored))


# ============================================================================
# Story 1.10 — xdist + Windows + NFS edge cases (NFR-PORT-10)
# ============================================================================
#
# When pytest-xdist is active, multiple worker subprocesses concurrently
# write to the SQL handler's SQLite DB. Default (DELETE) journal mode
# serializes writers; under contention we'd see `database is locked`
# errors. The strategy:
#
#   1. Detect xdist via env vars (PYTEST_XDIST_WORKER, _TESTRUNUID).
#   2. On Windows + xdist: unconditionally swap SQL → JSONL (file-locking
#      semantics on Windows are unreliable for SQLite under multi-process).
#   3. On Linux/macOS + xdist + NFS: swap (network FS doesn't support
#      reliable SQLite locking).
#   4. On Linux/macOS + xdist + local FS: enable PRAGMA journal_mode=WAL
#      so concurrent writes proceed without serialization.


_NETWORK_FS_TYPES_LINUX = {
    "nfs", "nfs4", "cifs", "smbfs", "smb3",
    "fuse.sshfs", "9p", "ceph",
}
_NETWORK_FS_TYPES_MACOS = {"nfs", "smbfs", "afpfs", "webdav"}


def _xdist_active() -> bool:
    """Return True if pytest-xdist is running (worker env vars present)."""
    return bool(
        os.environ.get("PYTEST_XDIST_WORKER")
        or os.environ.get("PYTEST_XDIST_TESTRUNUID")
    )


def _is_network_fs_linux(path: Path) -> bool:
    """Linux: parse /proc/self/mountinfo for the path's filesystem type."""
    try:
        with open("/proc/self/mountinfo") as fh:
            lines = fh.readlines()
    except OSError:
        return False
    best_match = ("", "")  # (mountpoint, fstype)
    path_str = str(path)
    for line in lines:
        parts = line.split()
        try:
            sep_idx = parts.index("-")
            mountpoint = parts[4]
            fstype = parts[sep_idx + 1]
        except (ValueError, IndexError):
            continue
        # Special-case the root mount `/`: every path lives under it,
        # so `path_str.startswith("/" + "/")` would never be true.
        is_match = (
            mountpoint == "/"
            or path_str == mountpoint
            or path_str.startswith(mountpoint + "/")
        )
        if is_match and len(mountpoint) > len(best_match[0]):
            best_match = (mountpoint, fstype)
        elif best_match[0] == "" and mountpoint == "/":
            best_match = (mountpoint, fstype)  # root-mount fallback
    return best_match[1] in _NETWORK_FS_TYPES_LINUX


def _is_network_fs_macos(path: Path) -> bool:
    """macOS: parse `mount` output for the path's filesystem type."""
    import subprocess
    try:
        output = subprocess.run(
            ["mount"], capture_output=True, text=True, timeout=2.0
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
    best_match = ("", "")
    path_str = str(path)
    for line in output.splitlines():
        # Format: <device> on <mountpoint> (<fstype>, ...)
        try:
            _, _, rest = line.partition(" on ")
            mountpoint, _, paren = rest.partition(" (")
            fstype = paren.split(",", 1)[0].strip()
        except Exception:  # noqa: BLE001
            continue
        is_match = (
            mountpoint == "/"
            or path_str == mountpoint
            or path_str.startswith(mountpoint + "/")
        )
        if is_match and len(mountpoint) > len(best_match[0]):
            best_match = (mountpoint, fstype)
    return best_match[1] in _NETWORK_FS_TYPES_MACOS


def _is_network_fs_windows(path: Path) -> bool:
    """Windows: GetDriveTypeW returns 4 for DRIVE_REMOTE.
    Conservative: if the ctypes call fails, return True so xdist+Windows
    always falls back to JSONL (per AC4)."""
    try:
        import ctypes
        DRIVE_REMOTE = 4
        drive = str(path)[:3]  # e.g. "C:\\"
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # ctypes returns Any; cast to bool explicitly to keep mypy clean.
        return bool(kernel32.GetDriveTypeW(drive) == DRIVE_REMOTE)
    except Exception:  # noqa: BLE001
        return True


def _is_network_fs(path: "str | Path") -> bool:
    """Detect whether `path` lives on a network filesystem (NFS / CIFS / SMB).

    Uses stdlib only (no psutil dep). Per-platform dispatch:
      - Linux: /proc/self/mountinfo
      - Windows: GetDriveTypeW (DRIVE_REMOTE = 4)
      - macOS: `mount` command output
      - Other: False (best-effort, assume local).

    Errors / unknown paths → False (conservative — local fs assumption).
    """
    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError):
        return False

    if sys.platform == "win32":
        return _is_network_fs_windows(resolved)
    if sys.platform == "darwin":
        return _is_network_fs_macos(resolved)
    return _is_network_fs_linux(resolved)


def _swap_sql_for_jsonl(reason: str) -> None:
    """Detach all `_ulog_managed` SQL handlers and reinstall as JSONL at
    the same path stem. Prints a single warning to stderr.

    `reason` is included in the warning text (e.g. 'xdist+NFS', 'xdist+
    Windows', 'WAL mode unavailable').
    """
    import ulog
    from ulog.handlers.sql import SQLHandler

    root = logging.getLogger()
    for handler in list(root.handlers):
        if not isinstance(handler, SQLHandler):
            continue
        if not getattr(handler, "_ulog_managed", False):
            continue
        url = getattr(handler, "_url", "")
        if not url.startswith("sqlite:///"):
            continue
        sqlite_path = url[len("sqlite:///"):]
        jsonl_path = sqlite_path.rsplit(".", 1)[0] + ".jsonl"
        print(
            f"ulog: {reason} detected — falling back from SQLite to "
            f"JSONL at {jsonl_path}",
            file=sys.stderr,
        )
        # Detach + close the SQL handler. Wrapped in try/except so a
        # broken handler doesn't prevent the JSONL replacement.
        try:
            handler.flush()
            handler.close()
        except Exception:  # noqa: BLE001
            pass
        root.removeHandler(handler)
        # Reinstall via setup — its idempotency removes any other managed
        # handlers and installs the JSONL one cleanly.
        ulog.setup(handlers=["json"], json_path=jsonl_path)
        return  # only one ulog SQL handler at a time per project convention


def _enable_wal_mode_or_fallback() -> bool:
    """For local-FS xdist: enable PRAGMA journal_mode=WAL on the SQL
    handler's engine. Returns True if WAL was enabled successfully.

    On failure (read-only DB, exotic filesystem), falls back to JSONL.

    Reentrancy note (review patch C1): we MUST NOT call
    `_swap_sql_for_jsonl` from inside the `with handler._engine.connect()
    as conn:` block — the swap closes the engine, and on `with`-exit
    SQLAlchemy would try to release a connection to a disposed pool.
    Capture the failure boolean inside the `try`, exit the connection
    context cleanly, THEN dispatch the fallback.
    """
    from ulog.handlers.sql import SQLHandler

    root = logging.getLogger()
    target_handler = None
    for handler in list(root.handlers):
        if not isinstance(handler, SQLHandler):
            continue
        if not getattr(handler, "_ulog_managed", False):
            continue
        target_handler = handler
        break
    if target_handler is None:
        return False

    wal_failed = False
    try:
        with target_handler._engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    except Exception:  # noqa: BLE001 — fall back on any PRAGMA failure
        wal_failed = True
    if wal_failed:
        _swap_sql_for_jsonl("WAL mode unavailable")
        return False
    return True


def _apply_xdist_storage_strategy(config: pytest.Config) -> None:
    """Story 1.10 entry point — called from `pytest_configure` AFTER the
    auto-setup branch (Story 1.5). No-op when not under xdist or when
    plugin is disabled.

    Dispatches: Windows+xdist → JSONL swap; NFS+xdist → JSONL swap;
    local+xdist → WAL mode (or JSONL fallback if PRAGMA fails).
    """
    if not _get_enabled(config):
        return  # AC5: gated off
    if not _xdist_active():
        return  # AC3: not under xdist — nothing to do

    from ulog.handlers.sql import SQLHandler

    # Find the active SQL handler (host-configured OR auto-set-up by us)
    sql_path = None
    for h in logging.getLogger().handlers:
        if isinstance(h, SQLHandler) and getattr(h, "_ulog_managed", False):
            url = getattr(h, "_url", "")
            if url.startswith("sqlite:///"):
                sql_path = url[len("sqlite:///"):]
                break

    if sql_path is None:
        return  # nothing to swap (e.g. JSONL handler already in use)

    if sys.platform == "win32":
        # AC4: Windows + xdist always falls back to JSONL.
        _swap_sql_for_jsonl("xdist+Windows")
    elif _is_network_fs(sql_path):
        # AC1: NFS / CIFS detected — fall back.
        _swap_sql_for_jsonl("xdist+NFS")
    else:
        # AC2: local FS — enable WAL mode (or JSONL if WAL fails).
        _enable_wal_mode_or_fallback()
