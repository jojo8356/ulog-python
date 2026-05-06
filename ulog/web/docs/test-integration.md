# Test integration

ULog v0.3 ships a pytest plugin that records every test's lifecycle as
structured log records — so you can answer "what did this failing test
log?" in two clicks instead of grepping CI output.

## 1. Install

```bash
pip install ulog[testing]
```

Pytest auto-discovers the plugin via the `pytest11` entry-point — no
`conftest.py` configuration required.

## 2. Run your tests

### Option A — bare CLI flag

```bash
pytest --ulog-db ./tests-logs.sqlite
```

The plugin auto-configures `ulog.setup(handlers=['sql'], sql_url=...)`
pointing at your chosen path.

### Option B — `conftest.py` setup

```python
# conftest.py
import ulog

def pytest_configure(config):
    ulog.setup(
        handlers=['sql'],
        sql_url='sqlite:///./tests-logs.sqlite',
    )
```

Use this when your project already has a `conftest.py` and you want test
logs to live alongside other ulog setup (e.g. shared with application
logs in dev).

## 3. CLI flags

| Flag | Behavior |
|---|---|
| `--ulog-db PATH` | Override the destination DB. Auto-configures `setup()` if no host conftest did. |
| `--ulog-disable` | Short-circuit the plugin (no records emitted). Escape hatch. |
| `--ulog-summary` | Default ON. Prints a one-line stderr summary at session end. `pytest -q` suppresses. |

Example summary line:

```
ulog: 412 tests, 409 passed, 3 failed, 0 skipped → ulog-web ./logs.sqlite to triage
```

## 4. Test event schema

Each test produces 2-3 records, all with the same `test_id` (the pytest
nodeid):

```json
{"level": "INFO", "msg": "test started", "logger": "ulog.test",
 "context": {"test_id": "tests/test_foo.py::test_bar"}}
```

```json
{"level": "INFO", "msg": "test passed", "logger": "ulog.test",
 "context": {"test_id": "...", "outcome": "passed",
             "duration_s": 0.024, "phase": "call"}}
```

On failure, an additional ERROR record carries the traceback:

```json
{"level": "ERROR", "msg": "AssertionError: foo != bar", "logger": "ulog.test",
 "context": {"exc": {"type": "AssertionError", "msg": "...", "tb": ["..."]}}}
```

Application records emitted DURING a test inherit `test_id` automatically
via `ulog.bind`:

```python
log = ulog.get_logger("myapp")

def test_render():
    log.info("rendering rom")  # record carries test_id="...::test_render"
```

## 5. Find failed tests — worked example

Say a CI run flagged 3 failing tests out of 412 and you have the SQLite
log artefact. Open the viewer:

```bash
ulog-web ./logs.sqlite
```

1. The TESTS sidebar lists every test grouped by file with outcome
   badges (passed / failed / errored / skipped).
2. Tick "Failed only" — the records list narrows to the 3 failing tests'
   outcome records.
3. Click a test name in the sidebar — the records list filters to ALL
   records bound to that test (plugin records + application records
   inherited via `bind`).
4. Click any record in the list to see its full detail. The "Test
   context" panel offers two more drill-downs: "view all records for
   this test" and "errors+warnings only".

Total: 3 clicks from CI artefact to root cause.

## 6. Programmatic API (non-pytest runners)

For custom test runners (asyncio drivers, benchmark harnesses, hand-
rolled test loops), use the `test_event` context manager:

```python
from ulog.testing import test_event

with test_event("custom_test_42") as ev:
    log.info("step 1")  # propagates test_id via bind
    do_thing()
    ev.outcome("passed", duration_s=0.42)
```

Same record shape as pytest tests. If the block raises without an
explicit `ev.outcome(...)` call, the wrapper auto-emits
`outcome="errored"` plus the traceback.

## 7. Troubleshooting

### "I see a `ulog: xdist+NFS detected` warning"

The plugin detected `pytest-xdist` running with the SQLite path on a
network filesystem (NFS / CIFS / SMB). SQLite locking is unreliable over
NFS, so the plugin transparently swapped to JSONL output at the same
path stem. Records still land — just in `<path>.jsonl` instead of
`<path>.sqlite`. The viewer reads JSONL natively.

### "I see a `ulog: xdist+Windows detected` warning"

Same fallback, triggered for any xdist run on Windows. Windows
file-locking semantics on SQLite under multi-process are unreliable;
JSONL is the safe path.

### "I see a `ulog: WAL mode unavailable` warning"

The plugin tried to enable SQLite's WAL journal mode for concurrent
xdist writers and the underlying filesystem rejected it. Falls back to
JSONL — same as the NFS / Windows cases.

## See also

- [Storage handlers](/docs/storage/) — how the SQL handler stores records
- [Quickstart](/docs/quickstart/) — non-pytest setup
