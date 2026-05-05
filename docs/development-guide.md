---
docType: development-guide
project_name: ulog-python
date: 2026-05-05
---

# Development Guide

## Prerequisites

- **Python `>=3.10`** (matrix: 3.10 / 3.11 / 3.12 / 3.13)
- **git** (the project depends on a submodule)
- Optional: **`uv`** — `run.sh setup` uses it when available, falls
  back to `python3 -m venv`

## Initial clone

```bash
# 1. Clone WITH submodules (vendored ucolor lives under vendor/ucolor-python)
git clone --recursive https://github.com/jojo8356/ulog-python.git
cd ulog-python

# If you already cloned without --recursive:
git submodule update --init --recursive
```

## Two equivalent setups

### Option A — `./run.sh setup` (recommended)

```bash
./run.sh setup
```

Creates `.venv` (uv-aware), installs `ulog[storage,web,dev]` + the
vendored `ucolor` (when the submodule is checked out). `--force`
recreates an existing `.venv`.

### Option B — manual

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./vendor/ucolor-python    # for truecolor (optional)
pip install -e ".[storage,web,dev]"
```

## Day-to-day commands

| Command | What it does |
|---|---|
| `make test` | `pytest tests/ -v` — runs all ~70 tests |
| `make mypy` | `mypy ulog/` (`--strict` from `pyproject.toml`) |
| `make check` | mypy + tests |
| `make build` | `python -m build` (wheel + sdist) |
| `make clean` | wipe `build/`, `dist/`, caches |
| `./run.sh dev` | runs pytest with logs landing in the `test` profile |
| `./run.sh demo` | generates a 7-record fixture in `~/.cache/ulog/prod.sqlite` |
| `./run.sh prod` | opens the inspection UI on the prod DB (port 8765) |
| `./run.sh test` | opens the UI on the test DB (port 8765) |
| `./run.sh clean` | deletes the prod + test SQLite caches |

`run.sh prod`/`test` accept extra args forwarded to `ulog-web`:

```bash
./run.sh prod --port 9000 --no-open
./run.sh dev -k profile -v
```

## Project layout for contributors

- **Add a new formatter** — subclass `logging.Formatter` (or the
  internal `_ColorAwareFormatter` for ANSI-aware), then call
  `ulog.register_formatter('myname', MyClass)`. See
  `tests/test_formatters.py:test_register_custom_formatter`.
- **Add a new storage handler** — subclass `logging.Handler` (or
  `FileHandler` for an append-to-file shape). Wire it into
  `ulog/setup.py:_build_handler` under a new `kind` string, with the
  matching new kwarg on `setup()`. Add a `_RESERVED` frozenset that
  matches the existing copies if you merge `record.__dict__` into
  output. Add an adapter under `ulog/web/viewer/adapters.py` if the
  inspection UI should support reading it.
- **Add a Django view** — wire it into `ulog/web/urls.py`, render via
  `django.shortcuts.render` against a template under
  `ulog/web/templates/ulog/`. The module-level `_adapter` singleton
  in `views.py` lazy-builds on first request — reset
  `_views._adapter = None` between tests if your test injects a fresh
  fixture.
- **Edit a PRD** — drop `docs/prds/PRD-vX.Y[.Z]-<topic-kebab>.md`
  with the standard frontmatter (`docType: prd`, `version`,
  `status`, `parent_prd`). Update `docs/prds/index.md` with the new
  row + the filiation tree.

## Testing conventions

- **Tests must be hermetic.** All filesystem-touching tests use
  `tmp_path` (pytest fixture) or `monkeypatch.setenv("XDG_CACHE_HOME",
  str(tmp_path))` to avoid leaking into `~/.cache/ulog/`.
- **Each test module has an `_isolate` autouse fixture** that strips
  `_ulog_managed` handlers post-test. Always include one when adding
  a new test file that calls `ulog.setup()`.
- **Use real fixtures, not mocks.** `tests/test_web.py:sqlite_fixture`
  builds a real SQLite via `SQLHandler` itself, so adapter tests
  exercise the full record-build path.
- **Profile auto-detection inside pytest is a feature, not noise.**
  `test_setup_profile_auto_picks_test_under_pytest` literally asserts
  that `profile='auto'` lands in the `test` DB because pytest is
  running. Don't override `profile=` defensively in fixtures unless
  the test deliberately exercises prod profile behavior.

## Type checking

`mypy --strict` is enforced. When suppressing an error, ALWAYS use a
specific code:

```python
handler._ulog_managed = True   # type: ignore[attr-defined]
```

Avoid bare `# type: ignore`. PEP 604 union syntax (`X | None`) is
preferred over `Optional[X]` everywhere.

## Coding conventions

- `from __future__ import annotations` at the top of EVERY module
  (3.10 needs it for `tuple[str, ...]` / `dict[str, Any]` /
  `Literal` runtime support in some contexts).
- `ValueError` for input validation (unknown level / profile /
  formatter / colour / handler kind). Don't introduce custom
  exceptions or `TypeError` here — keep the messages discoverable
  via the standard exception class.
- Lazy imports for optional deps (`sqlalchemy`, `django`, `ucolor`)
  — INSIDE the function/handler that needs them, never at module top.
- `f-strings` are fine for ULog's own diagnostic strings (errors,
  internal logs); user-facing log MESSAGES are stdlib-`%`-formatted
  or use `extra=`.
- Exception swallowing only with `# noqa: BLE001` and only in
  handler-cleanup or `Handler.emit` paths.

## Deployment

There's no CI/CD pipeline file in the repo today (no
`.github/workflows/`, no `.gitlab-ci.yml`, no `Dockerfile`). The
`run.sh` launcher is the canonical local entry point. Releases are
built with `make build` and published manually.

The Django web viewer binds `127.0.0.1` by default (NFR-SEC-10).
`--host 0.0.0.0` is supported but the CLI prints a warning to stderr
because the viewer has no auth — exposing it to the network exposes
the log archive.

## Troubleshooting

- **`ulog-run: missing dependency: django`** — install the `[web]`
  extra: `pip install -e ".[web]"`.
- **`runserver` migration warnings on boot** — should not appear;
  `ulog/web/settings.py` sets `MIGRATION_MODULES = {"contenttypes":
  None}`. If they reappear, check that the settings module is being
  loaded (env var `DJANGO_SETTINGS_MODULE=ulog.web.settings`).
- **`SchemaError` on existing SQLite** — expected when columns drift.
  v0.2 ships no migrations: delete the DB, or add the missing
  columns manually.
- **Colour not appearing on TTY** — set `NO_COLOR` env var unset (it
  hard-clamps off), check `--color always` or programmatic
  `setup(color='always')`. Without the ucolor submodule installed,
  ULog uses an 8-color fallback (no truecolor).
