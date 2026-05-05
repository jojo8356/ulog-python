# Story 1.1: Pytest plugin entry-point registration

Status: ready-for-dev

**Epic:** 1 — v0.3 Test integration
**Story key:** `1-1-pytest-plugin-entry-point-registration`
**Implements:** FR51, FR52, FR53
**Source:** `docs/prds/PRD-v0.3-test-integration.md` §3.1, `_bmad-output/planning-artifacts/architecture.md` Decision C2, `_bmad-output/planning-artifacts/epics.md` Story 1.1
**Foundation for:** Story 1.2 (hook bodies emit `test.started`/`test.outcome` records consume the gating set up here)

---

## Story

As a **pytest user**,
I want **`ulog[testing]` to register the pytest plugin via the standard `pytest11` entry-point**,
so that **`pip install ulog[testing]` followed by `pytest` auto-discovers the plugin without any manual configuration**.

## Acceptance Criteria

### AC1 — Plugin is auto-discovered by pytest

**Given** a fresh project with `pip install -e ".[testing]"` (or `pip install ulog[testing]` from a tarball/wheel)
**When** `pytest --trace-config` is invoked in any directory
**Then** the trace output includes a line listing `ulog` (or `ulog.testing.pytest_plugin`) as a registered plugin
**And** importing `ulog.testing.pytest_plugin` succeeds without ImportError.

### AC2 — Plugin gating is OFF by default (FR52)

**Given** `ulog[testing]` is installed
**And** no host `conftest.py` has called `ulog.setup(...)` (i.e. `ulog.is_configured()` returns False)
**And** the user does NOT pass `--ulog-db`
**When** pytest collects and runs tests
**Then** `pytest_configure(config)` sets `config._ulog_enabled = False` (gating decision recorded)
**And** the plugin makes NO calls to `ulog.bind()` / `ulog.setup()` / `log.info()` at any pytest lifecycle point
**And** no `test.started`-shaped records are emitted (verifiable as: no rows added to any SQLite cache, no JSONL/CSV growth, no records visible to a parallel `ulog.is_configured()` check on root logger).

### AC3 — `--ulog-disable` short-circuits the plugin (FR53)

**Given** `ulog[testing]` is installed
**And** the host's `conftest.py` HAS called `ulog.setup(...)` (so `ulog.is_configured()` returns True) OR the user passes `--ulog-db /some/path.sqlite`
**When** pytest is invoked with `--ulog-disable`
**Then** `pytest_configure(config)` sets `config._ulog_enabled = False` regardless of the host setup or `--ulog-db` presence
**And** the plugin makes NO calls to ulog APIs throughout the session.

### AC4 — Three CLI flags are registered without acting on them yet

**Given** the plugin is loaded
**When** the user runs `pytest --help`
**Then** the help output includes `--ulog-db PATH`, `--ulog-disable`, `--ulog-summary`
**And** all three flags are accepted by argparse without error (their behavior is implemented in Stories 1.2 and 1.5; this story only registers them).

---

## Tasks / Subtasks

- [ ] **Task 1** — Add `[testing]` extra + `pytest11` entry-point to `pyproject.toml` (AC1)
  - [ ] 1.1 Add a new optional-dependencies group: `testing = ["pytest>=7.0"]` (mirrors PRD-v0.3 NFR-COMPAT-10).
  - [ ] 1.2 Add a new top-level table `[project.entry-points.pytest11]` with one entry: `ulog = "ulog.testing.pytest_plugin"`.
  - [ ] 1.3 Verify `pip install -e ".[testing]"` succeeds locally.

- [ ] **Task 2** — Create the `ulog/testing/` sub-package (AC1, foundation for Stories 1.2 and 1.9)
  - [ ] 2.1 Create `ulog/testing/__init__.py` with a module docstring describing the sub-package as the home of `ulog.testing.test_event` (Story 1.9), `ulog.testing.replay_records` (Story 4.9), and the pytest plugin. Set `__all__ = []` for now (Story 1.9 will add `test_event` and `TestSession`).
  - [ ] 2.2 Create `ulog/testing/pytest_plugin.py` with module docstring, `from __future__ import annotations`, and a single top-level `import pytest` (allowed at top level here per architecture.md step-05 lazy-import discipline carve-out — pytest is loaded only when pytest itself imports this module).

- [ ] **Task 3** — Implement `pytest_addoption(parser)` registering the three flags (AC4)
  - [ ] 3.1 Define `pytest_addoption(parser: pytest.Parser) -> None` in `ulog/testing/pytest_plugin.py`.
  - [ ] 3.2 Create a pytest option group named "ulog" via `parser.getgroup("ulog", "ulog test integration")`.
  - [ ] 3.3 Register `--ulog-db` with `action="store"`, `dest="ulog_db"`, `default=None`, `metavar="PATH"`, help text from PRD-v0.3 FR67.
  - [ ] 3.4 Register `--ulog-disable` with `action="store_true"`, `dest="ulog_disable"`, `default=False`, help text from PRD-v0.3 FR68.
  - [ ] 3.5 Register `--ulog-summary` with `action="store_true"`, `dest="ulog_summary"`, `default=True`, help text from PRD-v0.3 FR69. (Default-True is correct per FR69; `-q`/quiet suppression is Story 1.5's concern.)

- [ ] **Task 4** — Implement gating logic in `pytest_configure(config)` with `trylast=True` (AC2, AC3)
  - [ ] 4.1 Define `pytest_configure(config: pytest.Config) -> None` decorated with `@pytest.hookimpl(trylast=True)`.
  - [ ] 4.2 Lazy-import `ulog` inside the function body (NOT at module top — keeps `ulog.testing.pytest_plugin` import cheap when the user has `--ulog-disable`d the plugin and we only need argparse registration). Note: this is a divergence from the architecture.md C2 "pytest may be imported at top level only inside pytest_plugin.py" rule — that rule allows pytest itself, not ulog. ulog stays lazy.
  - [ ] 4.3 Compute the gating decision as: `enabled = (not config.getoption("ulog_disable")) and (ulog.is_configured() or config.getoption("ulog_db") is not None)`.
  - [ ] 4.4 Store the decision on the config object: `config._ulog_enabled = enabled` (use a leading underscore — pytest tolerates arbitrary attributes on `config` and this is the standard plugin pattern for sharing state across hooks).
  - [ ] 4.5 If `--ulog-disable` was passed, `enabled` MUST be False regardless of the host setup or `--ulog-db` presence (AC3).
  - [ ] 4.6 **Critical scheduling note:** by default, pytest entry-point plugins' `pytest_configure` runs BEFORE the user's `conftest.py` `pytest_configure`. Without `trylast=True`, the host's `ulog.setup(...)` call in conftest fires AFTER our gate is computed, so `ulog.is_configured()` returns False and the plugin is incorrectly disabled. `@pytest.hookimpl(trylast=True)` reverses the order, making our `pytest_configure` the LAST `pytest_configure` to run. Story 1.2's hooks (`pytest_runtest_logstart`, etc.) inherit this scheduling correctness because they read the gate via `_get_enabled(config)`.

- [ ] **Task 5** — Add a stable type hint shim for the `_ulog_enabled` attribute
  - [ ] 5.1 Define a small helper `_get_enabled(config: pytest.Config) -> bool: return getattr(config, "_ulog_enabled", False)`. Future stories (1.2 onwards) consume the gate via this helper rather than reading the attribute directly. Keeps mypy --strict happy without a `# type: ignore`.

- [ ] **Task 6** — Add tests (AC1, AC2, AC3, AC4)
  - [ ] 6.1 Create `tests/test_pytest_plugin.py`. Use the `pytester` fixture (built into pytest, no new dep) to run pytest-in-pytest scenarios.
  - [ ] 6.2 Test `test_plugin_is_registered`: invoke a sub-pytest run with `--trace-config` and assert "ulog" appears in the output (AC1).
  - [ ] 6.3 Test `test_gate_off_by_default`: spawn a sub-pytest with no host setup and no `--ulog-db`, assert `config._ulog_enabled is False` after `pytest_configure` (AC2). Use a custom collected hook fixture or a helper plugin module to inspect.
  - [ ] 6.4 Test `test_gate_on_with_host_setup`: spawn a sub-pytest with a `conftest.py` that calls `ulog.setup(...)`, assert `config._ulog_enabled is True`.
  - [ ] 6.5 Test `test_gate_on_with_ulog_db`: spawn a sub-pytest with `--ulog-db /tmp/x.sqlite`, no host setup, assert `config._ulog_enabled is True`.
  - [ ] 6.6 Test `test_ulog_disable_overrides`: spawn a sub-pytest with both host setup AND `--ulog-disable`, assert `config._ulog_enabled is False` (AC3).
  - [ ] 6.7 Test `test_three_flags_in_help`: assert `pytest --help` output (captured via `pytester.runpytest("--help")`) contains the three flag names (AC4).
  - [ ] 6.8 Add the standard `_isolate_logging` autouse fixture at the top of the test module — same shape as `tests/test_setup.py` lines 12-23. This is per architecture.md step-05 "extend existing fixture, don't spawn parallel".

- [ ] **Task 7** — Verify and ship
  - [ ] 7.1 Run `make test` — all existing 70+ tests + new ones pass.
  - [ ] 7.2 Run `make mypy` — no type errors (`mypy --strict`).
  - [ ] 7.3 Run `pytest --trace-config` manually in repo root, confirm `ulog` appears.

---

## Dev Notes

### Why this story is foundational

This is the **lowest-blast-radius story in the entire v0.3-v0.5 roadmap** (per architecture.md step-04 Implementation Sequence). It introduces:

1. The `ulog/testing/` sub-package layout that Stories 1.2-1.11 will fill in.
2. The pytest plugin discovery convention that ALL future test-integration work depends on.
3. The first new optional-dep extra (`[testing]`) since v0.2 (`[storage]`, `[web]`).

If this story ships clean, Stories 1.2-1.11 are mechanical extensions. If it ships with a bug in the entry-point or the gating, every subsequent v0.3 test will be flaky.

### Three frozen invariants this story must respect

From PRD-v0.5 §2.4 + architecture.md "Frozen invariants":

- **I5/I6:** stdlib `logging.getLogger(__name__).info(...)` continues to work in test code. **This story does not touch `ulog/setup.py` or `ulog/context.py`** — those modules stay untouched.
- **NFR-DEP-50 / SC4:** `pyproject.toml dependencies = []` stays unchanged. The `pytest` dep goes into `[project.optional-dependencies] testing`, NOT into `dependencies`. **Verify this by running `grep '^dependencies' pyproject.toml | grep -q '\[\]'` after your change** (Decision E2 / Story 7.9 will gate this in CI; pre-emptively respect it).
- **NFR-REL-10:** the plugin is OFF by default. Installing `ulog[testing]` MUST NOT change the behavior of `pytest` until a user passes `--ulog-db` or sets up host instrumentation in `conftest.py`. AC2 verifies this.

### Architecture references — what to read before coding

| Topic | Read |
|---|---|
| Why this story exists at all | `_bmad-output/planning-artifacts/architecture.md` § "Project Context Analysis" → "FR51-53 plugin discovery" + § "Decision C2 — Pytest plugin packaging: sub-package `ulog/testing/`" |
| Lazy-import discipline carve-out | `_bmad-output/planning-artifacts/architecture.md` § "Implementation Patterns" → "Lazy-import discipline" → bullet about `pytest` being imported at top level **only** in `ulog/testing/pytest_plugin.py` |
| What `is_configured()` does | `ulog/setup.py:260-267` (existing function, returns True iff a `_ulog_managed=True` handler exists on the named logger) |
| Existing test fixture pattern | `tests/test_setup.py:12-23` (the `_isolate_logging` autouse fixture — replicate this shape) |

### Files being modified — read before editing

#### `pyproject.toml` (UPDATE)

**Current state (relevant excerpt):**

```toml
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7.0", "mypy>=1.0"]
storage = ["sqlalchemy>=2.0"]
web = ["django>=5.0", "sqlalchemy>=2.0", "django-lucide>=1.3"]

[project.scripts]
ulog-web = "ulog.web.cli:main"
```

**Behavior to preserve:**
- `dependencies = []` literal (regression gate).
- `dev` extra MUST keep `pytest>=7.0` AND `mypy>=1.0`. Note: `dev` and `testing` will both list `pytest>=7.0`. That's intentional — `dev` is for contributors running `make test`, `testing` is for end-users adopting the plugin in their own projects.
- `storage` and `web` extras unchanged.
- `[project.scripts] ulog-web` unchanged (its removal is Story 7.3, not 1.1).
- `[tool.setuptools.packages.find]` constraint with `include = ["ulog*"]` and `exclude = ["tests*", "vendor*"]` MUST keep working — `ulog/testing/` is a `ulog*` package, so it's auto-discovered by setuptools without further config.

**What this story changes:**

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0", "mypy>=1.0"]
storage = ["sqlalchemy>=2.0"]
web = ["django>=5.0", "sqlalchemy>=2.0", "django-lucide>=1.3"]
testing = ["pytest>=7.0"]                       # NEW

[project.entry-points.pytest11]                 # NEW table
ulog = "ulog.testing.pytest_plugin"
```

#### `ulog/__init__.py` (DO NOT MODIFY)

Current `__all__` is the contract surface (frozen per I5). Story 1.1 does NOT export anything new from the package root — `ulog.testing` is a sub-package accessed via `from ulog.testing import test_event` (Story 1.9 introduces that), not via `from ulog import test_event`. **Leave `ulog/__init__.py` untouched.**

#### `ulog/setup.py` (DO NOT MODIFY)

`ulog.is_configured()` already exists at `setup.py:260-267` and is the gate for FR52. The plugin reads it (lazy-imported in Task 4.2). No changes needed in this file.

#### `ulog/testing/__init__.py` (NEW)

Minimal:

```python
"""ulog.testing — pytest plugin and programmatic test-event APIs.

Sub-package home for v0.3 test integration:
- `pytest_plugin` module — auto-discovered via `[project.entry-points.pytest11]`.
- `test_event` (Story 1.9) — programmatic API for non-pytest runners.
- `replay_records` (Story 4.9) — context manager used by `replay_to_pytest()` output.

The sub-package is loaded only when the `[testing]` extra is installed.
"""
from __future__ import annotations

__all__: list[str] = []  # populated in Story 1.9
```

#### `ulog/testing/pytest_plugin.py` (NEW)

Skeleton (Task 3 + 4 + 5 fill in the bodies):

```python
"""ulog pytest plugin — auto-discovered via `[project.entry-points.pytest11]`.

Story 1.1 owns: option registration + gating decision (`config._ulog_enabled`).
Stories 1.2-1.5 own: lifecycle hooks, test_id propagation, summary output.

The plugin is OFF by default unless either:
  (a) a host `conftest.py` has called `ulog.setup(...)` (i.e.
      `ulog.is_configured()` returns True), OR
  (b) the user passes `--ulog-db PATH` on the pytest CLI.

`--ulog-disable` short-circuits the plugin even when (a) or (b) hold.
"""
from __future__ import annotations

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
        help="Override the destination DB for ulog test records. "
             "Setup is auto-configured if no host setup() exists.",
    )
    group.addoption(
        "--ulog-disable",
        action="store_true",
        dest="ulog_disable",
        default=False,
        help="Short-circuit the ulog pytest plugin even when host "
             "setup() exists or --ulog-db is set.",
    )
    group.addoption(
        "--ulog-summary",
        action="store_true",
        dest="ulog_summary",
        default=True,
        help="Print one-line stderr summary after the session "
             "(default ON; -q suppresses).",
    )


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    """Compute the gating decision and store it on `config._ulog_enabled`.

    `trylast=True` is critical: pytest schedules entry-point plugins'
    `pytest_configure` BEFORE the user's `conftest.py` `pytest_configure`.
    Without it, a host that calls `ulog.setup(...)` in their conftest
    sees their own configure run AFTER ours, and our gate (which reads
    `ulog.is_configured()`) would always be False — disabling the plugin
    even though the user intended to enable it.
    """
    import ulog                                 # lazy: only on pytest config
    enabled = (
        not config.getoption("ulog_disable")
        and (ulog.is_configured() or config.getoption("ulog_db") is not None)
    )
    config._ulog_enabled = enabled              # type: ignore[attr-defined]


def _get_enabled(config: pytest.Config) -> bool:
    """Helper consumed by Story 1.2+ hooks. Defaults False if attr missing."""
    return getattr(config, "_ulog_enabled", False)
```

#### `tests/test_pytest_plugin.py` (NEW)

Use pytest's built-in `pytester` fixture (no new dep, ships with pytest itself). Pattern:

```python
"""Tests for ulog.testing.pytest_plugin (Story 1.1)."""
from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def _isolate_logging():
    """Same shape as tests/test_setup.py — strip _ulog_managed handlers."""
    yield
    for name in (None, "test", "test.sub", "myapp", "qlnes"):
        logger = logging.getLogger(name)
        for h in list(logger.handlers):
            if getattr(h, "_ulog_managed", False):
                logger.removeHandler(h)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def test_plugin_is_registered(pytester: pytest.Pytester) -> None:
    """AC1 — pytest --trace-config lists the ulog plugin."""
    pytester.makepyfile("def test_x(): pass")
    result = pytester.runpytest("--trace-config")
    # The plugin entry-point name is "ulog" (left-hand side of pytest11 entry)
    result.stdout.fnmatch_lines(["*ulog*"])


def test_gate_off_by_default(pytester: pytest.Pytester) -> None:
    """AC2 — gate is False with no host setup and no --ulog-db."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert getattr(pytestconfig, '_ulog_enabled', None) is False
        """
    )
    result = pytester.runpytest()
    assert result.ret == 0


def test_gate_on_with_ulog_db(pytester: pytest.Pytester, tmp_path) -> None:
    """AC2 inverse — --ulog-db sets gate True."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is True
        """
    )
    db = tmp_path / "x.sqlite"
    result = pytester.runpytest("--ulog-db", str(db))
    assert result.ret == 0


def test_gate_on_with_host_setup(pytester: pytest.Pytester) -> None:
    """AC2 inverse — host conftest setup() sets gate True."""
    pytester.makeconftest(
        """
        import ulog
        def pytest_configure(config):
            ulog.setup()  # idempotent — installs _ulog_managed handler
        """
    )
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is True
        """
    )
    result = pytester.runpytest()
    assert result.ret == 0


def test_ulog_disable_overrides(pytester: pytest.Pytester, tmp_path) -> None:
    """AC3 — --ulog-disable short-circuits even when other gating triggers fire."""
    pytester.makepyfile(
        """
        def test_check_gate(pytestconfig):
            assert pytestconfig._ulog_enabled is False
        """
    )
    db = tmp_path / "x.sqlite"
    result = pytester.runpytest("--ulog-db", str(db), "--ulog-disable")
    assert result.ret == 0


def test_three_flags_in_help(pytester: pytest.Pytester) -> None:
    """AC4 — the three flags appear in pytest --help."""
    result = pytester.runpytest("--help")
    output = result.stdout.str() + result.stderr.str()
    assert "--ulog-db" in output
    assert "--ulog-disable" in output
    assert "--ulog-summary" in output
```

### Project Structure Notes

- New sub-package `ulog/testing/` aligns with the existing `ulog/handlers/` pattern (sub-package per concern). See architecture.md step-06 tree at line `ulog/testing/  [+v0.3 sub-package]`.
- Test file `tests/test_pytest_plugin.py` follows the existing `tests/test_<feature>.py` convention (see `tests/test_setup.py`, `test_handlers.py`, `test_web.py`).
- No conflict with the `[tool.setuptools.packages.find]` `include = ["ulog*"]` constraint — `ulog/testing/` matches the pattern.

### LLM-Dev anti-patterns to avoid

| Anti-pattern | Why avoid | Correct approach |
|---|---|---|
| Putting `pytest` in `dependencies = []` (or "to be safe, also add to `[storage]`") | Breaks NFR-DEP-50 / SC4. Regression gate fails. | Only `testing` extra. |
| Importing `ulog` at the top of `pytest_plugin.py` | Slows down `--ulog-disable` invocations + couples plugin discovery to ulog initialization | Lazy-import inside `pytest_configure`. |
| Adding `from ulog.testing import ...` to `ulog/__init__.py:__all__` | Story 1.1 doesn't export anything user-facing. The `test_event` API is Story 1.9. | Leave `ulog/__init__.py` untouched. |
| Implementing `pytest_runtest_logstart` or other lifecycle hooks now | That's Story 1.2's scope. Story 1.1 only registers options + computes the gate. | Stop at `pytest_configure`. |
| Using `getattr(config, "_ulog_enabled")` without default in Story 1.2+ | Crashes if `pytest_configure` was skipped (e.g. plugin disabled by another plugin). | Use the `_get_enabled(config)` helper with `default=False`. |
| Writing a custom conftest.py that imports the plugin manually | Defeats auto-discovery (FR51) and creates a divergent code path. | Trust `[project.entry-points.pytest11]`. |
| Naming the entry-point key something other than `ulog` | The name appears in pytest --trace-config output. AC1's `*ulog*` glob expects exactly this. | `ulog = "ulog.testing.pytest_plugin"`. |
| Forgetting `@pytest.hookimpl(trylast=True)` on `pytest_configure` | Plugin's configure runs BEFORE conftest by default → `ulog.is_configured()` is False even when host did `ulog.setup()` in conftest. Test `test_gate_on_with_host_setup` will fail. | Always decorate `pytest_configure` with `trylast=True`. |

### References

- [Source: `docs/prds/PRD-v0.3-test-integration.md`#3.1] FR51-53 plugin auto-discovery + gating
- [Source: `docs/prds/PRD-v0.3-test-integration.md`#3.5] FR67-69 three CLI flags
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Decision C2] Sub-package `ulog/testing/`
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Implementation Patterns / Lazy-import discipline] pytest top-level import carve-out
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Frozen invariants (PRD-v0.5 §2.4 invariants)] I5/I6 stdlib compat
- [Source: `_bmad-output/planning-artifacts/architecture.md`# Locked-out libraries] no GitPython, no click; argparse stdlib only (relevant: `parser.getgroup` is pytest's argparse facade)
- [Source: `_bmad-output/project-context.md`#Technology Stack & Versions] `pytest>=7.0`, mypy --strict, dependencies = []
- [Source: `ulog/setup.py`:260-267] `is_configured()` — the gate's truth source
- [Source: `tests/test_setup.py`:12-23] `_isolate_logging` autouse fixture pattern

### Library / framework versions

- **pytest >= 7.0** (NFR-COMPAT-10). The `pytester` fixture is built into pytest 7.0+ — no new dep needed for tests. Newer pytest 8.x is forward-compatible with the `pytest11` entry-point convention; nothing in this story requires a specific minor.
- **No other new deps.** ucolor, sqlalchemy, django, django-lucide untouched. `dependencies = []` regression gate must stay green.

### Definition of Done — Story 1.1

- [ ] `pyproject.toml` has `[testing]` extra and `[project.entry-points.pytest11]` table.
- [ ] `ulog/testing/__init__.py` and `ulog/testing/pytest_plugin.py` exist with the contents specified above.
- [ ] `pytest_addoption` registers `--ulog-db`, `--ulog-disable`, `--ulog-summary`.
- [ ] `pytest_configure` computes and stores `config._ulog_enabled` per the gating logic.
- [ ] `_get_enabled(config)` helper exists for Story 1.2+ consumers.
- [ ] `tests/test_pytest_plugin.py` has 6 passing tests covering AC1-AC4.
- [ ] `make test` green (existing 70+ tests + 6 new).
- [ ] `make mypy` green (no new `# type: ignore` beyond the documented `_ulog_enabled` set).
- [ ] `grep '^dependencies' pyproject.toml | grep -q '\[\]'` returns 0 (regression gate manual check).
- [ ] No changes to `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/handlers/*`, `ulog/web/*` (verify with `git diff --stat`).

## Dev Agent Record

### Agent Model Used

_(populated by dev agent at implementation time)_

### Debug Log References

_(populated by dev agent)_

### Completion Notes List

_(populated by dev agent)_

### File List

_Expected files touched at completion:_

- `pyproject.toml` (UPDATE)
- `ulog/testing/__init__.py` (NEW)
- `ulog/testing/pytest_plugin.py` (NEW)
- `tests/test_pytest_plugin.py` (NEW)
