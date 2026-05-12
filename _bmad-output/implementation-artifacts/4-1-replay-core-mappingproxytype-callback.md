# Story 4.1: `replay()` core + MappingProxyType callback

Status: done

**Epic:** 4 — v0.5 Queryability (replay, correlate, bisect)
**Story key:** `4-1-replay-core-mappingproxytype-callback`
**Implements:** FR98 (replay iteration), Decision C3 (MappingProxyType frozen view).
**Built on:** Story 3.4 (chain writer), Story 3.5 (chain emit + canonical JSON), Story 3.7 (`ulog verify` + chain walk pattern).
**Foundation for:** Story 4.2 (`_REPLAY_ACTIVE` contextvar), Story 4.3 (`replay_to_pytest`), Story 4.4 (DSL parser feeds `where_sql`), Story 4.9 (`replay_records` context manager).

## Story

As a **developer reproducing a production incident locally**,
I want **`ulog.replay(db_path, where=..., on=callback)` to iterate matching records in chain order and call my callback with a read-only frozen view**,
so that **I can analyse the records without risk of mutation** + the same iteration primitive plugs into v4.3 (pytest gen) + v4.4 (DSL) + v4.9 (test fixture).

## Acceptance Criteria

1. **Public function `ulog.replay(db_path, *, where=None, where_fn=None, on=callback, order='chain') -> int`** exposed from the top-level `ulog` namespace. Returns count of records replayed.
2. **Filter dispatch** — exactly ONE of `where: str` (raw SQL WHERE fragment) OR `where_fn: Callable[[Mapping], bool]` (Python predicate). Passing both → `ValueError`. Passing neither → iterates ALL records.
3. **Chain-order iteration** — `ORDER BY chain_pos` when `order='chain'` (default). `order='ts'` also supported (`ORDER BY ts ASC`). Other values → `ValueError`.
4. **Frozen-view callback** — each yielded record is wrapped in `types.MappingProxyType` BEFORE being passed to `on(record)`. The proxy reflects the record dict 1:1 (keys: `id`, `chain_pos`, `ts`, `level`, `logger`, `msg`, `file`, `line`, `exc`, `context`, `immutable`, `record_hash`, `prev_hash`).
5. **Mutation raises TypeError** — `record["msg"] = "modified"` from inside the callback raises `TypeError: 'mappingproxy' object does not support item assignment`. Tested.
6. **Nested mutation does NOT raise** (documented limitation) — `record["context"]["key"] = "x"` succeeds because the inner dict is not frozen. The contract is "shallow read-only"; deep-freeze is out of v0.5 scope (Decision below).
7. **SQL-side filter via `where`** — `where="level = 'ERROR'"` becomes `SELECT … FROM logs WHERE level = 'ERROR' ORDER BY chain_pos`. Parameterless raw SQL (Story 4.4 will add the DSL → safe-SQL parser). SQL injection surface is the user's responsibility for Story 4.1; documented.
8. **Python-side filter via `where_fn`** — applied AFTER SQL iteration; per-record `if where_fn(record): on(record)`. Slower but flexible.
9. **`db_path` resolution** — accepts `Path`, `str` (path or `sqlite:///…` URL). Required arg.
10. **Idempotent / re-entrant** — calling `replay()` twice on the same DB yields identical results (subject to chain-order determinism).
11. **No emit-time side effects in v4.1** — the callback may emit records, but `_REPLAY_ACTIVE` is NOT set in this story (that's Story 4.2). Documented.
12. **Type checking green** — `mypy --strict` clean.
13. **Tests** — `tests/test_replay_core.py`:
    - `test_replay_iterates_all_records_in_chain_order`
    - `test_replay_with_sql_where_filters_correctly`
    - `test_replay_with_where_fn_filters_correctly`
    - `test_replay_passes_both_where_and_where_fn_raises`
    - `test_replay_callback_receives_mappingproxytype`
    - `test_replay_callback_mutation_raises_typeerror`
    - `test_replay_returns_count_of_records_replayed`
    - `test_replay_order_ts_works`
    - `test_replay_order_invalid_raises`
    - `test_replay_on_empty_db_returns_zero`
    - `test_replay_db_path_as_pathlib_and_str_work`
    - `test_replay_db_path_nonexistent_raises_filenotfound`

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/replay.py` (NEW)**
  - [ ] 1.1 — Module docstring referencing FR98, Decision C3, and the Epic-4 cousin features (4.2 contextvar, 4.4 DSL).
  - [ ] 1.2 — `def replay(db_path, *, where=None, where_fn=None, on, order='chain') -> int`. Module-top-level stdlib imports only; SQLAlchemy lazy-imported inside the function.
  - [ ] 1.3 — Row → record dict construction (helper `_row_to_dict(row, columns) -> dict`). Same field order as v0.5 chain schema.
  - [ ] 1.4 — Datetime round-trip: parse SQLite-text `ts` back to `datetime` via the `_parse_ts` helper from `ulog/_cli/cmd_verify.py` (or extract into `ulog/_chain.py` for shared use). **Decision: extract `_parse_ts` to `ulog/_chain.py` as `parse_stored_ts()` so both verify and replay share it.**
  - [ ] 1.5 — JSON columns (`exc`, `context`) parsed back to dicts.
- [ ] **Task 2 — Public namespace export**
  - [ ] 2.1 — Add `from .replay import replay` to `ulog/__init__.py`. Verify `ulog.replay` is importable.
  - [ ] 2.2 — Update `ulog/__init__.py`'s `__all__` if it exists.
- [ ] **Task 3 — Tests in `tests/test_replay_core.py` (NEW)**
  - [ ] 3.1 — Shared fixture `seeded_chain_db(tmp_path)` — seeds 5 chain-mode records of varying level/logger/msg.
  - [ ] 3.2 — 12 tests per AC13.
- [ ] **Task 4 — Validation**
  - [ ] 4.1 — pytest tests/test_replay_core.py → 12 / 12 green.
  - [ ] 4.2 — pytest tests/ → no regression.
  - [ ] 4.3 — mypy / ruff / deptry clean.

## Dev Notes

### What this story is and is NOT

**IN scope:**
- Public `ulog.replay(db_path, *, where, where_fn, on, order)` function.
- Chain-order or ts-order iteration.
- MappingProxyType frozen view per record.
- TypeError on top-level mutation.
- Datetime + JSON column round-trip (reuses pattern from `cmd_verify`).
- 12 tests covering the contract.

**OUT of scope:**
- `_REPLAY_ACTIVE` contextvar → **Story 4.2**.
- `replay_to_pytest` generator → **Story 4.3**.
- DSL parser (`where='resolves="abc"'` style) → **Story 4.4**.
- `correlate()` / `bisect()` → **Stories 4.5 / 4.7**.
- CLI `ulog replay` → **Story 4.8**.
- `replay_records` context manager in `ulog/testing/` → **Story 4.9**.
- Deep-freeze of nested dicts → out forever (cost: would require recursive proxy; doc the shallow contract).
- Write protection during replay → **Story 4.10** (replay write attempt edge case).

### Files

- `ulog/replay.py` (NEW) — single function + helpers.
- `ulog/__init__.py` (UPDATE) — public export.
- `ulog/_chain.py` (UPDATE) — extract `parse_stored_ts(raw)` from `_cli/cmd_verify.py:_parse_ts` for shared use.
- `ulog/_cli/cmd_verify.py` (UPDATE) — replace inline `_parse_ts` with import from `_chain.parse_stored_ts`. Keep the local name as alias for module-internal consistency.
- `tests/test_replay_core.py` (NEW).

### Architecture compliance

- **Decision C3 (MappingProxyType):** [Source: architecture.md, lines 693-...]. Locked: the callback receives a frozen view.
- **FR98 (replay iteration):** [Source: PRD-v0.5 §3.3].
- **Enforcement #2 (Lazy SQLAlchemy):** import inside the function body, never module-top.
- **Stdlib only at module top:** `types.MappingProxyType`, `pathlib.Path`, `collections.abc`. Stdlib `datetime` + `json` (already in `_chain.py`).

### Library / framework requirements

- Python 3.10+ (`types.MappingProxyType` exists since 3.3; the function `__getitem__` typing nuance works with 3.10+).
- SQLAlchemy ≥ 2.0 — already pinned via `[storage]` extra.
- Zero new deps.

### Snippet (concrete implementation guide)

```python
# ulog/replay.py
"""Replay records from a chain DB through a callback (FR98, Decision C3).

`replay(db_path, where=..., on=callback)` walks records in chain order
(default) and yields each as a `types.MappingProxyType` frozen view
to the callback. The Protocol shape feeds Story 4.3 (replay_to_pytest)
and Story 4.9 (replay_records test context manager).
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

_VALID_ORDERS = {"chain", "ts"}


def replay(
    db_path: str | Path,
    *,
    where: str | None = None,
    where_fn: Callable[[Mapping[str, Any]], bool] | None = None,
    on: Callable[[Mapping[str, Any]], None],
    order: str = "chain",
) -> int:
    """Iterate records from a ULog SQL DB and pass each to `on(...)`
    wrapped in `MappingProxyType`.

    Args:
        db_path: SQLite path (Path / str) OR `sqlite:///...` URL.
        where: raw SQL WHERE fragment. Mutually exclusive with where_fn.
        where_fn: Python predicate over the record dict.
        on: callback receiving the frozen-view record.
        order: 'chain' (default; ORDER BY chain_pos ASC) or 'ts'.

    Returns:
        Number of records passed to the callback.

    Raises:
        ValueError: both `where` AND `where_fn` provided, or unknown `order`.
        FileNotFoundError: db_path doesn't point at an existing file.
    """
    if where is not None and where_fn is not None:
        raise ValueError("replay() accepts at most one of `where` / `where_fn`")
    if order not in _VALID_ORDERS:
        raise ValueError(
            f"unknown order {order!r}; valid: {', '.join(sorted(_VALID_ORDERS))}"
        )

    url = _resolve_db_url(db_path)

    from sqlalchemy import create_engine, text

    from ._chain import parse_stored_ts  # extracted from cmd_verify

    engine = create_engine(url, future=True)
    order_clause = "chain_pos" if order == "chain" else "ts"
    sql = (
        "SELECT id, chain_pos, ts, level, logger, msg, file, line, "
        "exc, context, immutable, record_hash, prev_hash "
        f"FROM logs{f' WHERE {where}' if where else ''} "
        f"ORDER BY {order_clause} ASC"
    )

    count = 0
    with engine.begin() as conn:
        for row in conn.execute(text(sql)):
            record: dict[str, Any] = {
                "id": row[0],
                "chain_pos": row[1],
                "ts": parse_stored_ts(row[2]),
                "level": row[3],
                "logger": row[4],
                "msg": row[5],
                "file": row[6],
                "line": row[7],
                "exc": _json.loads(row[8]) if isinstance(row[8], str) else row[8],
                "context": _json.loads(row[9]) if isinstance(row[9], str) else row[9],
                "immutable": row[10],
                "record_hash": bytes(row[11]) if row[11] is not None else None,
                "prev_hash": bytes(row[12]) if row[12] is not None else None,
            }
            if where_fn is not None and not where_fn(record):
                continue
            on(MappingProxyType(record))
            count += 1
    engine.dispose()
    return count


def _resolve_db_url(db_path: str | Path) -> str:
    if isinstance(db_path, str) and db_path.startswith("sqlite:///"):
        return db_path
    path = Path(db_path) if not isinstance(db_path, Path) else db_path
    if not path.exists():
        raise FileNotFoundError(f"replay(): DB not found at {path}")
    return f"sqlite:///{path}"
```

### Test patterns

- Reuse `_seed_chain(tmp_path, n=5)` helper from `tests/test_qa_epic3_e2e.py` style. **Decision: in-file copy for now** (5 lines); extract to a shared `conftest.py` fixture when 3+ test files need it (deferred).
- `test_replay_callback_mutation_raises_typeerror`:
  ```python
  def test_replay_callback_mutation_raises_typeerror(tmp_path):
      db = _seed_chain(tmp_path, n=1)
      captured = []
      def cb(record):
          captured.append(record)
          record["msg"] = "x"  # should raise TypeError
      with pytest.raises(TypeError, match="mappingproxy"):
          replay(db, on=cb)
  ```

### Previous-work intelligence

- **Pattern: shared `parse_stored_ts` helper** — Story 3.7's `cmd_verify._parse_ts` solved the same SQLite-text-ts round-trip. Extract to `ulog/_chain.py` for replay + verify + future bisect/correlate to share. Mirrors how `sha256_record` / `canonical_record_json` were placed in `_chain.py`.
- **Pattern: lazy SQLAlchemy + JSON column unmarshalling** — copied directly from `cmd_verify.run`.
- **Pattern: `_VALID_ORDERS` frozenset for arg validation** — mirrors `_retention.set_min_retention_days` validation style.

### Project context reference

- Repo-wide guardrails: `_bmad-output/project-context.md` (Python 3.10+, mypy strict, zero runtime deps for core).
- Architecture: `architecture.md` §C3 (MappingProxyType), §B1 (replay-is-a-read).
- Epics: `epics.md` Story 4.1 at lines 1311-1326.

### References

- [Source: epics.md, lines 1311-1326] — Story 4.1 AC
- [Source: architecture.md, Decision C3] — MappingProxyType frozen view
- [Source: ulog/_cli/cmd_verify.py:_parse_ts] — pattern reused
- [Source: ulog/_chain.py:canonical_record_json] — module placement precedent
- [stdlib `types.MappingProxyType`] — chosen freezing primitive

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m]

### Completion Notes List

- `parse_stored_ts` extracted from `ulog/_cli/cmd_verify.py:_parse_ts`
  into `ulog/_chain.py` so verify / repair / replay share the same
  SQLite-text-ts round-trip helper. `cmd_verify` and `cmd_repair`
  re-import it as `_parse_ts` (alias preserves the local convention).
- `ulog/replay.py` (NEW): single function `replay(db_path, *, where,
  where_fn, on, order)`. Stdlib-only imports at module top
  (`MappingProxyType`, `Path`, `Mapping`, `Callable`); SQLAlchemy
  lazy-imported inside the function body per Enforcement #2.
- Public namespace: `ulog.replay` added to `__init__.py` + `__all__`.
- 13 / 13 tests in `tests/test_replay_core.py` green: chain-order
  iteration, ts-order, invalid-order, count return, empty DB,
  SQL WHERE filter, Python predicate filter, mutex `where`+`where_fn`
  rejection, MappingProxyType type check, mutation TypeError,
  full record schema (incl. datetime + bytes round-trip), path/str/URL
  inputs, missing DB error.
- 87 affected-area tests green (test_replay_core + cmd_verify +
  cmd_repair + handlers + chain + chain_emit + chain_edge_cases —
  shared helper refactor didn't break anything).
- mypy --strict / ruff check / ruff format / deptry all clean.

### File List

- `ulog/_chain.py` — added `parse_stored_ts(raw)` helper.
- `ulog/_cli/cmd_verify.py` — `_parse_ts` becomes an alias for
  `parse_stored_ts` (local-name preserved for internal consistency).
- `ulog/_cli/cmd_repair.py` — same alias from shared module.
- `ulog/replay.py` (NEW) — `replay(...)` public entry point.
- `ulog/__init__.py` — export + `__all__` entry.
- `tests/test_replay_core.py` (NEW) — 13 tests.
