# Story 4.3: `replay_to_pytest()` generator

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-3-replay-to-pytest-generator`
**Implements:** FR100 (incident → regression-test generator).
**Built on:** Story 4.1 (`replay()` iterator), Story 4.9 (`replay_records()` import target).
**Foundation for:** Story 4.4 (DSL — when shipped, the `where=...` arg will accept the DSL string form).

## Story

As a **developer turning a real incident into a permanent regression test**,
I want **`ulog.replay_to_pytest(db_path, where=..., output_path=...)`** to generate `tests/test_incident_<hash>_<topic>.py` with the matching records snapshotted and an assertion stub,
so that the **production incident becomes a CI-gated test** that never silently regresses.

## Acceptance Criteria

1. **`ulog.replay_to_pytest(db_path, *, where=None, where_fn=None, output_path, incident_hash="", topic="incident") -> int`**. Returns the number of records snapshotted into the file.
2. **Generated file structure** — header docstring (auto-generated tag + incident_hash + ISO date + topic), `import pytest`, `from ulog.testing import replay_records`, `INCIDENT_RECORDS = [...]` (frozen list of dict literals), `def test_incident_<hash>_<topic>(): with replay_records(INCIDENT_RECORDS) as session: pass` stub.
3. **Record serialisation slim form** — each entry is `{"ts": "<iso>", "level": str, "logger": str, "msg": str, "file": str, "line": int, "context": dict | None}`. Bytes columns (`record_hash`, `prev_hash`), `chain_pos`, `id`, `immutable`, `is_replay` are NOT serialised (they're chain-internal; replay doesn't need them).
4. **Filename slug** — `test_incident_<hash><suffix>.py` where `<hash>` is the user-supplied incident_hash (truncated/normalised: keep `[0-9a-fA-F]`, lowercase, max 12 chars) + `_<topic>` if topic ≠ "incident" (default). Empty hash → uses the auto-derived sha256 of canonical(input filter).
5. **Auto-overwrite refuses without `--force`** — `replay_to_pytest(..., output_path=existing.py)` raises `FileExistsError` unless `force=True`. Test isolation in CI is the load-bearing concern.
6. **Generated file is valid Python** — `compile(content, output_path, "exec")` succeeds. No syntax errors.
7. **Generated file is runnable via pytest** — `pytest <path>` collects the test, runs the stub (passes by default; user fills in the assertion). The stub body is `pass`, comment-explained: `# TODO: add your regression assertion (e.g. session.matches(...))`.
8. **`INCIDENT_RECORDS` is alphabetically deterministic** within each dict (keys sorted) — diff-friendly across reruns.
9. **No bytes-typed values leak into the generated file** — only stdlib JSON-serialisable types (str, int, None, list, dict, bool). Datetimes become ISO strings.
10. **CLI invocation deferred to Story 4.8** — Story 4.3 ships only the Python API. `ulog replay --to-pytest=...` flag arrives later.
11. **Tests** — `tests/test_replay_to_pytest.py` (NEW):
    - `test_generated_file_is_valid_python`
    - `test_generated_file_contains_required_imports`
    - `test_generated_file_contains_incident_records_list`
    - `test_generated_file_has_test_function_with_replay_records_block`
    - `test_returns_count_of_records_snapshotted`
    - `test_records_are_slim_form_no_bytes_no_chain_pos`
    - `test_ts_serialized_as_iso_string`
    - `test_existing_file_without_force_raises_fileexistserror`
    - `test_existing_file_with_force_overwrites`
    - `test_generated_file_runs_pytest_clean` (subprocess pytest invocation on the generated file)
    - `test_filename_slug_normalises_hash` (`incident_hash="A3F7-C12@"` → `a3f7c12`)
    - `test_topic_appended_to_test_function_name`

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/replay.py` extend with `replay_to_pytest`**
  - [ ] 1.1 — Add function with signature per AC1.
  - [ ] 1.2 — Internal `_slim_record(r) -> dict` strips bytes / chain_pos / id / immutable / is_replay; converts `ts` → ISO string.
  - [ ] 1.3 — Internal `_slugify_hash(h: str) -> str` keeps hex, lowercase, truncates to 12 chars.
  - [ ] 1.4 — Auto-derive hash when `incident_hash=""` — `hashlib.sha256(repr((where, where_fn_name, db_path)).encode()).hexdigest()[:12]`.
- [ ] **Task 2 — Generated-file content**
  - [ ] 2.1 — Use `pprint.pformat(records, sort_dicts=True, width=88)` for the `INCIDENT_RECORDS = [...]` literal.
  - [ ] 2.2 — Header docstring + imports + records literal + test function stub.
- [ ] **Task 3 — Public namespace**
  - [ ] 3.1 — Add `replay_to_pytest` to `ulog/__init__.py` exports + `__all__`.
- [ ] **Task 4 — Tests** (NEW file `tests/test_replay_to_pytest.py`)
- [ ] **Task 5 — Validation** — pytest / mypy / ruff / deptry clean.

## Dev Notes

### Snippet — generator

```python
# in ulog/replay.py
import hashlib
import pprint
import re
from datetime import date, datetime


def replay_to_pytest(
    db_path: str | Path,
    *,
    where: str | None = None,
    where_fn: Callable[[Mapping[str, Any]], bool] | None = None,
    output_path: str | Path,
    incident_hash: str = "",
    topic: str = "incident",
    force: bool = False,
) -> int:
    """Generate a pytest regression test from records matching the filter."""
    out = Path(output_path)
    if out.exists() and not force:
        raise FileExistsError(
            f"replay_to_pytest(): refused to overwrite {out}; pass force=True"
        )

    snapshot: list[Mapping[str, Any]] = []
    replay(db_path, where=where, where_fn=where_fn, on=snapshot.append)

    slim_records = [_slim_record(r) for r in snapshot]
    h_slug = _slugify_hash(incident_hash) or _auto_hash(db_path, where, where_fn)
    t_slug = re.sub(r"[^a-z0-9_]", "_", topic.lower()) or "incident"
    test_fn_name = f"test_incident_{h_slug}_{t_slug}"

    body = f'''"""Auto-generated regression test (ulog.replay_to_pytest).

incident_hash: {h_slug}
topic:         {t_slug}
generated:     {date.today().isoformat()}
source_db:     {db_path}
filter:        {where!r}
"""

import pytest
from ulog.testing import replay_records

INCIDENT_RECORDS = {pprint.pformat(slim_records, sort_dicts=True, width=88)}


def {test_fn_name}():
    """TODO: replace `pass` with your regression assertion. Example:

        assert not session.matches(lambda r: r.extras.get("db_timeout"))
    """
    with replay_records(INCIDENT_RECORDS) as session:
        # TODO: add your regression assertion (e.g. session.matches(...)).
        pass
'''
    out.write_text(body, encoding="utf-8")
    return len(slim_records)


def _slim_record(r: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ts": r["ts"].isoformat() if isinstance(r["ts"], datetime) else r["ts"],
        "level": r["level"],
        "logger": r["logger"],
        "msg": r["msg"],
        "file": r["file"],
        "line": r["line"],
        "context": dict(r["context"]) if r.get("context") else None,
    }


def _slugify_hash(h: str) -> str:
    h_clean = "".join(c for c in h.lower() if c in "0123456789abcdef")
    return h_clean[:12]


def _auto_hash(db_path, where, where_fn) -> str:
    seed = repr((str(db_path), where, getattr(where_fn, "__name__", None)))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
```

### Architecture compliance

- **FR100:** [Source: PRD-v0.5 §3.3] — incident → regression test.
- **Gap G5:** generated tests import `from ulog.testing import replay_records` (Story 4.9 stable signature).
- **I5 invariant:** generator runs offline; no side effect except writing the output file.
- **No new deps:** stdlib `pprint`, `hashlib`, `re`, `datetime`.

### References

- [Source: epics.md, lines 1351-1366] — Story 4.3 AC
- [Source: PRD-v0.5 §3.3, FR100] — regression-test generation
- [Source: ulog/testing/_replay_records.py] — target import for the generated test
- [stdlib `pprint`, `hashlib`] — chosen tools

## Dev Agent Record

### Completion Notes List

- `replay_to_pytest()` added to `ulog/replay.py` with the full
  contract: snapshot via `replay()`, slim each record (strip
  bytes/chain_pos/id/immutable/is_replay; ISO-stringify ts),
  pprint.pformat the list literal, write the file.
- 3 internal helpers: `_slim_record`, `_slugify_hash`,
  `_auto_hash` (sha256 of `(db_path, where, where_fn.__name__)`
  when no explicit hash).
- Generated file is self-contained: stdlib + `pytest` +
  `from ulog.testing import replay_records` only. Compiles
  cleanly. Pytest collects + runs the stub (placeholder
  `assert session is not None` passes by default).
- Public namespace: `ulog.replay_to_pytest` exported + in
  `__all__`.
- 13 / 13 tests in `tests/test_replay_to_pytest.py` green incl.
  the end-to-end test that runs the generated file via
  `pytest` subprocess and asserts "1 passed". Records-shape
  asserts no `record_hash` / `prev_hash` / `chain_pos` /
  `is_replay` keys leak (slim contract).
- 48 affected-area tests across replay_core + replay_state +
  replay_records + replay_to_pytest green.
- mypy --strict / ruff check / ruff format / deptry all clean.

### File List

- `ulog/replay.py` — `replay_to_pytest()` + `_slim_record` /
  `_slugify_hash` / `_auto_hash` helpers + stdlib imports
  (`datetime as _dt`, `hashlib as _hashlib`, `pprint as _pprint`,
  `re as _re`).
- `ulog/__init__.py` — `replay_to_pytest` export + `__all__`.
- `tests/test_replay_to_pytest.py` (NEW) — 13 tests.
