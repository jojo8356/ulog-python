"""ulog pytest plugin — auto-discovered via ``[project.entry-points.pytest11]``.

Story 1.1 owns: option registration + gating decision (``config._ulog_enabled``).
Story 1.2 owns: lifecycle hooks (``pytest_runtest_protocol`` +
``pytest_runtest_makereport``) that emit ``test started`` / ``test outcome``
records, plus a separate ERROR record on failure carrying the traceback.
Stories 1.3-1.5 own: parametrize verification, propagation contract tests,
summary output.

The plugin is OFF by default unless either:
  (a) a host ``conftest.py`` has called ``ulog.setup(...)`` (i.e.
      ``ulog.is_configured()`` returns True), OR
  (b) the user passes ``--ulog-db PATH`` on the pytest CLI.

``--ulog-disable`` short-circuits the plugin even when (a) or (b) hold.
"""
from __future__ import annotations

import logging
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
    """Compute the gating decision and store it on ``config._ulog_enabled``.

    ``trylast=True`` is critical: pytest schedules entry-point plugins'
    ``pytest_configure`` BEFORE the user's ``conftest.py`` ``pytest_configure``.
    Without it, a host that calls ``ulog.setup(...)`` in their conftest
    sees their own configure run AFTER ours, and our gate (which reads
    ``ulog.is_configured()``) would always be False — disabling the plugin
    even though the user intended to enable it.
    """
    import ulog  # lazy: only on pytest config
    enabled = (
        not config.getoption("ulog_disable")
        and (
            ulog.is_configured()
            or bool(config.getoption("ulog_db"))
        )
    )
    config._ulog_enabled = enabled  # type: ignore[attr-defined]


def _get_enabled(config: pytest.Config) -> bool:
    """Helper consumed by Story 1.2+ hooks. Defaults False if attr missing."""
    return bool(getattr(config, "_ulog_enabled", False))


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
    test_id = item.nodeid
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
        log.error(
            "test errored",
            extra={"outcome": "errored", "duration_s": 0.0, "phase": "setup"},
        )
        return

    final_outcome, final_phase, failure_report = _classify(reports)
    duration_s = sum(r.duration for r in reports.values())

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
