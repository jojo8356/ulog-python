# Story 3.6: `setup()` new params (integrity, immutable_when, min_retention_days)

Status: done

**Epic:** 3 — v0.5 Storage core & chain integrity
**Story key:** `3-6-setup-new-params-integrity-immutable-when-min-retention-days`
**Implements:** FR90 (immutable_when callable), FR91/FR94 (chain mode toggle), FR92 (min_retention_days configuration surface)
**Built on:** Story 3.5 (chain mode + `integrity` param already wired; this story extends with `'none'` alias + the other two params).
**Foundation for:** Story 3.9 (`ulog purge --before <date>` reads `min_retention_days` to refuse premature deletes).

## Story

As a **developer configuring v0.5**,
I want **`ulog.setup()` to accept `integrity`, `immutable_when`, and `min_retention_days` parameters**,
so that **I can opt into chain mode + immutability + retention floor with a single call**.

## Acceptance Criteria

1. **`integrity='none'`** — accepted as an explicit alias for `None`. Combined valid values: `None`, `'none'`, `'hash-chain'`. Other values still raise `ValueError`.
2. **`immutable_when=callable`** — when set, every record passed to the SQL handler is evaluated. `callable(record: logging.LogRecord) -> bool`. When True, the row is persisted with `immutable=1`; when False (or the callable not set), `immutable=0`. Works in BOTH chain mode and non-chain mode (FR90 is independent of the chain feature — a user might want immutable rows for retention without hash linking).
3. **`min_retention_days=int`** — stored as a process-wide module attribute (`ulog._retention.MIN_RETENTION_DAYS`, defaults to `0` = no floor). `None` or omitted → unchanged. Validated: must be `int` and `>= 0`. `setup(min_retention_days=-1)` raises `ValueError`. `setup(min_retention_days="730")` raises `TypeError`.
4. **`immutable_when` evaluation isolation** — if the callable raises, the row defaults to `immutable=0` (fail-safe per Decision B5: "fail-safe — defaults to NOT immutable so the record persists"). A WARNING is logged once via `warnings.warn(..., RuntimeWarning, ...)` so callable bugs surface in dev. **Not** repeated on every record (would flood) — track a per-handler "warned-once" flag.
5. **Immutable trigger composition** — when `immutable_when` returns True, the row hits the DB with `immutable=1`. Story 3.2's triggers then guarantee subsequent UPDATE/DELETE attempts fail. End-to-end smoke test verifies this.
6. **`integrity='none'` runs the v0.4-compatible path** — chain columns stay NULL, `chain_pos=0`. Identical to `integrity=None`. Verified by the same shape of test as the existing `test_non_chain_mode_unchanged` (Story 3.5).
7. **`immutable_when` works without `integrity='hash-chain'`** — non-chain mode + immutable_when can still mark rows immutable. The buffered/batched flush path applies the same flag (per Decision B5 — implementation in SQL handler, not chain writer).
8. **Type checking green** — `mypy --strict` accepts the new param types. `immutable_when: Callable[[logging.LogRecord], bool] | None = None`.
9. **Tests** — new file `tests/test_setup_v05_params.py`:
   - `test_integrity_none_string_alias_accepted` — `setup(integrity='none')` does not raise.
   - `test_integrity_unknown_value_still_raises` — `setup(integrity='hashes')` → `ValueError`.
   - `test_immutable_when_marks_error_records_immutable` — `lambda r: r.levelno >= ERROR` → ERROR row has `immutable=1`, INFO row has `immutable=0`.
   - `test_immutable_when_does_not_affect_chain_mode_link` — chain mode + `immutable_when` → chain link still verifies AND the marked row is `immutable=1`.
   - `test_immutable_when_callable_raising_falls_back_safe` — callable that raises → row persisted with `immutable=0`. `warnings.warn(RuntimeWarning, ...)` fired ONCE.
   - `test_min_retention_days_stored_globally` — `setup(min_retention_days=730)` → `ulog._retention.MIN_RETENTION_DAYS == 730`.
   - `test_min_retention_days_invalid_values` — negative int → ValueError; string → TypeError.
   - `test_min_retention_days_none_or_omitted_keeps_existing` — `setup(min_retention_days=None)` (or omitted) → MIN_RETENTION_DAYS unchanged from its current value.
   - `test_immutable_trigger_blocks_update_on_immutable_when_marked_row` — end-to-end: immutable_when sets immutable=1; attempt UPDATE on that row → trigger fires.

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/_retention.py` (NEW)** (AC: 3)
  - [ ] 1.1 — Module docstring noting it's a small mutable-state holder for v0.5 retention config; Story 3.9 (`ulog purge`) reads it.
  - [ ] 1.2 — `MIN_RETENTION_DAYS: int = 0` module attribute.
  - [ ] 1.3 — `def set_min_retention_days(n: int) -> None:` — validates type + non-negative; stores into module attribute. Used by setup.
  - [ ] 1.4 — Annotate `MIN_RETENTION_DAYS` clearly so mypy stays happy.
- [ ] **Task 2 — Extend `setup()`** (AC: 1, 2, 3, 8)
  - [ ] 2.1 — Add `immutable_when: Callable[[logging.LogRecord], bool] | None = None` and `min_retention_days: int | None = None` to signature. Update integrity validator to accept `'none'`.
  - [ ] 2.2 — When `min_retention_days is not None`, call `_retention.set_min_retention_days(min_retention_days)`. Validation lives in `_retention`.
  - [ ] 2.3 — Thread `immutable_when` through `_build_handler` → `SQLHandler(..., immutable_when=...)`.
  - [ ] 2.4 — Treat `integrity in ('hash-chain',)` as chain mode; `integrity in (None, 'none')` as non-chain.
- [ ] **Task 3 — `SQLHandler` immutable_when wiring** (AC: 2, 4, 7)
  - [ ] 3.1 — Add `immutable_when: Callable[[logging.LogRecord], bool] | None = None` to `__init__`. Store as `self._immutable_when`.
  - [ ] 3.2 — Initialise `self._immutable_when_warned: bool = False`.
  - [ ] 3.3 — In `_record_to_row(record)`: AFTER building the dict, if `self._immutable_when is not None`, call it with `record`. Catch any exception → log warning once → default to `immutable=0`. Otherwise, store the boolean result as `row["immutable"] = 1 if result else 0`. This applies in BOTH chain and non-chain emit paths because `_record_to_row` is shared.
  - [ ] 3.4 — Existing non-chain path (`flush` via `self._table.insert()`) already sends the row dict to the `logs` table; the `immutable` column is part of the table since Story 3.1, so adding `"immutable"` to the dict simply binds the value. No flush-path changes needed.
- [ ] **Task 4 — Tests** (AC: 9)
  - [ ] 4.1 — New file `tests/test_setup_v05_params.py` with `_isolate` autouse fixture (same shape as test_chain_emit.py).
  - [ ] 4.2 — 9 tests per AC9 list.
  - [ ] 4.3 — For `min_retention_days` tests, reset module state in fixture teardown (reset to 0) so cross-test ordering doesn't leak.
- [ ] **Task 5 — Validation**
  - [ ] 5.1 — `pytest tests/` → all green.
  - [ ] 5.2 — `mypy ulog/` → clean.
  - [ ] 5.3 — `ruff check .` + `ruff format .` → clean.
  - [ ] 5.4 — `deptry` clean.

## Dev Notes

### Files being modified — current state and required changes

#### `ulog/_retention.py` (NEW)

Small module:
```python
"""Retention configuration (Story 3.6 + Story 3.9).

Holds the process-wide `MIN_RETENTION_DAYS` floor configured via
`ulog.setup(min_retention_days=...)`. Story 3.9 (`ulog purge`)
reads this to refuse deletes within the retention window.
"""

from __future__ import annotations

MIN_RETENTION_DAYS: int = 0


def set_min_retention_days(n: int) -> None:
    if not isinstance(n, int) or isinstance(n, bool):
        raise TypeError(
            f"min_retention_days must be int, got {type(n).__name__}"
        )
    if n < 0:
        raise ValueError(f"min_retention_days must be >= 0, got {n}")
    global MIN_RETENTION_DAYS
    MIN_RETENTION_DAYS = n
```

The `isinstance(n, bool)` guard excludes `True`/`False` which `isinstance(bool, int)` would otherwise accept.

#### `ulog/handlers/sql.py` (UPDATE)

- Add `immutable_when` param to `__init__` + store.
- Initialise `_immutable_when_warned = False`.
- In `_record_to_row`: apply the callable, default to 0 on missing-or-raise, set `row["immutable"]`. Important: existing non-chain INSERT via `self._table.insert()` will pick up the `immutable` key automatically because the Table has that column.

Snippet:
```python
def _record_to_row(self, record: logging.LogRecord) -> dict[str, Any]:
    # ... existing bound/exc/context build ...
    row = { ... }
    immutable_flag = 0
    if self._immutable_when is not None:
        try:
            if self._immutable_when(record):
                immutable_flag = 1
        except Exception as exc:
            if not self._immutable_when_warned:
                warnings.warn(
                    f"immutable_when callable raised {type(exc).__name__}: {exc!r}; "
                    "defaulting to immutable=0 (Decision B5 fail-safe)",
                    RuntimeWarning,
                    stacklevel=2,
                )
                self._immutable_when_warned = True
    row["immutable"] = immutable_flag
    return row
```

Add `import warnings` to module imports.

#### `ulog/setup.py` (UPDATE)

- Add `immutable_when` and `min_retention_days` params.
- Update integrity validator: `if integrity not in (None, 'none', 'hash-chain')`.
- Thread `chain_mode = (integrity == 'hash-chain')` (already done; just note `'none'` is non-chain).
- Thread `immutable_when` through `_build_handler` → `SQLHandler`.
- When `min_retention_days is not None`, call `_retention.set_min_retention_days(min_retention_days)`.

### Architecture compliance

- **Decision B5 (`immutable_when` raise → fail-safe to immutable=0):** [architecture.md line 686-690]
- **FR90 (immutable_when callable):** [PRD-v0.5]
- **FR92 (min_retention_days floor):** [PRD-v0.5]
- **Decision B3 / B1 chain separation:** immutable_when is orthogonal to chain — handler-level concern, not chain-writer concern.

### Library / framework requirements

- Python 3.10+ generic syntax (`Callable[..., ...]`).
- Stdlib `warnings`.
- Zero new deps.

### References

- [Source: epics.md, lines 1139-1162] — Story 3.6 acceptance criteria
- [Source: architecture.md, lines 686-690] — Decision B5 (`immutable_when` fail-safe)
- [Source: ulog/setup.py, lines 65-181] — setup signature + handler build
- [Source: ulog/handlers/sql.py, _record_to_row line 346] — row dict builder

## Dev Agent Record

### Agent Model Used
claude-opus-4-7[1m]

### Debug Log References
n/a

### Completion Notes List

- New module `ulog/_retention.py` (tiny) — `MIN_RETENTION_DAYS` int +
  `set_min_retention_days(n)` validator. Rejects `bool` explicitly
  via `isinstance(n, bool)` guard (bool subclasses int).
- `setup()` gained `integrity='none'` alias (valid: `None`, `'none'`,
  `'hash-chain'`), `immutable_when` callable, `min_retention_days`.
- `SQLHandler.__init__` gained `immutable_when` param +
  `_immutable_when_warned` flag. `_record_to_row` evaluates the
  callable, catches exceptions, defaults to `immutable=0` per
  Decision B5 fail-safe, emits a one-shot `RuntimeWarning`.
- Works in BOTH non-chain and chain paths (the immutable flag flows
  through the row dict regardless of which INSERT path runs).
- 12 / 12 new tests in `tests/test_setup_v05_params.py` green.
  Full affected-area suite (82 tests across test_setup,
  test_setup_v05_params, test_handlers, test_chain, test_chain_emit)
  green. `mypy --strict`, `ruff check`, `ruff format`, `deptry` all
  clean. Zero new PyPI deps.

### File List

- `ulog/_retention.py` (NEW) — `MIN_RETENTION_DAYS` config attr +
  `set_min_retention_days` validator.
- `ulog/setup.py` — `setup()` params: `integrity='none'` alias,
  `immutable_when`, `min_retention_days`. Threaded `immutable_when`
  through `_build_handler` to `SQLHandler`. Updated integrity
  validator.
- `ulog/handlers/sql.py` — `__init__` gained `immutable_when` +
  `_immutable_when_warned`. `_record_to_row` evaluates callable,
  fail-safe to immutable=0 on exception, one-shot RuntimeWarning.
  `import warnings` added at module top.
- `tests/test_setup_v05_params.py` (NEW) — 12 tests covering
  integrity-alias, immutable_when (chain + non-chain + raising +
  trigger-blocks-update), min_retention_days (valid/negative/string/
  bool/none-keeps-existing).
