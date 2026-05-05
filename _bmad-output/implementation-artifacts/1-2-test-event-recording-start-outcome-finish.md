# Story 1.2: Test event recording (start, outcome, finish)

Status: done

**Epic:** 1 — v0.3 Test integration
**Story key:** `1-2-test-event-recording-start-outcome-finish`
**Implements:** FR54, FR56, FR57, FR58 (also implicitly grounds FR59 by binding `test_id` — verification of FR59-61 propagation is Story 1.4's scope).
**Source:** `docs/prds/PRD-v0.3-test-integration.md` §3.2 + §2.1.2 schema, `_bmad-output/planning-artifacts/architecture.md`, `_bmad-output/planning-artifacts/epics.md` Story 1.2
**Built on:** Story 1.1 (entry-point + `_get_enabled(config)` gate already exist)
**Foundation for:** Story 1.3 (test_id stability for parametrize), Story 1.4 (verifies application records inherit `test_id`), Stories 1.5-1.8 (consume the records in CLI summary + viewer UI)

---

## Story

As a **pytest user**,
I want **every test to emit at least 2 structured records (`test.started`, `test.outcome`) plus an additional ERROR record on failure with full traceback**,
so that **I can reconstruct what happened during any test run from the log archive alone — closing the "what did this failing test log?" gap that motivated v0.3**.

## Acceptance Criteria

### AC1 — Passing test emits exactly 2 records (FR54, FR58)

**Given** the plugin is enabled (host conftest called `ulog.setup(handlers=['sql'], sql_url=...)`) and a test that passes
**When** the test runs to completion
**Then** the SQL log table contains exactly 2 rows with `logger='ulog.test'` for that `test_id`:
  1. `level='INFO'`, `msg='test started'`, `test_id=<nodeid>`
  2. `level='INFO'`, `msg='test passed'`, `test_id=<nodeid>`, `context.outcome='passed'`, `context.duration_s` is a float ≥ 0, `context.phase='call'`

### AC2 — Failing test emits 3 records with traceback (FR54, FR56)

**Given** a test that fails on `assert False`
**When** the test runs
**Then** the SQL log table contains exactly 3 rows with `logger='ulog.test'`:
  1. `level='INFO'`, `msg='test started'`, `test_id=<nodeid>`
  2. `level='ERROR'`, `msg='test failed'`, `test_id=<nodeid>`, `context.outcome='failed'`, `context.duration_s≥0`, `context.phase='call'`
  3. `level='ERROR'`, `msg` matches the assertion error text (e.g. `'AssertionError: assert False'`), `test_id=<nodeid>`, `context.exc.type='AssertionError'`, `context.exc.msg` non-empty, `context.exc.tb` is a non-empty list of strings sourced from `report.longrepr`.

### AC3 — Phase field on outcome record (FR57)

**Given** any pytest test
**When** the outcome record is emitted
**Then** `context.phase` is one of `'setup'`, `'call'`, or `'teardown'` reflecting where the verdict was decided. Specifically:
  - Pass or fail at `call` phase → `phase='call'`.
  - Setup-phase failure (e.g. fixture raised) → `phase='setup'`, `outcome='errored'`.
  - Teardown-phase failure → outcome record carries `phase='call'` (the test's own verdict) AND a SEPARATE ERROR record is also emitted with `phase='teardown'` (see AC4).

### AC4 — Teardown failure produces a separate ERROR record (FR57)

**Given** a fixture whose teardown raises an exception, but whose test body passes
**When** the test runs to completion
**Then** in addition to the 2 standard records (started + passed), a 3rd ERROR record is emitted with `level='ERROR'`, `context.phase='teardown'`, `context.exc` populated from the teardown's `report.longrepr`. The `outcome` record itself stays `outcome='passed'` (the test body passed) — the teardown is reported orthogonally.

### AC5 — Duration sourced from `report.duration` (FR58)

**Given** the outcome record has `context.duration_s`
**When** inspected
**Then** `duration_s` is a float computed as the SUM of `report.duration` across all phases (`setup` + `call` + `teardown`). For a fast pass, `duration_s` is ≥ 0 and < 1.0; for a `time.sleep(0.05)` test, `duration_s` is ≥ 0.05.

### AC6 — Records carry `test_id` from logstart through logfinish

**Given** the plugin is enabled
**When** records are emitted at any point during the test (started, outcome, additional ERROR records)
**Then** every record's `test_id` (in the `context` payload) equals `item.nodeid`. The bind happens before "test started" is emitted; the unbind happens after the last record (including teardown ERROR if any) is emitted. Records emitted by application code or fixtures DURING the test ALSO inherit `test_id` automatically via contextvars (this is FR60/61, formally verified in Story 1.4 — Story 1.2 just sets up the binding).

### AC7 — Plugin disabled gate is fully respected

**Given** `_get_enabled(config) is False` (no host setup, no `--ulog-db`, OR `--ulog-disable` was passed)
**When** any pytest test runs
**Then** ZERO records with `logger='ulog.test'` are emitted. `ulog.bind`/`ulog.unbind` are never called. The hooks short-circuit on the gate check before any side effect.

### AC8 — Logger name `ulog.test` per PRD-v0.3 §2.1.2 schema

**Given** any record emitted by the plugin's hooks
**When** inspected
**Then** `logger='ulog.test'` (NOT `ulog`, NOT `ulog.testing`, NOT the user's logger). All records use `ulog.get_logger("ulog.test")` as the producer.

---

## Tasks / Subtasks

- [x] **Task 1** — Implement `pytest_runtest_protocol(item, nextitem)` as the lifecycle wrapper (AC1, AC6, AC7, AC8)
  - [x] 1.1 Add a new `@pytest.hookimpl(hookwrapper=True)` decorated function `pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None, None, None]` to `ulog/testing/pytest_plugin.py`.
  - [x] 1.2 First line of body: `if not _get_enabled(item.config): yield; return` — short-circuit when the gate is False (AC7).
  - [x] 1.3 Lazy-import `ulog` inside the function body (NOT at top — same pattern as `pytest_configure` per Story 1.1 convention).
  - [x] 1.4 Compute `test_id = item.nodeid` (parametrize-included by pytest's nodeid format — Story 1.3 will verify stability semantics; Story 1.2 just uses what pytest gives us).
  - [x] 1.5 Acquire the test-event logger: `log = ulog.get_logger("ulog.test")` (AC8). Cache the reference for the function — do NOT cache module-level (would re-bind across tests).
  - [x] 1.6 Bind `test_id`: `ulog.bind(test_id=test_id)`. The yield from this hookwrapper happens AFTER the bind — fixtures and the test body see `test_id` in their context (FR60/61 grounding).
  - [x] 1.7 Emit `test started` record: `log.info("test started")` BEFORE `yield`. With `test_id` already bound, this record carries `test_id` (AC1 record #1, AC6).
  - [x] 1.8 Wrap the `yield` in a `try` block. The `finally` clause must always run (so unbind happens even on early termination).
  - [x] 1.9 In `finally`: emit the outcome records (Task 3), then `ulog.unbind("test_id")` AS THE LAST OPERATION (AC6 — outcome records still need `test_id` bound).

- [x] **Task 2** — Capture per-phase reports via `pytest_runtest_makereport` hookwrapper (AC2, AC3, AC4, AC5)
  - [x] 2.1 Add `@pytest.hookimpl(hookwrapper=True)` decorated function `pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, None, None]`.
  - [x] 2.2 Short-circuit if gate False: `if not _get_enabled(item.config): yield; return`.
  - [x] 2.3 `outcome = yield` — let pytest produce the report.
  - [x] 2.4 `report = outcome.get_result()` — pytest's `TestReport` object with `.when` (`"setup"`/`"call"`/`"teardown"`), `.outcome` (`"passed"`/`"failed"`/`"skipped"`), `.duration` (float), `.longrepr` (None on pass, exception info on fail).
  - [x] 2.5 Stash on item: `if not hasattr(item, "_ulog_reports"): item._ulog_reports = {}; item._ulog_reports[report.when] = report`. Type-ignore the attribute set: `item._ulog_reports = {}  # type: ignore[attr-defined]` (consistent with `_ulog_enabled` pattern from Story 1.1).
  - [x] 2.6 Note: `pytest_runtest_makereport` is called by pytest 3 times per test (once per phase). The hookwrapper accumulates reports onto the item across calls.

- [x] **Task 3** — Emit outcome records inside `pytest_runtest_protocol`'s `finally` block (AC1-AC5)
  - [x] 3.1 Define an internal helper `_emit_outcome_records(item: pytest.Item, log: logging.Logger) -> None` (or inline; choice up to dev agent).
  - [x] 3.2 Read the stashed reports: `reports: dict[str, pytest.TestReport] = getattr(item, "_ulog_reports", {})`.
  - [x] 3.3 Determine the **final outcome and phase** for the body record:
    - If `setup` failed (exists in reports and `.outcome == "failed"`) → `outcome="errored"`, `phase="setup"`, `failure_report = reports["setup"]`.
    - Else if `call` failed → `outcome="failed"`, `phase="call"`, `failure_report = reports["call"]`.
    - Else if `setup` skipped or `call` skipped → `outcome="skipped"`, `phase=` whichever was skipped, `failure_report = None` (skip is not an error).
    - Else (all phases that ran are passed) → `outcome="passed"`, `phase="call"`, `failure_report = None`.
    - **Teardown is treated separately** (see Task 3.6 below) — teardown failure does NOT change the body's outcome.
  - [x] 3.4 Compute `duration_s = sum(r.duration for r in reports.values())` — total wall time across all phases that ran (AC5).
  - [x] 3.5 Emit the **outcome record** (always, exactly one — AC1 record #2, AC2 record #2, AC3, AC5):
    - `level = logging.ERROR if outcome in ("failed", "errored") else logging.INFO`.
    - `msg = f"test {outcome}"` (e.g. `"test passed"`, `"test failed"`, `"test skipped"`, `"test errored"`).
    - `extra = {"outcome": outcome, "duration_s": duration_s, "phase": phase}`.
    - `log.log(level, msg, extra=extra)`.
  - [x] 3.6 If `failure_report is not None` (i.e. setup or call phase failed), emit the **traceback ERROR record** (AC2 record #3):
    - Convert `failure_report.longrepr` to the JSON shape `{"type": str, "msg": str, "tb": list[str]}` per PRD-v0.3 §2.1.2.
    - `type` and `msg`: prefer `failure_report.longrepr.reprcrash.message.split(":", 1)` if available (split type from message); fall back to `("Unknown", str(failure_report.longrepr))` for non-standard longrepr shapes.
    - `tb`: `str(failure_report.longrepr).splitlines()` is the simplest extraction; richer extraction via `failure_report.longreprtext.splitlines()` if `longreprtext` attribute exists. Either is acceptable — the contract is "non-empty list of strings reflecting the formatted traceback".
    - Emit: `log.error(f"{exc_type}: {exc_msg}", extra={"exc": {"type": exc_type, "msg": exc_msg, "tb": tb_lines}})`.
  - [x] 3.7 If `reports.get("teardown")` exists AND its `.outcome == "failed"`, emit the **teardown ERROR record** (AC4):
    - Convert `reports["teardown"].longrepr` to the same JSON shape.
    - Emit: `log.error(f"teardown failed: {td_exc_msg}", extra={"phase": "teardown", "exc": td_exc_dict})`.
    - This is a SEPARATE record from the body outcome record (AC4). Do NOT mutate the body outcome to `failed` because of teardown.

- [x] **Task 4** — Define a small `_longrepr_to_exc` helper (Tasks 3.6, 3.7)
  - [x] 4.1 Define `_longrepr_to_exc(longrepr: object) -> dict[str, Any]` returning `{"type": str, "msg": str, "tb": list[str]}`.
  - [x] 4.2 Try the rich path first: `if hasattr(longrepr, "reprcrash"):` → use `reprcrash.message` for type+msg.
  - [x] 4.3 Fall back to plain `str(longrepr)` parsing if rich path fails.
  - [x] 4.4 `tb = str(longrepr).splitlines()` — keep traceback formatted as-is.
  - [x] 4.5 Always return a non-empty `tb` list (even if it's just `[str(longrepr)]`).

- [x] **Task 5** — Tests for the new behavior (AC1-AC8)
  - [x] 5.1 Extend `tests/test_pytest_plugin.py` with new tests. Use `pytester` with a host conftest that calls `ulog.setup(handlers=['sql'], sql_url=...)` pointing at `tmp_path / "logs.sqlite"`. After `runpytest()`, read the records back via SQLAlchemy.
  - [x] 5.2 Helper `_read_test_records(db_path: Path) -> list[dict]`: opens SQLite, selects `WHERE logger='ulog.test' ORDER BY id ASC`, returns rows as dicts. Add this helper at the top of the test file (module-private, `_`-prefixed).
  - [x] 5.3 Test `test_passing_test_emits_two_records`: pass test → 2 records, msgs are `"test started"` + `"test passed"`, `outcome=passed`, `duration_s>=0`, `phase=call` (AC1, AC5).
  - [x] 5.4 Test `test_failing_test_emits_three_records`: failing assertion → 3 records, msg #3 starts with `"AssertionError"`, `exc.type='AssertionError'`, `exc.tb` non-empty (AC2).
  - [x] 5.5 Test `test_outcome_record_has_phase_field`: explicitly inspect the outcome record's context for `phase` (AC3).
  - [x] 5.6 Test `test_teardown_failure_separate_record`: a fixture whose teardown raises, test body passes → 3 records (started, passed, teardown ERROR with `phase=teardown`); body outcome stays `passed` (AC4). Use `pytester.makepyfile` with a fixture using `yield` then raising in cleanup.
  - [x] 5.7 Test `test_skipped_test`: `pytest.skip()` → 2 records, outcome record has `outcome=skipped` and level INFO.
  - [x] 5.8 Test `test_records_carry_test_id`: assert every record has `context.test_id == nodeid` (AC6).
  - [x] 5.9 Test `test_records_use_ulog_test_logger`: assert all records have `logger='ulog.test'` (AC8).
  - [x] 5.10 Test `test_disabled_plugin_emits_nothing`: with `--ulog-disable`, no records emitted to the logs table (AC7). Re-use the host setup conftest, just add `--ulog-disable` to the runpytest call.

- [x] **Task 6** — Verify and ship
  - [x] 6.1 `make test` — full regression suite green (89+ tests now: 88 before + 8 new = 96 minimum).
  - [x] 6.2 `mypy ulog/testing/` — no new errors. The `_ulog_reports` and other attribute writes use the same `# type: ignore[attr-defined]` pattern as `_ulog_enabled` (Story 1.1 precedent).
  - [x] 6.3 `grep '^dependencies' pyproject.toml | grep -q '\[\]'` returns 0 (NFR-DEP-50 regression gate).
  - [x] 6.4 `git diff --stat HEAD -- ulog/__init__.py ulog/setup.py ulog/context.py ulog/formatters.py ulog/_color.py ulog/handlers/ ulog/web/` returns empty (protected files unchanged, I5/I6 invariants preserved).

### Review Findings (added by `bmad-code-review` 2026-05-05, Sonnet 4.6 fresh-eyes)

3 reviewers parallèles (Blind Hunter + Edge Case Hunter + Acceptance Auditor) en `model=sonnet`. ~30 findings après dedupe → **12 patches appliqués + 0 deferred + ~15 dismissed avec rationale**.

**Patches HIGH (3 — bugs réels identifiés par convergence Blind+Edge):**

- [x] [Review][Patch] H1: `_emit_outcome_records` raise → `unbind` skipped → `test_id` poisoned in contextvars [`pytest_plugin.py` finally block] — wrapped emission in nested try/except/finally. Source: Blind Hunter HIGH + Edge Case Hunter HIGH (convergent). Fix: garantit que `unbind` + cleanup `_ulog_reports`/`_ulog_excinfo` tournent toujours, même si l'émission lève.
- [x] [Review][Patch] H2: `_ulog_reports` / `_ulog_excinfo` jamais nettoyés → pollution sur reruns (pytest-rerunfailures) [`pytest_plugin.py:_emit_outcome_records` callsite] — `delattr(item, attr)` après emission. Source: Blind Hunter HIGH.
- [x] [Review][Patch] H3: `outcome.get_result()` re-raise si autre plugin a stocké une exception [`pytest_plugin.py:pytest_runtest_makereport`] — try/except autour. Pluggy's `_Result.get_result()` re-throw lifeline if a peer wrapper fails. Source: Edge Case Hunter HIGH.

**Patches MED (4):**

- [x] [Review][Patch] M1: Windows path backslashes dans sqlite URL [`tests/test_pytest_plugin.py:_conftest_with_setup`] — `db_path.as_posix()`. Source: Blind Hunter MED.
- [x] [Review][Patch] M2: Empty `_ulog_reports` → faussement `passed` au lieu de `errored` [`pytest_plugin.py:_emit_outcome_records`] — early return `outcome=errored, phase=setup` if no reports captured. Source: Edge Case Hunter MED.
- [x] [Review][Patch] M3: `":" in message` fragile pour OSError-like (`[Errno 2]...:'/foo'`) [`pytest_plugin.py:_longrepr_to_exc`] — only treat prefix as type if it looks like Python identifier (alnum/`._`). Source: Blind Hunter MED.
- [x] [Review][Patch] M4: Test setup-phase failure manquant (AC3 sub-case + `errored` path untested) — added `test_setup_failure_emits_errored`. Source: Acceptance Auditor MED.

**Patches LOW (5 — nettoyage tests):**

- [x] [Review][Patch] L1: `assert len(records) >= 1` viole anti-pattern table row 8 [`tests/test_pytest_plugin.py:test_records_use_ulog_test_logger`] — tighten à `== 2`. Source: Acceptance Auditor LOW.
- [x] [Review][Patch] L2: `_isolate_logging` manque `"ulog.test"` (Story 1.2's logger name) [`tests/test_pytest_plugin.py:_isolate_logging`] — ajouté à la liste. Source: Acceptance Auditor LOW.
- [x] [Review][Patch] L3: Loose teardown exc.type assertion `or "Exception" in ...` [`test_teardown_failure_separate_record`] — tighten à `== "RuntimeError"`. Source: Acceptance Auditor LOW.
- [x] [Review][Patch] L4: `if db.exists()` guard masquait potentiel vacuous-pass [`test_disabled_plugin_emits_nothing`] — explicit `records = ... if db.exists() else []` avec assertion non-conditionnelle. Source: Edge Case Hunter MED + Acceptance Auditor LOW. Note: ma première tentative (`assert db.exists()`) cassait le test car le schema SQLite est lazy-créé seulement au premier emit, jamais avec `--ulog-disable`. Fixée.
- [x] [Review][Patch] L5: `tb_lines = ... or [str(longrepr)]` dead branch (produces `[""]`) [`pytest_plugin.py:_longrepr_to_exc`] — collapse empty result to `["<no traceback>"]` placeholder. Source: Blind Hunter MED + Edge Case Hunter LOW (convergent).

**Bonus AC5 strengthening:**

- [x] [Review][Patch] AC5 sleep-bound test — added `test_duration_reflects_sleep` (`time.sleep(0.05)` → `duration_s >= 0.05`). Source: Acceptance Auditor LOW (AC5 partial coverage). Catches a hypothetical regression where `duration_s` only sums `call.duration` instead of all phases.

**Deferred (3 — out of scope for Story 1.2):**

- D1: `@pytest.hookimpl(hookwrapper=True)` → `wrapper=True` migration. Pluggy 1.3.0 / pytest 8.1 introduced the new API; current syntax still works in pytest 9.0.3 (no warnings observed). Refactor when pluggy hardens the deprecation, or as part of a dedicated tech-debt story.
- D2: xfail strict / XPASS handling — `excinfo` is None for XPASS, `longrepr` is plain str → `_longrepr_to_exc` falls to `("Unknown", longreprtext)`. Real edge case but not in Story 1.2's explicit scope; PRD-v0.3 doesn't mandate XFail/XPass record shape. Address when v0.3 sees its first xfail-heavy adopter.
- D3: `--setuponly` mode → `_classify` returns `phase='call'` even when call never ran. Exotic pytest mode; not a typical user path. Document if anyone reports it.

**Dismissed (~12 with rationale):**

| # | Finding | Source | Why dismissed |
|---|---|---|---|
| 1 | Teardown failure should flip body outcome | Blind HIGH | **Spec-correct per AC4**: "body outcome stays `passed`" — separate ERROR record for teardown is intentional. Reviewer misinterpreted spec. |
| 2 | `db` undefined in `test_disabled_plugin_emits_nothing` | Blind MED | **False positive** — `db = tmp_path / "logs.sqlite"` IS defined at line 1 of the function body. Diff snippet sent to Blind Hunter was abbreviated; the variable exists. |
| 3 | `_ulog_excinfo` variable naming "deeply misleading" | Blind HIGH | `call` IS the per-phase `CallInfo` argument provided by pytest. Naming convention follows pytest's hook signature; not a bug. |
| 4 | `_read_test_records` no schema validation | Blind MED | If schema is wrong, SELECT returns 0 rows → `assert len(records) == 2` fails LOUDLY with informative error. Test failure surfaces the issue; no silent corruption. |
| 5 | Lazy `import ulog` thread-safety | Blind LOW | Python's import lock serializes module-level imports. Standard pattern; mirrors `pytest_configure`'s lazy import from Story 1.1. |
| 6 | `logging.Logger` annotation incorrect | Blind LOW | `ulog.get_logger()` returns `logging.getLogger(name)` — actual stdlib `logging.Logger`. Annotation correct. Verified `ulog/setup.py:240-248`. |
| 7 | Double failure log if call+teardown both fail | Blind MED | Currently impossible — `_classify` excludes teardown from `failure_report`. Only triggered if a future change introduces teardown classification, which violates AC4. Dismiss as anticipating non-existent path. |
| 8 | `splitlines() or [str(longrepr)]` dead branch | Blind MED + Edge LOW | Addressed under L5 (different code form, same intent). |
| 9 | `_isolate_logging` doesn't `h.close()` (latent leak) | Edge LOW | Latent only: Story 1.2 SQL handlers live inside pytester subprocess scope, cleaned by inner `pytest_unconfigure`. Outer fixture only sees `StreamHandler` (no resource). Defer to dedicated tests-cleanup story. |
| 10 | AC3 setup-failure phase test (Auditor 3) | Auditor LOW | Addressed under M4 (`test_setup_failure_emits_errored`). |
| 11 | AC5 sleep-bound test (Auditor 2) | Auditor LOW | Addressed under bonus patch (`test_duration_reflects_sleep`). |
| 12 | `hookwrapper=True` deprecation note | Auditor LOW | Same as D1 (deferred). |

**Final review verdict:** ✅ **3 HIGH bugs corrigés (réels, non-trivial), 4 MED, 5 LOW + 1 bonus = 13 patches au total. Tests : 98/98 (was 96 + 2 nouveaux). mypy clean. Regression gate PASS. Sonnet 4.6 review pass adds substantive correctness improvements (notably H1 contextvars-leak guard + H3 plugin-interop safety) without changing behavior on the happy path.**

---

## Dev Notes

### Why the `pytest_runtest_protocol` hookwrapper pattern (NOT `pytest_runtest_logstart`/`logfinish`)

PRD-v0.3 FR54 says records emit "at logstart" and "at logfinish". The naive translation is to use those two hooks directly. **Don't.** Reasons:

1. `pytest_runtest_logstart(nodeid, location)` does NOT receive `config` or `item`. Reading the gate `_get_enabled(config)` requires `config`. Accessing it would require either a module-level cached config (a smell + thread-safety risk) or session fixtures that are awkward.
2. `pytest_runtest_protocol(item, nextitem)` with `hookwrapper=True` runs BEFORE setup and AFTER teardown — semantically equivalent to "around logstart and logfinish" — and gives us `item.config` for the gate check.
3. The hookwrapper pattern lets us emit the outcome record AFTER all phase reports are captured by `pytest_runtest_makereport` (Task 2), without needing inter-hook plumbing beyond `item._ulog_reports`.

### The `_ulog_reports` attribute on `pytest.Item`

We stash per-phase reports on the item via `item._ulog_reports`. This is the same monkey-patch pattern as `config._ulog_enabled` from Story 1.1 — pytest tolerates arbitrary attributes on these objects, and `# type: ignore[attr-defined]` is the documented suppression. The attribute lifetime equals the item's lifetime (one test run); no leak.

### test_id format — pytest's `item.nodeid` is already correct

`item.nodeid` returns `"tests/test_foo.py::test_bar"` for non-parametrized and `"tests/test_foo.py::test_bar[True-1]"` for parametrized variants. **Story 1.2 just uses this directly.** Story 1.3 (next) will verify stability and document the contract — but no implementation change there.

### Story 1.1 lessons applied

From Story 1.1's code review (Sonnet 4.6 fresh-eyes):
- **Use `bool(...)` for option checks**, not `is not None`. Empty-string `--ulog-db ''` would have falsely activated the gate. Story 1.2's hooks read `_get_enabled(config)` only — no new option checks needed here, but if you add any option-derived branching, use `bool()`.
- **Don't annotate generator fixtures `-> None`**. Mirror `tests/test_setup.py` exactly: no annotation. Same convention applies to ALL test fixtures touching `yield`.
- **Don't introduce `# type: ignore[operator]`**. Use `pathlib.Path` for `tmp_path`, not `object`.
- **Tighten test patterns** — use specific module paths, not glob `*ulog*`.

### Architecture references — what to read before coding

| Topic | Read |
|---|---|
| Why this story exists (FR coverage) | `_bmad-output/planning-artifacts/epics.md` Story 1.2 (FR54-58) |
| Schema for the records | `docs/prds/PRD-v0.3-test-integration.md` §2.1.2 ("Test event schema") |
| Outcome / phase / traceback contract | `docs/prds/PRD-v0.3-test-integration.md` §3.2 FR54-58 |
| Frozen invariants context | `_bmad-output/planning-artifacts/architecture.md` § "Frozen invariants (PRD-v0.5 §2.4 invariants)" — I5/I6 (stdlib compat must hold) |
| Lazy-import discipline | `_bmad-output/planning-artifacts/architecture.md` § "Implementation Patterns" → "Lazy-import discipline" |
| `is_configured()` + setup contract | `ulog/setup.py:65-193` (`setup()`) and `ulog/setup.py:260-267` (`is_configured()`) |
| Existing test pattern | `tests/test_setup.py:12-23` (`_isolate_logging` fixture) and Story 1.1's `tests/test_pytest_plugin.py` for pytester usage |
| Story 1.1 plugin module current state | `ulog/testing/pytest_plugin.py` (post-1.1 + post-review patches) |

### Files being modified — read before editing

#### `ulog/testing/pytest_plugin.py` (UPDATE)

**Current state (post-Story 1.1):** 79 lines. Has `pytest_addoption` (Story 1.1 owned), `pytest_configure` decorated `@pytest.hookimpl(trylast=True)` (Story 1.1), `_get_enabled(config)` helper (Story 1.1).

**Behavior to preserve:**
- `pytest_addoption` signature and the 3 registered flags — UNCHANGED. Story 1.5 will eventually consume them; Story 1.2 doesn't read or write them.
- `pytest_configure` body — UNCHANGED. The gate is still computed exactly as today.
- `_get_enabled(config) -> bool` — UNCHANGED. Story 1.2 just calls it from inside the new hooks.

**What this story changes:**
- Adds `pytest_runtest_protocol(item, nextitem)` decorated `@pytest.hookimpl(hookwrapper=True)`.
- Adds `pytest_runtest_makereport(item, call)` decorated `@pytest.hookimpl(hookwrapper=True)`.
- Adds `_emit_outcome_records(item, log)` private helper.
- Adds `_longrepr_to_exc(longrepr) -> dict` private helper.

#### `tests/test_pytest_plugin.py` (UPDATE)

**Current state (post-Story 1.1 + post-review):** 6 tests covering AC1-AC4 of Story 1.1. Uses `pytester` fixture, hand-rolled `_isolate_logging` fixture mirroring `test_setup.py`.

**Behavior to preserve:**
- All 6 existing Story-1.1 tests must keep passing — Story 1.2's changes are additive.
- The `pytest_plugins = ["pytester"]` declaration is still required (verified empirically in Story 1.1).
- The `_isolate_logging` autouse fixture pattern stays unchanged — Story 1.2 inherits it.

**What this story adds:**
- `_read_test_records(db_path)` helper at module top.
- 8 new tests (Tasks 5.3-5.10).
- New imports: `import sqlite3` (or `from sqlalchemy import create_engine, MetaData, text` — choose one; sqlite3 stdlib is enough for our test reads).

#### `pyproject.toml` (DO NOT MODIFY)

Story 1.2 introduces no new dependencies. The `[testing]` extra (pytest>=7.0) and `[storage]` extra (sqlalchemy>=2.0) added in earlier stories are sufficient. **Verify with `git diff HEAD -- pyproject.toml` returning empty post-implementation.**

#### Other protected files (DO NOT MODIFY)

Same list as Story 1.1: `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/`. Story 1.2 lives entirely in `ulog/testing/pytest_plugin.py` and `tests/test_pytest_plugin.py`. **Verify post-implementation.**

### Code skeleton — `pytest_runtest_protocol`

```python
import logging
from typing import Generator

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, None, None]:
    """Wrap test execution: bind test_id, emit started+outcome records, unbind."""
    if not _get_enabled(item.config):
        yield
        return

    import ulog
    test_id = item.nodeid
    log = ulog.get_logger("ulog.test")

    ulog.bind(test_id=test_id)
    log.info("test started")
    try:
        yield
    finally:
        # Reports populated by the makereport hookwrapper across phases.
        _emit_outcome_records(item, log)
        ulog.unbind("test_id")
```

### Code skeleton — `pytest_runtest_makereport`

```python
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, None, None]:
    """Capture per-phase reports onto item._ulog_reports for the protocol wrapper."""
    if not _get_enabled(item.config):
        yield
        return

    outcome = yield
    report = outcome.get_result()
    if not hasattr(item, "_ulog_reports"):
        item._ulog_reports = {}  # type: ignore[attr-defined]
    item._ulog_reports[report.when] = report  # type: ignore[attr-defined]
```

### Code skeleton — `_emit_outcome_records` and `_longrepr_to_exc`

```python
def _emit_outcome_records(item: pytest.Item, log: logging.Logger) -> None:
    reports: dict[str, pytest.TestReport] = getattr(item, "_ulog_reports", {})
    final_outcome, final_phase, failure_report = _classify(reports)
    duration_s = sum(r.duration for r in reports.values())

    level = logging.ERROR if final_outcome in ("failed", "errored") else logging.INFO
    log.log(
        level,
        f"test {final_outcome}",
        extra={"outcome": final_outcome, "duration_s": duration_s, "phase": final_phase},
    )

    if failure_report is not None:
        exc = _longrepr_to_exc(failure_report.longrepr)
        log.error(f"{exc['type']}: {exc['msg']}", extra={"exc": exc})

    teardown = reports.get("teardown")
    if teardown is not None and teardown.outcome == "failed":
        td_exc = _longrepr_to_exc(teardown.longrepr)
        log.error(
            f"teardown failed: {td_exc['msg']}",
            extra={"phase": "teardown", "exc": td_exc},
        )


def _classify(
    reports: dict[str, pytest.TestReport],
) -> tuple[str, str, pytest.TestReport | None]:
    """Determine final outcome+phase ignoring teardown (handled separately)."""
    setup = reports.get("setup")
    call = reports.get("call")
    if setup is not None and setup.outcome == "failed":
        return ("errored", "setup", setup)
    if call is not None and call.outcome == "failed":
        return ("failed", "call", call)
    if (setup is not None and setup.outcome == "skipped") or \
       (call is not None and call.outcome == "skipped"):
        return ("skipped", "call", None)
    return ("passed", "call", None)


def _longrepr_to_exc(longrepr: object) -> dict[str, object]:
    """Best-effort extraction to {type, msg, tb} JSON shape."""
    if hasattr(longrepr, "reprcrash"):
        crash = longrepr.reprcrash  # type: ignore[attr-defined]
        message = str(crash.message)
        if ":" in message:
            exc_type, _, exc_msg = message.partition(":")
            exc_type = exc_type.strip()
            exc_msg = exc_msg.strip()
        else:
            exc_type, exc_msg = "Exception", message
    else:
        exc_type, exc_msg = "Unknown", str(longrepr)
    tb_lines = str(longrepr).splitlines() or [str(longrepr)]
    return {"type": exc_type, "msg": exc_msg, "tb": tb_lines}
```

### Code skeleton — test pattern (read-back via sqlite3)

```python
import sqlite3
from pathlib import Path


def _read_test_records(db_path: Path) -> list[dict]:
    """Read ulog.test records from a SQLite log DB. Returns list of dicts in id order."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM logs WHERE logger='ulog.test' ORDER BY id ASC"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def test_passing_test_emits_two_records(pytester: pytest.Pytester, tmp_path: Path) -> None:
    db = tmp_path / "logs.sqlite"
    pytester.makeconftest(f"""
        import ulog
        def pytest_configure(config):
            ulog.setup(handlers=['sql'], sql_url='sqlite:///{db}')
    """)
    pytester.makepyfile("def test_pass(): assert True")
    result = pytester.runpytest()
    assert result.ret == 0

    records = _read_test_records(db)
    assert len(records) == 2
    assert records[0]["msg"] == "test started"
    assert records[1]["msg"] == "test passed"
    # context is a JSON column; sqlite3 returns it as str
    import json
    ctx = json.loads(records[1]["context"])
    assert ctx["outcome"] == "passed"
    assert ctx["phase"] == "call"
    assert ctx["duration_s"] >= 0.0
    assert ctx["test_id"].endswith("::test_pass")
```

(Subsequent tests follow the same pattern — adapt for failure / skip / teardown-fail / disable scenarios.)

### LLM-Dev anti-patterns to avoid

| Anti-pattern | Why avoid | Correct approach |
|---|---|---|
| Using `pytest_runtest_logstart` + `pytest_runtest_logfinish` directly | These hooks don't get `config` — gate check requires plumbing through module state | Use `pytest_runtest_protocol(item, nextitem)` hookwrapper — gets `item.config` |
| Forgetting to short-circuit when gate is False | Plugin would emit records even when disabled — violates AC7 | First line of every hook body: `if not _get_enabled(...): yield; return` |
| Calling `ulog.unbind` BEFORE emitting outcome records | Outcome records would not carry `test_id` — violates AC6 | Order in `finally`: `_emit_outcome_records(...)` FIRST, then `ulog.unbind("test_id")` |
| Importing `ulog` at module top of `pytest_plugin.py` | Breaks lazy-import discipline; loaded even with `--ulog-disable` | Lazy import inside each hook body (consistent with Story 1.1's `pytest_configure`) |
| Using `report.failed` as the outcome key | Pytest's `report.failed` is just a bool; the spec uses `passed`/`failed`/`skipped`/`errored` strings | Read `report.outcome` (string) directly for the `outcome` field |
| Letting teardown failure flip the body's outcome to "failed" | The body's verdict is independent of teardown — violates AC4 | Two separate records: body outcome reflects setup/call only; teardown failure produces an extra ERROR record |
| Computing duration only from the `call` phase | `report.duration` includes only that phase's wall time; the spec wants total wall time | `duration_s = sum(r.duration for r in reports.values())` across all phases |
| Hardcoded record count assertion `assert len(records) >= 2` | Sloppy — masks accidental extra records | Use `==` and document the exact expected count per scenario (AC1: ==2, AC2: ==3, AC4: ==3) |
| Reading records from the SQL DB while the SQL handler is still buffering | The default `batch_size=100` means small test runs may not flush before the test asserts | The SQL handler's `atexit` flush + `close()` on `ulog.setup()` re-call handles this in normal flow. For tests, ensure `pytester.runpytest()` returns (subprocess exit triggers atexit flush) before reading the DB. |
| Calling `ulog.bind(test_id=...)` from a fixture instead of the protocol wrapper | Wrong layer — bind belongs in the wrapper for FR60/61 to work cleanly | Bind in `pytest_runtest_protocol` BEFORE `yield` |
| Annotating `_isolate_logging` or any new generator fixture with `-> None` | Mirror `tests/test_setup.py` exactly: no annotation on generator fixtures | Leave generator fixtures unannotated — convention from existing codebase |
| Introducing `# type: ignore[operator]` because `tmp_path` is mistyped | Story 1.1 review caught this. `tmp_path: pathlib.Path` is the correct annotation | `from pathlib import Path` and annotate explicitly |

### References

- [Source: `docs/prds/PRD-v0.3-test-integration.md`#3.2] FR54-58 test event recording requirements
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#2.1.2] Test event schema (record shape and `logger="ulog.test"`)
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Decision C2] Sub-package `ulog/testing/` housing the plugin
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Implementation Patterns / Lazy-import discipline] pytest top-level allowed; `ulog` stays lazy
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Frozen invariants] I5/I6 — stdlib `logging.getLogger(__name__).info(...)` continues to work; the plugin must not break it
- [Source: `_bmad-output/planning-artifacts/epics.md`# Epic 1 / Story 1.2] business value + AC framing
- [Source: `_bmad-output/implementation-artifacts/1-1-pytest-plugin-entry-point-registration.md`] previous story — `_get_enabled(config)` helper, `# type: ignore[attr-defined]` pattern, `pytester` test pattern
- [Source: `ulog/setup.py`:65-193] `setup()` signature — Story 1.2's tests configure the host via `ulog.setup(handlers=['sql'], sql_url=...)`
- [Source: `ulog/handlers/sql.py`] `SQLHandler` — produces the `logs` table with `context` JSON column that records' `extra={...}` payload lands in
- [Source: `tests/test_setup.py`:12-23] `_isolate_logging` fixture pattern (Story 1.2 inherits the existing one in `test_pytest_plugin.py`)

### Library / framework versions

- **pytest >= 7.0** (NFR-COMPAT-10). `pytester` fixture, `hookimpl(hookwrapper=True)` decorator, `TestReport.outcome` / `.duration` / `.longrepr` / `.when` are all stable across pytest 7.x and 8.x/9.x.
- **sqlalchemy >= 2.0** (already in `[storage]` extra) — used by `SQLHandler` in the test conftest and by the `_read_test_records` helper.
- **stdlib only for `_longrepr_to_exc`** — `str()`, `splitlines()`, `partition(":")`. No regex needed.
- **No new dependencies.** `dependencies = []` regression gate stays green.

### Definition of Done — Story 1.2

- [x] `ulog/testing/pytest_plugin.py` has `pytest_runtest_protocol` (hookwrapper) + `pytest_runtest_makereport` (hookwrapper) + `_emit_outcome_records` + `_classify` + `_longrepr_to_exc` helpers, with all `# type: ignore[attr-defined]` suppressions documented inline.
- [x] `tests/test_pytest_plugin.py` has 8 new tests (Tasks 5.3-5.10) + the `_read_test_records` helper.
- [x] `make test` green — at least 96 tests passing (88 from Story 1.1 + 8 new).
- [x] `mypy ulog/testing/` — no new errors beyond Story 1.1's already-clean state.
- [x] `grep '^dependencies' pyproject.toml | grep -q '\[\]'` returns 0 (NFR-DEP-50 / SC4).
- [x] `pyproject.toml` is unchanged (verified via `git diff HEAD -- pyproject.toml` empty).
- [x] `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/` all unchanged (verified via `git diff --stat HEAD -- ...`).
- [x] All 8 ACs (AC1-AC8) verifiable via the corresponding tests.
- [x] `_get_enabled(config)` is the only authority on plugin enablement — every new hook short-circuits via it (AC7 enforcement).

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (1M context window)

### Debug Log References

- **Initial test run failed: 7/14 failing — records emitted but DB empty.** Captured logs (`INFO ulog.test:pytest_plugin.py:110 test started`) confirmed records WERE produced, but `_read_test_records(db)` returned `[]`. Root cause: `pytester.runpytest()` runs the inner pytest **in-process** by default; the outer test reads the DB before `atexit` triggers `SQLHandler.flush()` (which is the only path to disk in the default `batch_size=100` config). **Fix:** the test conftest helper passes `sql_batch_size=1` and adds a `pytest_unconfigure` that explicitly flushes/closes managed handlers. After fix: 13/14 passing.
- **Last failing test: `test_failing_test_emits_three_records`.** The record was emitted but with `exc.type='Exception'` instead of `'AssertionError'`. Root cause: pytest's `longrepr.reprcrash.message` for a plain `assert 1 == 2` is just `"assert 1 == 2"` without an `AssertionError:` prefix. My `_longrepr_to_exc` had no way to recover the type name from that string. **Fix:** captured `call.excinfo` in `pytest_runtest_makereport` (where it's available) onto `item._ulog_excinfo`, threaded it through to `_emit_outcome_records` → `_longrepr_to_exc(longrepr, excinfo)`. The helper now prefers `excinfo.type.__name__` when present (canonical source) and falls back to the prior reprcrash parsing only when excinfo is missing.
- **mypy --strict on Story 1.2 files:** initially flagged `outcome.get_result()` as `"None" has no attribute "get_result"`. Pytest's type stubs declare hookwrapper yield as `None` even though runtime returns `_Result`. Suppressed with `# type: ignore[attr-defined]` and inline comment, consistent with the `_ulog_enabled` / `_ulog_reports` pattern from Story 1.1.
- Final state: `mypy ulog/testing/ --follow-imports=silent` → `Success: no issues found in 2 source files`.

### Completion Notes List

**Implementation summary:**
- Extended `ulog/testing/pytest_plugin.py` with three new hook-implementations and three helpers, all guarded by `_get_enabled(item.config)` for AC7 compliance. The Story 1.1 surface (option registration + `pytest_configure` + `_get_enabled`) stays unchanged.
- `pytest_runtest_protocol(item, nextitem)` (`hookwrapper=True`): binds `test_id`, emits `"test started"`, yields, calls `_emit_outcome_records`, unbinds. Order in the `finally` block is **emit-then-unbind** so outcome records still carry `test_id` (AC6 requirement).
- `pytest_runtest_makereport(item, call)` (`hookwrapper=True`): captures per-phase `TestReport` onto `item._ulog_reports[report.when]` AND captures `call.excinfo` onto `item._ulog_excinfo[report.when]`. The excinfo capture is the lesson learned from the AssertionError extraction failure.
- `_emit_outcome_records(item, log)`: emits the outcome record (always, exactly one), the traceback ERROR (only when setup or call failed), and the teardown ERROR (only when teardown failed, separately from the body verdict per AC4).
- `_classify(reports)`: pure function determining (outcome, phase, failure_report). Setup-fail → `errored`/`setup`; call-fail → `failed`/`call`; setup or call skipped → `skipped`/<phase>; else → `passed`/`call`. Teardown is deliberately excluded from this classification — its failure is reported orthogonally.
- `_longrepr_to_exc(longrepr, excinfo=None)`: best-effort extraction to `{type, msg, tb}` JSON shape. Prefers `excinfo.type.__name__` when present (reliable); falls back to `reprcrash.message` parsing.

**Test conftest helper `_conftest_with_setup`:**
- Initial implementation used `ulog.setup(handlers=['sql'], sql_url=...)` only — failed because `pytester.runpytest()` runs in-process, bypassing the `atexit` flush.
- Final implementation passes `sql_batch_size=1` AND defines `pytest_unconfigure` that explicitly flushes/closes managed handlers as a belt-and-braces measure.

**Validation:**
- `pytest`: 96/96 pass (88 baseline + 8 new tests for Story 1.2 = 14 total in `test_pytest_plugin.py`).
- `mypy ulog/testing/ --follow-imports=silent`: clean.
- `grep '^dependencies' pyproject.toml | grep -q '\[\]'`: PASS (NFR-DEP-50 / SC4 regression gate).
- `git diff HEAD -- ulog/__init__.py ulog/setup.py ulog/context.py ulog/formatters.py ulog/_color.py ulog/handlers/ ulog/web/ pyproject.toml ulog/testing/__init__.py`: empty (zero changes to protected files; I5/I6 invariants preserved).

**ACs satisfied:**
- AC1 ✅ pass → 2 records (started + passed) — `test_passing_test_emits_two_records`
- AC2 ✅ fail → 3 records, type=`AssertionError`, tb non-empty — `test_failing_test_emits_three_records`
- AC3 ✅ phase field on outcome record — `test_outcome_record_has_phase_field`
- AC4 ✅ teardown failure → separate ERROR with phase=teardown, body outcome stays `passed` — `test_teardown_failure_separate_record`
- AC5 ✅ duration_s ≥ 0 from sum of phase durations — implicit in passing/failing tests
- AC6 ✅ records carry `test_id` matching nodeid — `test_records_carry_test_id`
- AC7 ✅ `--ulog-disable` → zero records — `test_disabled_plugin_emits_nothing`
- AC8 ✅ logger=`ulog.test` — `test_records_use_ulog_test_logger`
- Skipped test path covered too — `test_skipped_test`

**Out-of-scope deliberately deferred:**
- Parametrize stability verification → Story 1.3 (FR55).
- Bound-context propagation contract tests for fixtures and application code → Story 1.4 (FR60/61). Story 1.2's `bind` already lays the groundwork — Story 1.4 adds tests that verify a `log.info()` call inside the test body inherits `test_id`.
- `--ulog-summary` output behavior → Story 1.5 (FR69).
- The deferred finding from Story 1.1 (`_isolate_logging` hardcoded names) is NOT addressed here — Story 1.2 doesn't touch any new logger names beyond what Story 1.1 already cleans up. Will become relevant in Stories 1.3+ if they introduce new names.

### File List

**Modified:**
- `ulog/testing/pytest_plugin.py` (+138 lines: 3 hooks + 3 helpers + import additions)
- `tests/test_pytest_plugin.py` (+205 lines: `_read_test_records` + `_conftest_with_setup` helpers + 8 tests)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (1-2 status: ready-for-dev → in-progress → review; last_updated bumped)

**Untouched (verified via git diff):**
- `pyproject.toml`, `ulog/testing/__init__.py`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/*`, `ulog/web/*`

### Change Log

| Date | Change | Rationale |
|---|---|---|
| 2026-05-05 | Added `pytest_runtest_protocol` hookwrapper to `pytest_plugin.py` | FR54: emit `test started` at logstart-equivalent + `test outcome` at logfinish-equivalent. Hookwrapper around protocol gives access to `item.config` for the gate, unlike bare `pytest_runtest_logstart`/`logfinish` hooks. |
| 2026-05-05 | Added `pytest_runtest_makereport` hookwrapper | Captures per-phase reports + excinfo onto `item._ulog_reports` and `item._ulog_excinfo` for the protocol wrapper to synthesize the outcome records (FR54-58). |
| 2026-05-05 | Added `_emit_outcome_records` + `_classify` + `_longrepr_to_exc` helpers | Encapsulates the outcome logic: body verdict, traceback ERROR on failure, separate teardown ERROR (FR57) on teardown failure, sum-of-phase duration (FR58). |
| 2026-05-05 | `_longrepr_to_exc` accepts optional `excinfo` parameter | `pytest.ExceptionInfo.type.__name__` is the canonical source for exception type. `longrepr.reprcrash.message` strips `ExceptionType:` prefix for plain assertions, making it unreliable. Captured during dev when `test_failing_test_emits_three_records` extracted `type='Exception'` instead of `'AssertionError'`. |
| 2026-05-05 | Added 8 tests in `test_pytest_plugin.py` covering AC1-AC8 | Use `pytester` + `_read_test_records` SQLite read-back. Test conftest sets `sql_batch_size=1` to force per-record flush (in-process pytester doesn't trigger atexit) and adds `pytest_unconfigure` that explicitly closes managed handlers. |
