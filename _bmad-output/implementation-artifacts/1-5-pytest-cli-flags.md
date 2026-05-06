# Story 1.5: Pytest CLI flags

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**Epic:** 1 — v0.3 Test integration
**Story key:** `1-5-pytest-cli-flags`
**Implements:** FR67, FR68, FR69 (PRD-v0.3 §3.5)
**Source:** `docs/prds/PRD-v0.3-test-integration.md` §3.5 + §2.1.6, `_bmad-output/planning-artifacts/architecture.md` Decision C2 + lazy-import discipline, `_bmad-output/planning-artifacts/epics.md` Story 1.5
**Built on:** Story 1.1 (the three flags are ALREADY REGISTERED in `pytest_addoption`; `--ulog-disable` already short-circuits the gate; `--ulog-db` already enables the gate WITHOUT yet auto-configuring setup), Story 1.2 (`pytest_runtest_protocol` emits the records the summary line counts), Story 1.3 (`_make_test_id`), Story 1.4 (propagation tests already lock the SQL handler context)
**Foundation for:** Story 1.6 (the "Tests" sidebar in the viewer reads the records this story's auto-setup ensures land somewhere; the summary line teaches users where), Story 1.7 (URL filter assumes records exist), Story 1.10 (xdist-on-NFS edge cases assume `--ulog-db` works as documented)

---

## Story

As a **pytest user**,
I want **`--ulog-db PATH` to auto-configure the plugin when no host setup exists, `--ulog-disable` to fully short-circuit, and `--ulog-summary` (default ON; `-q` suppresses) to print a one-line stderr summary at session end**,
so that **I can run `pytest --ulog-db ./mytests.sqlite` once and have everything wired up — no `conftest.py` boilerplate, no surprise about where records went**.

## Acceptance Criteria

### AC1 — `--ulog-db PATH` auto-configures ulog.setup when no host setup exists (FR67)

**Given** no `conftest.py` has called `ulog.setup(...)` (i.e., `ulog.is_configured()` returns False at `pytest_configure` time)
**And** the user passes `pytest --ulog-db /tmp/X.sqlite`
**When** `pytest_configure` runs
**Then** the plugin calls `ulog.setup(handlers=['sql'], sql_url='sqlite:///tmp/X.sqlite', sql_batch_size=...)` exactly once, BEFORE the protocol hookwrapper fires for the first test
**And** records emitted by tests during the session land in `/tmp/X.sqlite` (verifiable via `_read_test_records`).

**Note on `sql_batch_size`:** the auto-setup uses pytest's default `sql_batch_size=100` (match `ulog.setup`'s default — the atexit flush + handler.close() in real CLI use handles the trailing batch). For pytester-based tests of the auto-setup path (Tasks 4.2 and 5.2 only), the host conftest declares a `pytest_unconfigure` that explicitly flushes/closes `_ulog_managed` handlers — this is the "flush-only" pattern, distinct from `_conftest_with_setup` which configures BOTH setup and unconfigure flush. See `_conftest_with_unconfigure_flush_only` helper introduced in Task 4.1.

**Auto-setup vs host-setup tests:** Tasks 5.1, 5.3, 5.4, 5.5, 5.6 all use `_conftest_with_setup` (host already configured → auto-setup does NOT fire). Only Tasks 4.2 and 5.2 exercise the auto-setup path through `--ulog-db` with no host configuration.

### AC2 — `--ulog-db PATH` does NOT override an existing host setup (FR67 corollary)

**Given** the host's `conftest.py` has called `ulog.setup(handlers=['sql'], sql_url='sqlite:///host.sqlite', ...)` (so `ulog.is_configured()` returns True)
**And** the user passes `pytest --ulog-db /tmp/cli.sqlite`
**When** `pytest_configure` runs
**Then** the plugin does NOT call `ulog.setup` again — the host's existing handler is preserved
**And** records land in `/host.sqlite` (the host's destination), not `/tmp/cli.sqlite`. The CLI flag is informational/path-tracking only when the host has already configured setup.

### AC3 — `--ulog-disable` short-circuits the plugin (FR68 — already covered, regression-only)

**Given** the plugin is enabled (host setup OR `--ulog-db`)
**And** the user passes `--ulog-disable`
**When** any test runs
**Then** ZERO records with `logger='ulog.test'` are emitted (already covered by Story 1.2's `test_disabled_plugin_emits_nothing`).

This AC is a REGRESSION GATE — Story 1.5 must not break it. No new test required.

### AC4 — `--ulog-summary` prints a one-line stderr summary at session end (FR69)

**Given** the plugin is enabled
**And** `--ulog-summary` is in effect (default ON; explicitly `--ulog-summary` also ON)
**And** the session ran some tests with mixed outcomes
**When** the session ends (the `pytest_terminal_summary` hook fires)
**Then** a single line is written to the terminal reporter / stderr matching the format:
```
ulog: <total> tests, <P> passed, <F> failed, <S> skipped → ulog-web <db_path> to triage
```
where `<total>` = `<P> + <F> + <S> + <errored count>` (errored counts as a non-pass/non-skip; PRD-v0.3 §2.1.6 example only shows passed/failed/skipped — Story 1.5 follows that 3-bucket display but `<total>` includes errored).

### AC5 — `pytest -q` suppresses the summary line (FR69)

**Given** the plugin is enabled and `--ulog-summary` is in its default-ON state
**And** the user passes `pytest -q` (or `--quiet`)
**When** the session ends
**Then** the ulog summary line is NOT printed.

The detection mechanism: read `config.getoption('verbose') < 0` (pytest's `-q` decrements verbose). Do NOT inspect the `terminalreporter`'s mode directly — verbose-level is the documented quiet contract.

### AC6 — Summary counts match `_emit_outcome_records` outcomes

**Given** a session of N tests with a mix of pass/fail/skip/errored
**When** the summary line is computed
**Then** the counts equal exactly the count of `_emit_outcome_records` calls per outcome (NOT a re-query of the SQL table). The plugin maintains an in-memory `dict[str, int]` counter indexed by outcome string, incremented from `_emit_outcome_records` after each item's protocol exits.

### AC7 — Summary db_path source

**Given** the plugin is enabled
**When** the summary line is printed
**Then** `<db_path>` is:
  - The `--ulog-db` value, ONLY IF the auto-setup branch actually fired (i.e., gate enabled AND host did NOT already configure setup AND `--ulog-db` was passed). In that case records are GUARANTEED to be at that path → printing it is accurate.
  - Otherwise (host already configured → records at host's path; OR no `--ulog-db` passed at all → records at the host's path or nowhere): the line OMITS the `→ ulog-web …` portion, showing only `ulog: N tests, X passed, Y failed, Z skipped`. **Rationale:** showing the CLI flag's path when records went elsewhere (host's path) would mislead the user. Introspecting host-configured handlers to recover the URL is OUT OF SCOPE; deferred to a v0.4 enhancement story.

### AC8 — `--ulog-disable` suppresses the summary line too

**Given** the plugin is gated OFF (`--ulog-disable` was passed OR no host setup AND no `--ulog-db`)
**When** the session ends
**Then** the summary line is NOT printed. The `pytest_terminal_summary` hook short-circuits on the gate via `_get_enabled(config)`.

### AC9 — Frozen-invariant + regression-gate compliance

**Given** Story 1.5's changes
**When** the standard regression checks run
**Then**:
  - `dependencies = []` in `pyproject.toml` is unchanged (NFR-DEP-50 / SC4).
  - `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/`, `ulog/testing/__init__.py` ALL UNCHANGED. Story 1.5 lives entirely in `ulog/testing/pytest_plugin.py` and `tests/test_pytest_plugin.py`.
  - All Story 1.1 + 1.2 + 1.3 + 1.4 tests still pass (31 baseline in `test_pytest_plugin.py`).

---

## Tasks / Subtasks

- [x] **Task 1** — Implement `--ulog-db` auto-setup in `pytest_configure` (AC1, AC2)
  - [x] 1.1 In `ulog/testing/pytest_plugin.py`, modify `pytest_configure` to call `ulog.setup(...)` when (a) the gate enables, (b) `ulog.is_configured()` returns False, (c) `--ulog-db` was explicitly passed. Pseudocode:

    ```python
    @pytest.hookimpl(trylast=True)
    def pytest_configure(config: pytest.Config) -> None:
        import ulog
        ulog_db = config.getoption("ulog_db")
        host_already_configured = ulog.is_configured()
        enabled = (
            not config.getoption("ulog_disable")
            and (host_already_configured or bool(ulog_db))
        )
        # FR67: auto-setup ONLY when host hasn't configured AND --ulog-db is set.
        # If host setup exists, we don't override (AC2).
        auto_setup_fired = (
            enabled and not host_already_configured and bool(ulog_db)
        )
        if auto_setup_fired:
            ulog.setup(handlers=["sql"], sql_url=f"sqlite:///{ulog_db}")
        config._ulog_enabled = enabled  # type: ignore[attr-defined]
        # AC7: stash db_path for the summary hook ONLY when auto-setup
        # actually fired — guarantees `→ ulog-web <path>` in the line points
        # to where records actually went. If host configured, we don't know
        # their URL → omit the suffix rather than mislead.
        config._ulog_db_path = ulog_db if auto_setup_fired else None  # type: ignore[attr-defined]
    ```

  - [x] 1.2 The `f"sqlite:///{ulog_db}"` form constructs a relative SQLite URL when `ulog_db` starts with `./` and an absolute one when it starts with `/`. Both work for `sqlalchemy.create_engine`. Do NOT call `Path(ulog_db).as_posix()` here — that breaks relative paths' leading `./`. Story 1.4's Test 4.1 hand-rolled conftest demonstrates the right URL shape; copy it.

  - [x] 1.3 Use `ulog.setup(handlers=["sql"], sql_url=...)` with the plain default `sql_batch_size=100`. Don't pass `sql_batch_size=1` here — that's a test-fixture concern, not a CLI-default concern. Real CLI users want batching for performance (NFR-PERF-20).

- [x] **Task 2** — Add session-level outcome counter (AC4, AC6)
  - [x] 2.1 In `pytest_configure`, after the `_ulog_db_path` stash, initialize:

    ```python
    config._ulog_session_stats = {  # type: ignore[attr-defined]
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errored": 0,
    }
    ```

  - [x] 2.2 In `_emit_outcome_records(item, log)`, after the outcome record is emitted, increment the counter:

    ```python
    stats = getattr(item.config, "_ulog_session_stats", None)
    if stats is not None and final_outcome in stats:
        stats[final_outcome] += 1
    ```

    Place this after the `log.log(level, f"test {final_outcome}", ...)` call but BEFORE the failure-traceback emit — the counter cares about the body verdict (`final_outcome`), not the optional traceback record. **Crucially:** the teardown-ERROR emit path (the `if teardown is not None and teardown.outcome == "failed":` block at the end of `_emit_outcome_records`) does NOT increment any counter — teardown failures are surfaced as a separate ERROR record but the body verdict has already been counted, and double-counting would inflate the failed bucket.

  - [x] 2.3 The early-return path in `_emit_outcome_records` (when `not reports`, i.e., no phase report captured — Story 1.2 review patch M2) emits an `errored` record. Increment the counter there too:

    ```python
    if not reports:
        log.error("test errored", extra={...})
        stats = getattr(item.config, "_ulog_session_stats", None)
        if stats is not None:
            stats["errored"] += 1
        return
    ```

  - [x] 2.4 Use `getattr(...)` rather than direct attribute access — `_emit_outcome_records` may run before `pytest_configure` populates the attribute in pathological scenarios (e.g., a plugin that dispatches `pytest_runtest_protocol` outside the normal lifecycle). Defensive default keeps the counter independent of that edge.

- [x] **Task 3** — Implement `pytest_terminal_summary` hook (AC4, AC5, AC7, AC8)
  - [x] 3.1 Add a new hook to `ulog/testing/pytest_plugin.py`:

    ```python
    def pytest_terminal_summary(
        terminalreporter: "Any", exitstatus: int, config: pytest.Config
    ) -> None:
        """Print a one-line ulog summary at session end (FR69).

        Suppressed when:
          - The plugin gate is OFF (`_get_enabled(config) is False`).
          - The user passed `-q` / `--quiet` (`config.getoption('verbose') < 0`).
          - `--ulog-summary` is OFF (defaults to True; the flag is store_true
            so this can only be False if a future option negation lands —
            currently unreachable but defensive).

        Output format (FR69):
            ulog: N tests, X passed, Y failed, Z skipped → ulog-web <db> to triage
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
            return  # nothing to summarize — empty session

        passed = stats["passed"]
        failed = stats["failed"]
        skipped = stats["skipped"]
        # Errored is conceptually grouped under "failed" for the user-facing
        # summary per PRD-v0.3 §2.1.6 example which only shows pass/fail/skip.
        # Keep them distinct in the counter (AC6) but combine for display.
        failed_or_errored = failed + stats["errored"]

        db_path = getattr(config, "_ulog_db_path", None)
        suffix = f" → ulog-web {db_path} to triage" if db_path else ""
        line = (
            f"ulog: {total} tests, {passed} passed, "
            f"{failed_or_errored} failed, {skipped} skipped{suffix}"
        )
        # `--collect-only` runs no items → total == 0 above already short-circuits.
        # write_line uses pytest's TerminalReporter `**markup` kwargs (yellow/red/bold).
        terminalreporter.write_line(line, yellow=bool(failed_or_errored))
    ```

  - [x] 3.2 The `terminalreporter.write_line(line, yellow=...)` API is pytest's standard mechanism — it writes to the same stream pytest's own summary uses (stderr in normal mode, captured in `-s`/`-q` modes). Don't use `print(file=sys.stderr)` directly; that bypasses pytester's capture and complicates testing.

  - [x] 3.3 The `errored` count is FOLDED into `failed` for the user-facing display (per PRD-v0.3 §2.1.6 example: `ulog: 412 tests, 409 passed, 3 failed, 0 skipped` — three buckets, not four). Internal counter stays four-way for AC6's "match `_emit_outcome_records` outcomes" requirement; only the rendered line collapses.

- [x] **Task 4** — Tests for FR67 auto-setup (AC1, AC2)
  - [x] 4.1 Add a section header in `tests/test_pytest_plugin.py`:

    ```python
    # ============================================================================
    # Story 1.5 — Pytest CLI flags (FR67-69)
    # ============================================================================
    ```

    Place after the Story 1.4 block. Also add a new helper just below `_conftest_with_setup` (around line 168 of the post-Story-1.4 file):

    ```python
    def _conftest_unconfigure_flush_only() -> str:
        """Conftest body for tests that exercise the plugin's --ulog-db auto-setup
        path: NO host pytest_configure call (so the plugin's own auto-setup is
        what wires up the SQL handler), but a pytest_unconfigure that flushes
        any _ulog_managed handlers before the outer test reads back the DB.

        Used by Tasks 4.2 (AC1) and 5.2 (AC7) — distinct from
        `_conftest_with_setup` which is for tests that simulate a host that
        already configured ulog (so auto-setup MUST NOT fire).
        """
        return '''
            import logging
            def pytest_unconfigure(config):
                for h in list(logging.getLogger().handlers):
                    if getattr(h, '_ulog_managed', False):
                        try:
                            h.flush()
                            h.close()
                        except Exception:
                            pass
                        logging.getLogger().removeHandler(h)
        '''
    ```

  - [x] 4.2 Add `test_ulog_db_auto_configures_setup_when_host_unconfigured` (AC1):

    ```python
    def test_ulog_db_auto_configures_setup_when_host_unconfigured(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC1 / FR67 — `--ulog-db PATH` triggers auto-setup when no host conftest
        called ulog.setup. Records emitted by tests land in PATH."""
        db = tmp_path / "logs.sqlite"
        # No host setup — relying on plugin's auto-setup. The conftest only
        # provides the unconfigure-flush so records land before we read back.
        pytester.makeconftest(_conftest_unconfigure_flush_only())
        pytester.makepyfile("def test_pass(): assert True")
        result = pytester.runpytest("--ulog-db", str(db))
        assert result.ret == 0

        records = _read_test_records(db)
        # If auto-setup didn't fire, records would be 0 (no SQL handler attached)
        # — anchoring the count catches the regression loudly.
        assert len(records) == 2, (
            f"FR67: --ulog-db must auto-configure setup; got {len(records)} records"
        )
        assert records[0]["msg"] == "test started"
        assert records[1]["msg"] == "test passed"
    ```

  - [x] 4.3 Add `test_ulog_db_does_not_override_host_setup` (AC2):

    ```python
    def test_ulog_db_does_not_override_host_setup(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC2 / FR67 — when host conftest already configured ulog.setup,
        `--ulog-db PATH_B` does NOT redirect — records land where the host
        configured them, not at PATH_B."""
        host_db = tmp_path / "host.sqlite"
        cli_db = tmp_path / "cli.sqlite"
        pytester.makeconftest(_conftest_with_setup(host_db))
        pytester.makepyfile("def test_pass(): assert True")
        result = pytester.runpytest("--ulog-db", str(cli_db))
        assert result.ret == 0

        # Records land at host_db, NOT at cli_db
        host_records = _read_test_records(host_db)
        assert len(host_records) == 2, "host setup must keep its destination"

        # cli_db either doesn't exist OR exists but is empty
        cli_records = _read_test_records(cli_db) if cli_db.exists() else []
        assert cli_records == [], (
            f"AC2: --ulog-db must not redirect when host setup exists; "
            f"found cli records: {cli_records}"
        )
    ```

- [x] **Task 5** — Tests for FR69 summary line (AC4, AC5, AC6, AC7, AC8)
  - [x] 5.1 Add `test_summary_line_default_on` (AC4) — single passing test, default summary ON, assert the line appears in the captured output:

    ```python
    def test_summary_line_default_on(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC4 / FR69 — `--ulog-summary` defaults to ON; one-line summary appears
        on session end."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_with_setup(db))
        pytester.makepyfile("""
            def test_a(): assert True
            def test_b(): assert True
            def test_c(): assert False
        """)
        result = pytester.runpytest()  # --ulog-summary defaults ON
        # Summary line is written via terminalreporter — captured in stdout
        output = result.stdout.str() + result.stderr.str()
        assert "ulog: 3 tests" in output, output
        assert "2 passed" in output
        assert "1 failed" in output
        assert "0 skipped" in output
    ```

  - [x] 5.2 Add `test_summary_line_includes_db_path_when_cli_passed` (AC7):

    ```python
    def test_summary_line_includes_db_path_when_cli_passed(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC7 — `--ulog-db PATH` (no host setup) makes the summary line include
        `→ ulog-web PATH`. Records actually land at PATH (auto-setup fired),
        so the suffix is accurate."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_unconfigure_flush_only())
        pytester.makepyfile("def test_pass(): assert True")
        result = pytester.runpytest("--ulog-db", str(db))
        output = result.stdout.str() + result.stderr.str()
        assert "ulog: 1 tests, 1 passed" in output
        assert f"→ ulog-web {db} to triage" in output, output
    ```

  - [x] 5.2.1 Add `test_summary_line_omits_db_path_when_host_configured` (AC7 inverse):

    ```python
    def test_summary_line_omits_db_path_when_host_configured(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC7 inverse — when host configured setup AND `--ulog-db PATH_B` is
        also passed, records went to host's path (AC2), so the summary line
        OMITS the `→ ulog-web` suffix to avoid misleading the user about where
        records landed."""
        host_db = tmp_path / "host.sqlite"
        cli_db = tmp_path / "cli.sqlite"
        pytester.makeconftest(_conftest_with_setup(host_db))
        pytester.makepyfile("def test_pass(): assert True")
        result = pytester.runpytest("--ulog-db", str(cli_db))
        output = result.stdout.str() + result.stderr.str()
        assert "ulog: 1 tests, 1 passed" in output
        # Critical: NO ulog-web suffix should appear, because we don't know
        # the host's path and showing the CLI path would lie.
        assert "→ ulog-web" not in output, (
            f"AC7: must omit `→ ulog-web` when host configured (records went "
            f"to host path, not CLI path); got: {output!r}"
        )
    ```

  - [x] 5.3 Add `test_quiet_mode_suppresses_summary` (AC5):

    ```python
    def test_quiet_mode_suppresses_summary(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC5 / FR69 — `pytest -q` suppresses the summary line."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_with_setup(db))
        pytester.makepyfile("def test_pass(): assert True")
        result = pytester.runpytest("-q")
        output = result.stdout.str() + result.stderr.str()
        assert "ulog:" not in output, (
            f"`-q` must suppress summary line; got output: {output!r}"
        )
    ```

  - [x] 5.4 Add `test_disabled_plugin_suppresses_summary` (AC8):

    ```python
    def test_disabled_plugin_suppresses_summary(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC8 — `--ulog-disable` short-circuits the summary line too."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_with_setup(db))
        pytester.makepyfile("def test_pass(): assert True")
        result = pytester.runpytest("--ulog-disable")
        output = result.stdout.str() + result.stderr.str()
        assert "ulog:" not in output
    ```

  - [x] 5.5 Add `test_summary_counts_match_outcomes` (AC6) — mixed-outcome session: 2 passed, 1 failed, 1 skipped. Assert the rendered counts match exactly:

    ```python
    def test_summary_counts_match_outcomes(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC6 — summary counts match the outcomes _emit_outcome_records produced."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_with_setup(db))
        pytester.makepyfile("""
            import pytest
            def test_p1(): assert True
            def test_p2(): assert True
            def test_f(): assert False
            def test_s(): pytest.skip("not in scope")
        """)
        result = pytester.runpytest()
        output = result.stdout.str() + result.stderr.str()
        assert "ulog: 4 tests, 2 passed, 1 failed, 1 skipped" in output, output
    ```

  - [x] 5.6 Add `test_summary_errored_counts_as_failed_for_display` (AC4 / AC6 corollary) — fixture-error session produces an `errored` outcome internally; the summary line collapses it into the `failed` bucket per PRD-v0.3 §2.1.6's three-bucket display:

    ```python
    def test_summary_errored_counts_as_failed_for_display(
        pytester: pytest.Pytester, tmp_path: Path
    ) -> None:
        """AC4 corollary — fixture errors increment internal `errored` counter
        but display under `failed` (PRD §2.1.6 shows 3 buckets, not 4)."""
        db = tmp_path / "logs.sqlite"
        pytester.makeconftest(_conftest_with_setup(db))
        pytester.makepyfile("""
            import pytest

            @pytest.fixture
            def boom():
                raise RuntimeError("setup explodes")

            def test_p(): assert True
            def test_e(boom): pass
        """)
        result = pytester.runpytest()
        output = result.stdout.str() + result.stderr.str()
        # 1 passed + 1 errored → display "1 passed, 1 failed"
        assert "ulog: 2 tests, 1 passed, 1 failed, 0 skipped" in output, output
    ```

- [x] **Task 6** — Verify and ship
  - [x] 6.1 Run `python3 -m pytest tests/ -v`. Full suite stays green. Plugin test module grows from 31 (Story 1.4 baseline) to **40 tests** (9 new from Tasks 4.2, 4.3, 5.1, 5.2, 5.2.1, 5.3, 5.4, 5.5, 5.6). Tests 5.5 and 5.6 are intentionally kept distinct: 5.5 verifies the pass/fail/skip counter path, 5.6 verifies the errored-folded-into-failed display path. Test 5.2.1 was added during VS step (AC7 inverse — summary suffix omission when host configured). Final count: **9 new tests**, total **40 in `test_pytest_plugin.py`**.

  - [x] 6.2 Run `mypy ulog/testing/ --follow-imports=silent` — clean. New attributes `_ulog_db_path` and `_ulog_session_stats` on `config` will need `# type: ignore[attr-defined]` suppressions matching the Story 1.1 / 1.2 pattern (`_ulog_enabled`, `_ulog_reports`, `_ulog_excinfo`).
  - [x] 6.3 `grep '^dependencies' pyproject.toml | grep -q '\[\]'` exits 0.
  - [x] 6.4 `git diff --stat HEAD -- pyproject.toml` empty.
  - [x] 6.5 `git diff --stat HEAD -- tests/` reports only `tests/test_pytest_plugin.py`.
  - [x] 6.6 `git diff --stat HEAD -- ulog/` reports only `ulog/testing/pytest_plugin.py` (no other ulog/ file touched).
  - [x] 6.7 Manually invoke `pytest tests/test_pytest_plugin.py -k "ulog_db or summary"` and confirm the 8 new tests run together in < 15s.

---

## Dev Notes

### What this story actually adds vs. what was already done

| Requirement | Status before Story 1.5 | Story 1.5 work |
|---|---|---|
| `--ulog-db` flag REGISTERED | ✅ Story 1.1 | none |
| `--ulog-db` enables the gate | ✅ Story 1.1 | none |
| `--ulog-db` triggers `ulog.setup` (FR67) | ❌ — gate enables but no setup is called → records have nowhere to land | **NEW: auto-setup logic in `pytest_configure`** |
| `--ulog-disable` flag REGISTERED | ✅ Story 1.1 | none |
| `--ulog-disable` short-circuits gate (FR68) | ✅ Story 1.1 + 1.2 | regression-only |
| `--ulog-summary` flag REGISTERED | ✅ Story 1.1 | none |
| Summary line printed at session end (FR69) | ❌ — flag exists but no hook | **NEW: `pytest_terminal_summary` hook + outcome counter** |
| `-q` suppresses summary | ❌ | **NEW: verbose-level check in summary hook** |

So Story 1.5 is **80% real implementation, 20% tests-locking-existing-behavior** — distinct from Stories 1.3/1.4 which were tests-only.

### Critical wiring detail: counter increment placement

The session-level counter (Task 2.2) lives on `config._ulog_session_stats: dict[str, int]`. It MUST be incremented from `_emit_outcome_records`, not from a separate hook, because:

1. The protocol hookwrapper's `finally`-block call to `_emit_outcome_records` runs EXACTLY ONCE per item, regardless of skip/fail/error path.
2. The body's verdict is computed inside `_classify(reports)` — the same place that drives the level/msg/extra of the outcome record. Re-deriving the verdict in a separate hook risks divergence (e.g., if `_classify` evolves, the counter and the records would disagree).
3. The early-return path (`if not reports`) in `_emit_outcome_records` (Story 1.2 review patch M2) emits an `errored` record. The counter MUST also increment there — it's a separate code path that's easy to miss.

### `--ulog-db` URL construction — preserve relative paths

Story 1.4's Test 4.1 used `db_path.as_posix()` for the SQLAlchemy URL because the test path was always absolute. The CLI flag accepts BOTH absolute (`/tmp/X.sqlite`) and relative (`./mytests.sqlite`) paths. SQLAlchemy's `sqlite:///` URL form expects either:
- `sqlite:///absolute/path` → 3 slashes + absolute (e.g. `sqlite:////tmp/X.sqlite`)
- `sqlite:///relative/path` → 3 slashes + relative (e.g. `sqlite:///./mytests.sqlite`)

So `f"sqlite:///{ulog_db}"` works for both forms IF `ulog_db` is the user's literal string. **Don't normalize via `Path()` — that would strip the leading `./` and convert to absolute.** Trust the user's input.

Edge case: if `ulog_db.startswith("/")`, the resulting URL is `sqlite:////absolute/path` (4 slashes). That's the correct SQLAlchemy form for absolute paths. The user just typed `--ulog-db /tmp/X.sqlite` and expects records to land there.

### Why the `errored` count folds into `failed` for display

PRD-v0.3 §2.1.6 shows the example summary as 3 buckets:
> `ulog: 412 tests, 409 passed, 3 failed, 0 skipped → ulog-web ./logs.sqlite to triage`

Internally Story 1.2 distinguishes 4 outcome strings (`passed`/`failed`/`skipped`/`errored`) — `errored` specifically means a setup-phase failure (fixture raised), not a test-body assertion failure. For triage purposes the user mostly cares "did it pass or did it not?" → folding errored into failed at display time matches the PRD example.

The internal 4-way counter stays for AC6 (the assertion `1 passed + 1 errored → display 1 passed, 1 failed` would be impossible to verify if the counter were already pre-folded). The collapse happens ONCE, at line-formatting time, in `pytest_terminal_summary`.

### `pytest_terminal_summary` hook semantics (relevant pytest internals)

- Signature per pytest 7+ stable contract: `pytest_terminal_summary(terminalreporter, exitstatus, config)`.
- Runs AFTER all items have completed AND pytest's own summary (`====== 5 passed in 0.42s ======`) has been printed.
- `terminalreporter.write_line(line, **markup_kwargs)` writes to pytest's display stream — captured by `pytester.runpytest()` and visible in `result.stdout.str()`.
- `markup_kwargs` accepts `red`, `yellow`, `green`, `bold`. Use `yellow=True` when failed/errored > 0 — matches pytest's own convention for test failures.
- The hook does NOT run if pytest exits early (e.g., collection error, KeyboardInterrupt). That's fine for v0.3 — the summary is informational; users already see pytest's own error output.

### Files being modified — production code touch

#### `ulog/testing/pytest_plugin.py` (UPDATE — significant)

**Current state (post-Story 1.4):** ~310 lines. Has `pytest_addoption` (Story 1.1), `pytest_configure` (Story 1.1), `_get_enabled` (Story 1.1), `_make_test_id` (Story 1.3), `pytest_runtest_protocol` (Story 1.2), `pytest_runtest_makereport` (Story 1.2), `_emit_outcome_records` (Story 1.2 + reviews), `_classify` (Story 1.2), `_longrepr_to_exc` (Story 1.2 + reviews).

**Behavior to preserve:**
- All Story 1.1 + 1.2 + 1.3 + 1.4 hooks and helpers — UNCHANGED EXCEPT for the additions in `pytest_configure` (Task 1) and the counter-increment in `_emit_outcome_records` (Task 2.2 + 2.3).
- The `_ulog_enabled` / `_ulog_reports` / `_ulog_excinfo` attribute pattern — UNCHANGED. Story 1.5 adds `_ulog_db_path` and `_ulog_session_stats` following the same convention.
- Module docstring — append `Story 1.5 owns: --ulog-db auto-setup + --ulog-summary line + -q suppression.`

**What this story changes:**
- `pytest_configure`: add auto-setup branch + `_ulog_db_path` stash + `_ulog_session_stats` initialization (Task 1 + 2.1).
- `_emit_outcome_records`: increment counter at two spots (Task 2.2 + 2.3).
- New `pytest_terminal_summary` hook (Task 3).

**Lines added: ~35-50** (auto-setup branch + counter init + terminal_summary hook + counter increments). No deletions.

#### `tests/test_pytest_plugin.py` (UPDATE — additive)

**Current state (post-Story 1.4):** ~1010 lines after Story 1.4's additions and review patches. 31 tests.

**What this story adds:**
- A new section header (Task 4.1).
- 8 new test functions (Tasks 4.2, 4.3, 5.1-5.6).

**Lines added: ~250-300.** No deletions.

#### Other files (DO NOT MODIFY)

`pyproject.toml`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/`, `ulog/testing/__init__.py`. **Verify with `git diff --stat HEAD --` after the change** — only `ulog/testing/pytest_plugin.py` and `tests/test_pytest_plugin.py` should appear in the production-code diff.

### Story 1.4 lessons applied (carry-forward)

- **Anchor record / count assertions** (Story 1.4 review P2 was a backport of Story 1.3 P3/P4/P6 — same lesson keeps surfacing). For Story 1.5, every test that asserts on counts or summary content should use `==` and document the exact expected value.
- **Make tests order-independent** (Story 1.4 review P6 — class-fixture test). Story 1.5's `test_summary_counts_match_outcomes` runs 4 tests in pytester; the order doesn't affect the summary counts (they're aggregates), so order-independence is automatic. But future tests that assert on per-test details should derive ordering from the records, not hard-code.
- **`@pytest.hookimpl(tryfirst=True)`** when needed (Story 1.4 review P8). The new `pytest_terminal_summary` hook in this story does NOT need `tryfirst` — pytest's own summary already prints first by convention; ours appears after, which is the desired ordering.
- **Graceful empty-DB handling** (Story 1.4 review P5 — `_read_app_records`). Same applies if a Story 1.5 test ever produces zero records: `_read_test_records` would also need the `try/except OperationalError` guard. Apply if needed; otherwise the existing helper is sufficient.

### Architecture references — what to read before coding

| Topic | Read |
|---|---|
| FR67-69 spec | `docs/prds/PRD-v0.3-test-integration.md` §3.5 + §2.1.6 (summary line example) |
| Decision C2 — sub-package | `_bmad-output/planning-artifacts/architecture.md` § "Decision C2" |
| Lazy-import discipline | `_bmad-output/planning-artifacts/architecture.md` § "Implementation Patterns / Lazy-import discipline" — `import ulog` stays lazy inside hook bodies |
| Story 1.1 plugin module current state | `ulog/testing/pytest_plugin.py:60-115` (`pytest_configure` + `_get_enabled`) |
| Story 1.2 outcome path | `ulog/testing/pytest_plugin.py:180-240` (`_emit_outcome_records`) — Task 2.2/2.3 increment site |
| `ulog.setup` signature | `ulog/setup.py:65-193` — verify `handlers=['sql']` + `sql_url=` works at this version |
| `is_configured` truth source | `ulog/setup.py:260-267` |
| Existing test fixture patterns | `tests/test_pytest_plugin.py:124-200` (`_read_test_records`, `_read_app_records`, `_conftest_with_setup`) |

### LLM-Dev anti-patterns to avoid

| Anti-pattern | Why avoid | Correct approach |
|---|---|---|
| Calling `ulog.setup(...)` at module top of `pytest_plugin.py` | Side-effect on import; breaks lazy-import discipline | Lazy `import ulog` inside `pytest_configure` (Story 1.1 / 1.2 pattern) |
| Auto-setup overrides existing host setup (FR67 violation) | Breaks AC2 — host's chosen handlers/path get silently replaced | Check `not ulog.is_configured()` BEFORE calling `setup` |
| Normalizing `--ulog-db` value via `Path(...).resolve()` or `as_posix()` | Strips leading `./` for relative paths, converts to absolute — user surprise | Use the user's literal string as-is in the SQLAlchemy URL |
| Querying SQLite in `pytest_terminal_summary` to count outcomes | Heavy, race-prone (handler may not have flushed), couples summary to storage | Use the in-memory `_ulog_session_stats` counter |
| Re-deriving outcome from reports in the summary hook | The hook doesn't have access to per-item reports; even if it did, divergence with `_classify` is a maintenance hazard | Counter is owned by `_emit_outcome_records` — single source of truth |
| Using `print(..., file=sys.stderr)` for the summary line | Bypasses pytester's capture; tests can't assert on it via `result.stdout.str()` | Use `terminalreporter.write_line(line, ...)` |
| Letting the summary line print when gate is OFF (AC8 violation) | Gate-off means no records were emitted; printing "0 tests" is noise | First check in `pytest_terminal_summary`: `if not _get_enabled(config): return` |
| Letting the summary line print under `-q` | FR69 explicit requirement | Check `config.getoption("verbose") < 0` |
| Hardcoding `4 buckets` in the rendered line (`X passed, Y failed, Z errored, W skipped`) | PRD §2.1.6 example shows 3 buckets; UI consistency matters | Fold `errored` into `failed` for display only; keep 4-way counter internally |
| Forgetting `# type: ignore[attr-defined]` on new `_ulog_*` config attributes | mypy --strict will fail | Add the suppression on every `config._ulog_X = ...` line, matching Story 1.1's `_ulog_enabled` precedent |
| Calling the summary hook for every test (e.g., wiring it as `pytest_runtest_logfinish`) | That fires N times, one per test; the summary is once-per-session | Use `pytest_terminal_summary` — fires exactly once at session end |
| Adding `errored` as a 4th displayed bucket "for completeness" | Diverges from PRD example; user expects 3 buckets | Display 3, count 4 |
| Reading `config._ulog_db_path` directly (without `getattr` default) | If `pytest_configure` short-circuited (e.g., gate already off → still set the attribute), reads must be defensive | Always `getattr(config, "_ulog_db_path", None)` |

### References

- [Source: `docs/prds/PRD-v0.3-test-integration.md`#3.5] FR67-69 — three CLI flag behaviors
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#2.1.6] Summary line example (3-bucket display)
- [Source: `_bmad-output/planning-artifacts/epics.md`#Story 1.5] AC framing
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Decision C2] Sub-package layout
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Implementation Patterns / Lazy-import discipline] `import ulog` stays lazy
- [Source: `_bmad-output/implementation-artifacts/1-2-test-event-recording-start-outcome-finish.md`] `_emit_outcome_records` early-return path (Story 1.2 review M2)
- [Source: `_bmad-output/implementation-artifacts/1-3-test-id-stability-for-parametrized-tests.md`] Anchor-record-count discipline
- [Source: `_bmad-output/implementation-artifacts/1-4-bound-context-propagation-of-test-id.md`] Order-independence + graceful-empty discipline (P5/P6)
- [Source: `ulog/testing/pytest_plugin.py`:62-86] Story 1.1's `pytest_configure` — extension site for Task 1
- [Source: `ulog/testing/pytest_plugin.py`:172-225] Story 1.2's `_emit_outcome_records` — counter increment site
- [Source: `ulog/setup.py`:65-193] `setup` signature — `handlers=['sql']` + `sql_url=` is the auto-setup form
- [Pytest docs] `_pytest.terminal.TerminalReporter.write_line(line, **markup)` — stable since pytest 5.0; `markup` includes `yellow`/`red`/`bold`
- [Pytest docs] `pytest_terminal_summary(terminalreporter, exitstatus, config)` — stable hook contract; runs once at session end after pytest's own summary

### Library / framework versions

- **pytest >= 7.0** (NFR-COMPAT-10). `pytest_terminal_summary` hook signature stable since pytest 5.0; `terminalreporter.write_line` since pytest 4.x.
- **sqlalchemy >= 2.0** (already in `[storage]` extra) — used by `SQLHandler` for the auto-setup path.
- **stdlib `logging` only** for the auto-setup wire-up (`ulog.setup` handles the SQL handler internally).
- **No new dependencies.** `dependencies = []` regression gate stays green.

### Definition of Done — Story 1.5

- [x] `pytest_configure` auto-calls `ulog.setup(handlers=['sql'], sql_url=...)` when `--ulog-db` is set AND `not ulog.is_configured()`.
- [x] `pytest_configure` stashes `config._ulog_db_path` (the CLI value if passed) and initializes `config._ulog_session_stats` with all four outcome keys.
- [x] `_emit_outcome_records` increments the counter on the body-verdict path AND on the `errored` early-return path.
- [x] `pytest_terminal_summary` hook prints the 3-bucket summary line when the plugin is enabled AND not under `-q` AND `--ulog-summary` is on.
- [x] Module docstring lists Story 1.5's ownership.
- [x] 9 new tests covering AC1, AC2, AC4, AC5, AC6, AC7 (both directions), AC8 + the errored-folded-into-failed corollary.
- [x] Test module count: 31 baseline + 9 new = **40 tests** in `tests/test_pytest_plugin.py`. Full suite stays green.
- [x] New helper `_conftest_unconfigure_flush_only()` introduced; tests 4.2 and 5.2 reuse it instead of duplicating the flush body.
- [x] All new tests use `_conftest_with_setup` (host-setup tests) OR `_conftest_unconfigure_flush_only` (auto-setup tests).
- [x] All new tests anchor record/string counts with `==` (no `>=`).
- [x] `mypy ulog/testing/ --follow-imports=silent` clean — new `# type: ignore[attr-defined]` suppressions on `_ulog_db_path` and `_ulog_session_stats` are documented inline.
- [x] `grep '^dependencies' pyproject.toml | grep -q '\[\]'` → exit 0.
- [x] `git diff --stat HEAD -- pyproject.toml` empty (no dep changes).
- [x] `git diff --stat HEAD -- tests/` reports only `tests/test_pytest_plugin.py`.
- [x] `git diff --stat HEAD -- ulog/` reports only `ulog/testing/pytest_plugin.py`.
- [x] Story 1.6 / 1.7 viewer work CAN now assume that `pytest --ulog-db PATH` reliably produces records at PATH.
- [x] AC1-AC9 each verifiable via the corresponding new test or invariant.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (1M context window)

### Debug Log References

- **9/9 new Story 1.5 tests passed first run.** No iteration on test fixtures or implementation needed — the VS step's pre-emptive helper `_conftest_unconfigure_flush_only` and the `_ulog_db_path` "auto-setup-fired only" stash logic both worked first try.
- **mypy clean on first run.** All four new `# type: ignore[attr-defined]` suppressions on `_ulog_db_path` / `_ulog_session_stats` follow the Story 1.1 / 1.2 precedent. The new `_bump_session_stats` helper has plain `(pytest.Config, str) -> None` signature — no ignores needed.
- Final state: `pytest tests/` → **122/122 pass** (113 baseline + 9 new). `mypy ulog/testing/ --follow-imports=silent` → clean. `grep '^dependencies' pyproject.toml | grep -q '\[\]'` → exit 0.

### Completion Notes List

**Implementation summary:**
- Extended `pytest_configure` with the FR67 auto-setup branch: when gate enables AND `not is_configured()` AND `--ulog-db` is set, the plugin calls `ulog.setup(handlers=['sql'], sql_url=f"sqlite:///{ulog_db}")` exactly once. The user's literal path string is preserved in the URL — no `Path()` normalization that would strip leading `./` for relative paths.
- Stashed `config._ulog_db_path` ONLY when auto-setup actually fired (i.e., not when host already configured). This way the summary line's `→ ulog-web <path>` suffix points at where records actually went; if host configured silently, the suffix is omitted (we don't know the host's URL).
- Initialized `config._ulog_session_stats` as a 4-way counter (passed/failed/skipped/errored) at `pytest_configure` time.
- Added `_bump_session_stats(config, outcome)` private helper invoked from two spots in `_emit_outcome_records`: the body-verdict path (after `log.log(level, f"test {final_outcome}", ...)`) and the no-reports `errored` early-return path. The teardown-ERROR path does NOT increment — teardown failures are orthogonal to the body verdict per Story 1.2's AC4.
- Added `pytest_terminal_summary(terminalreporter, exitstatus, config)` hook implementing FR69: gates on `_get_enabled` + `verbose < 0` + `ulog_summary` + `total > 0`; renders the 3-bucket display (`ulog: N tests, X passed, Y failed, Z skipped`) by collapsing the internal `errored` count into `failed`; appends `→ ulog-web <db_path> to triage` when `_ulog_db_path` is set; uses `terminalreporter.write_line(line, yellow=bool(failed_or_errored))`.
- Updated module docstring to declare Story 1.5's ownership.

**Test additions (9 new in `tests/test_pytest_plugin.py`):**
1. `test_ulog_db_auto_configures_setup_when_host_unconfigured` — AC1 / FR67.
2. `test_ulog_db_does_not_override_host_setup` — AC2 / FR67 corollary.
3. `test_summary_line_default_on` — AC4 / FR69 default behavior.
4. `test_summary_line_includes_db_path_when_cli_passed` — AC7 (auto-setup fired).
5. `test_summary_line_omits_db_path_when_host_configured` — AC7 inverse (host configured → no suffix).
6. `test_quiet_mode_suppresses_summary` — AC5 / FR69 `-q` suppression.
7. `test_disabled_plugin_suppresses_summary` — AC8.
8. `test_summary_counts_match_outcomes` — AC6 (2 passed + 1 failed + 1 skipped → exact counts).
9. `test_summary_errored_counts_as_failed_for_display` — AC4 corollary (fixture error → 4-way internal but 3-way display).

Plus a new helper `_conftest_unconfigure_flush_only()` placed next to `_conftest_with_setup` for tests that exercise the auto-setup path (no host setup → plugin's auto-setup is the wire-up; conftest only needs the unconfigure-flush).

**ACs satisfied:**
- AC1 ✅ FR67 — `test_ulog_db_auto_configures_setup_when_host_unconfigured`
- AC2 ✅ FR67 corollary — `test_ulog_db_does_not_override_host_setup`
- AC3 ✅ regression-only (Story 1.2's `test_disabled_plugin_emits_nothing` still passes)
- AC4 ✅ FR69 — `test_summary_line_default_on` + corollary `test_summary_errored_counts_as_failed_for_display`
- AC5 ✅ FR69 `-q` — `test_quiet_mode_suppresses_summary`
- AC6 ✅ — `test_summary_counts_match_outcomes`
- AC7 ✅ — `test_summary_line_includes_db_path_when_cli_passed` + inverse `test_summary_line_omits_db_path_when_host_configured`
- AC8 ✅ — `test_disabled_plugin_suppresses_summary`
- AC9 ✅ — only `ulog/testing/pytest_plugin.py` and `tests/test_pytest_plugin.py` modified

**Validation:**
- `pytest tests/`: **122/122 pass** (113 baseline + 9 new). `tests/test_pytest_plugin.py`: **40 tests** (31 baseline + 9 new).
- `mypy ulog/testing/ --follow-imports=silent`: clean.
- `grep '^dependencies' pyproject.toml | grep -q '\[\]'`: PASS (NFR-DEP-50 / SC4 regression gate).
- `git diff --stat HEAD -- pyproject.toml`: empty.
- `git diff --stat HEAD -- tests/`: only `tests/test_pytest_plugin.py` modified.
- `git diff --stat HEAD -- ulog/`: only `ulog/testing/pytest_plugin.py` modified.

**Out-of-scope deliberately deferred:**
- Recovering the host's configured `sql_url` (introspecting `_ulog_managed` SQL handlers) so the summary suffix can show the host's path → v0.4 enhancement story.
- `--ulog-summary=off` / negation flag → FR69 doesn't define a way to turn the summary off besides `-q`. Adding a negation flag is out of scope.

### File List

**Modified:**
- `ulog/testing/pytest_plugin.py` (+~75 lines: auto-setup branch in `pytest_configure`, `_bump_session_stats` helper, two counter-increment call sites in `_emit_outcome_records`, `pytest_terminal_summary` hook, updated module docstring)
- `tests/test_pytest_plugin.py` (+~210 lines: section header + `_conftest_unconfigure_flush_only` helper + 9 new test functions)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (1-5 status: ready-for-dev → in-progress → review)

**Untouched (verified via git diff):**
- `pyproject.toml`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/*`, `ulog/web/*`, `ulog/testing/__init__.py`. All other files under `tests/`.

### Change Log

| Date | Change | Rationale |
|---|---|---|
| 2026-05-06 | Added `--ulog-db` auto-setup branch in `pytest_configure` | FR67 — until now, `--ulog-db` only enabled the gate; nothing actually called `ulog.setup`, so records had nowhere to land. Auto-setup wires up the SQL handler when (gate enabled) AND (no host setup) AND (--ulog-db set). |
| 2026-05-06 | `config._ulog_db_path` stashed only when auto-setup actually fired | AC7 — guarantees the summary line's `→ ulog-web <path>` suffix points at where records actually went. If host configured silently, omit the suffix rather than mislead. |
| 2026-05-06 | `config._ulog_session_stats` 4-way counter; rendered as 3-way | AC6 / PRD-v0.3 §2.1.6 — internal counter distinguishes errored from failed (preserves Story 1.2 classification fidelity); rendered line collapses errored→failed to match the PRD's 3-bucket display. |
| 2026-05-06 | `_bump_session_stats` helper called from two sites in `_emit_outcome_records` | Centralizes the increment logic; defensive `getattr` default keeps it safe if a hypothetical caller invokes the function before `pytest_configure` populated the attribute. |
| 2026-05-06 | `pytest_terminal_summary` hook | FR69 — prints the one-line session summary at session end. Suppressed under gate-OFF / `-q` / `--ulog-summary=False` / zero-items-ran (covers `--collect-only`). |
| 2026-05-06 | New helper `_conftest_unconfigure_flush_only()` in tests | Eliminates duplication between Tasks 4.2 and 5.2 (auto-setup tests both need a host conftest with ONLY unconfigure-flush, no setup call). Distinct semantics from `_conftest_with_setup`. |
| 2026-05-06 | 9 new tests covering AC1-AC8 + errored-folded-into-failed corollary | Locks the FR67/FR69 behavior with literal-output assertions on the rendered summary line. |
| 2026-05-06 | Code review patches (P1-P6) applied | 3 reviewers in parallel (Blind Hunter + Edge Case Hunter + Acceptance Auditor) flagged 23 findings. 6 patched: P1 reordered `pytest_configure` so gate + stats dict are set BEFORE `ulog.setup` attempt (so a setup-raise leaves a coherent config state), P2 moved counter bumps BEFORE `log.log`/`log.error` calls (so a logging-raise doesn't undercount the summary), P3 tightened `test_summary_line_default_on` to the full literal ulog line (bare `"2 passed"` collides with pytest's own summary line — would pass even if our line was deleted), P4 added positive-line presence assertion to AC7 inverse test (catches vacuous-pass if the entire summary suppressed), P5 initializes `_ulog_session_stats` only on enabled=True (cleaner state in disabled runs), P6 added `@pytest.hookimpl(trylast=True)` to `pytest_terminal_summary` for ordering relative to pytest's own summary. 1 deferred (broader f-string injection hardening on `_conftest_with_setup` — touches Stories 1.2/1.4). 16 dismissed with rationale. |

### Review Findings (added by `bmad-code-review` 2026-05-06, Sonnet 4.6 fresh-eyes — 3 parallel reviewers)

**Patches applied (6):**

- [x] [Review][Patch] P1: `pytest_configure` reordered — `_ulog_enabled` + stats dict set BEFORE `ulog.setup` call [`ulog/testing/pytest_plugin.py:91-118`]. If `ulog.setup` raises (bad path, missing SQLAlchemy, etc.), downstream hooks still see a coherent gate state instead of falling back to the `getattr(..., False)` default and silently disabling. Source: Blind Hunter HIGH + Edge Case Hunter HIGH (convergent).
- [x] [Review][Patch] P2: counter bumps moved BEFORE `log.log`/`log.error` calls in `_emit_outcome_records` [`ulog/testing/pytest_plugin.py:240-265`]. Story 1.2's H1 patch wraps `_emit_outcome_records` in try/except so unbind always runs — but if `log.log` itself raises (broken handler), the counter wouldn't increment under the old order, leading to an undercount in the summary. Bumping first keeps counts honest. Source: Blind Hunter HIGH.
- [x] [Review][Patch] P3: `test_summary_line_default_on` assertion tightened to full literal `"ulog: 3 tests, 2 passed, 1 failed, 0 skipped"` [`tests/test_pytest_plugin.py:766-769`]. Bare substrings like `"2 passed"` also appear in pytest's own summary line — they'd pass even if our `pytest_terminal_summary` was deleted. The full literal anchors the assertion to our specific output. Source: Blind Hunter MED.
- [x] [Review][Patch] P4: `test_summary_line_omits_db_path_when_host_configured` adds positive-line assertion (`"ulog: 1 tests, 1 passed, 0 failed, 0 skipped" in output`) before the negative `"→ ulog-web" not in output` check [`tests/test_pytest_plugin.py:799`]. The negative-only form passed vacuously if the entire summary was suppressed for unrelated reasons; positive + negative makes the test diagnose actual suffix-omission behavior. Source: Blind Hunter MED.
- [x] [Review][Patch] P5: `config._ulog_session_stats` initialized only when `enabled=True` [`ulog/testing/pytest_plugin.py:113-118`]. Disabled runs no longer carry a populated counter dict on `config`. Cleaner state; defensive guards in `_bump_session_stats` continue to handle the missing-attribute case. Source: Blind Hunter MED.
- [x] [Review][Patch] P6: `pytest_terminal_summary` decorated `@pytest.hookimpl(trylast=True)` [`ulog/testing/pytest_plugin.py:1037`]. Ensures our line prints AFTER pytest's own session-end summary rather than before (the LIFO default for unordered hooks). Cosmetic but expected by users. Source: Blind Hunter LOW.

**Deferred (1):**

- [x] [Review][Defer] D1: `pytester.makeconftest(f"...")` f-string injection vulnerability on paths containing quotes/backslashes — broader concern affecting `_conftest_with_setup` (Story 1.2) and inline conftests in Story 1.4's `test_test_id_unbound_after_session`, not specific to Story 1.5. Reason: Linux `/tmp/pytest-of-USER/...` paths don't contain quotes; Windows paths with backslashes would need separate handling that's better tackled as a hardening pass once Story 1.10 (xdist + Windows) opens that surface. Source: Blind Hunter MED.

**Dismissed with rationale (16):**

| # | Finding | Source | Why dismissed |
|---|---|---|---|
| 1 | `terminalreporter.write_line(yellow=...)` is invalid kwarg, summary line silently vanishes | Blind HIGH | Empirically false. Pytest's `TerminalReporter.write_line(msg, **markup)` accepts `yellow=True/False` as documented `**markup` kwargs. The 9 Story 1.5 tests' assertions on `result.stdout.str()` find the rendered line — proves the line IS written. The Blind Hunter speculated about "silently vanishes"; the empirical green-ness disproves it. |
| 2 | Future `_classify` outcome string drops counter silently | Edge MED | The outcome key set is fixed by spec (Story 1.2). Future stories that add outcomes are responsible for updating both `_classify` AND the counter init dict — the type of change that touches both files together. The defensive `outcome in stats` guard prevents crashes; warnings are out of scope. |
| 3 | `config.getoption("verbose")` raises with `-p no:terminal` | Edge MED | If `terminal` plugin is disabled, `pytest_terminal_summary` doesn't fire at all (no terminalreporter to invoke the hook). The `getoption("verbose")` line is unreachable in that scenario. |
| 4 | `--ulog-summary` store_true→default-True makes negation unreachable; suppression branch is dead | Edge MED | Documented intent in code (`defensive for future option-negation flags`). FR69 doesn't require an off-switch beyond `-q`; current option shape is correct. |
| 5 | `_conftest_unconfigure_flush_only` uses default batch_size=100, records may not flush | Edge MED | The conftest's `pytest_unconfigure` flush rescues records via `h.flush()` on `_ulog_managed` handlers. The 9 Story 1.5 tests prove this works empirically (every test asserts on records and they're all green). |
| 6 | f-string with absolute path produces 4 slashes in URL | Edge HIGH | 4 slashes IS the canonical SQLAlchemy form for absolute SQLite paths (`sqlite:////absolute/path`). Not a bug. |
| 7 | f-string with relative path resolves CWD-relative; breaks if fixture chdirs | Edge HIGH (modeling) | Documented in spec — user controls the path; if they chdir mid-session that's their concern. SQLAlchemy resolves at first connect. Not a Story 1.5 bug. |
| 8 | `yellow=True` on no-color terminals silently degrades to plain text | Edge LOW | That's correct behavior — the line text is still written. No information loss. |
| 9 | `total == 0` early-return suppresses on collection errors | Blind LOW | Documented intent: avoid noisy `ulog: 0 tests` output when there's nothing to summarize. Collection errors produce pytest's own ERROR output; the user sees the failure regardless. |
| 10 | f-string injection vulnerability in helpers (D1 broader) | Blind MED | Addressed under D1 (deferred — not Story 1.5 scope). |
| 11 | DoD items "UNVERIFIED" from diff (mypy, deps grep, suite count) | Auditor convention | I actually ran every gate (`pytest tests/` 122/122, mypy clean, deps grep exit 0). Auditor convention marks self-reports as PARTIAL; not a real gap. |
| 12 | `_bump_session_stats` factoring not authorized by spec | Auditor | Auditor itself flagged as "quality improvement within spec intent". Spec's Task 2 used inline `getattr` patterns; the helper consolidates them — strictly cleaner. Not a deviation in spirit. |
| 13 | `sql_batch_size` not passed in auto-setup | Auditor | Confirmed correct per spec Task 1.3 (default `batch_size=100` is intentional for real CLI users — pytester tests use the conftest flush mechanism). |
| 14-16 | Various Story 1.4 / Story 1.3 territory items in cumulative diff | Auditor / Edge | Already reviewed in their respective story CRs; not Story 1.5 scope. |

**Final review verdict:** ✅ **All 9 ACs satisfied · all 6 tasks complete · 6 patches applied · 1 deferred · 16 dismissed with rationale.** Tests: 31 → 40 in `test_pytest_plugin.py`. Full suite: **122/122 verts**. mypy clean. Regression gates PASS. 3-reviewer parallel pass adds 6 net robustness improvements (most notably P1/P2 — making the auto-setup branch fail-safe under exception conditions).
