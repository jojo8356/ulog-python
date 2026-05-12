---
docType: prd
project_name: ulog-python
version: 0.9.0
date: 2026-05-12
author: jojo8356
status: draft v1
parent_prd: PRD-v0.4-commit-author-filter.md
related_prd:
  - PRD-v0.5-forensic-archive.md
---

# ULog v0.9 — Resource validity panel

> While ULog observes what your app **runs**, v0.9 observes what your
> app **reads**: the JSON, YAML, CSV, TOML, INI files your code
> assumes are well-formed. The viewer gains a **"Resources" sidebar
> panel** showing every tracked resource and its parse status
> (✓ valid / ✗ broken / ⚠ schema-drifted). A `ulog
> validate-resources` CLI subcommand returns exit 0/1 for CI.

---

## 0. The 30-second pitch

Half of "production bugs" aren't logic bugs — they're a config file
that's syntactically right but semantically off (an extra comma, a
mistyped key, a CSV row with one column too many). The symptom shows
up in logs as a `KeyError` / `JSONDecodeError` / `csv.Error` and the
debugger spends 10 minutes reading the wrong code path before
realising the input was the problem.

ULog v0.9 collapses that to: **the moment you open the viewer, a
"Resources" sidebar panel lists every JSON/YAML/CSV/TOML/INI file in
the project with a green/red badge.** Same pipeline that ingests
logs also validates the resources, side-by-side.

Bonus for CI: `ulog validate-resources --path . --types json,toml`
returns exit 1 if anything fails to parse. Drop it into a pre-merge
gate; never ship a malformed `pyproject.toml` again.

---

## 1. Vision

### 1.1 Why this exists

Three observations from the v0.1 → v0.5 user research:

1. **The "is it me or is it the data?" decision tree.** A failing
   pytest under `ulog-web` shows the stack trace, but answering
   "could this be a corrupt fixture?" requires switching to the
   shell and running `python -c "import json; json.load(...)"` per
   suspect file. The viewer should answer this in 1 click.
2. **Schema drift on a multi-month timescale.** A project's
   `config.json` shape evolves; an older record in the log archive
   was emitted under v0.3 of the config schema. Without knowing the
   config-was-valid-at-emit-time, you can't tell if "wrong field"
   means "code bug" or "config rolled forward without a migration".
3. **CI gating costs a CLI step.** Most teams run `python -c
   "import json; json.load(open('config.json'))"` in a Makefile or
   GitHub Action. With N config files this becomes N shell lines.
   One `ulog validate-resources` is shorter and produces structured
   output.

### 1.2 What v0.9 isn't

- **Not a schema validator.** We check **parse validity** (does
  the file load without throwing?), not **semantic correctness**
  (does it match a JSON Schema / Pydantic model). Schema validation
  is the user's app's job; v0.9 catches the layer below.
- **Not a linter.** No "your indent is 4 spaces, should be 2",
  no "this YAML uses tabs". If `yaml.safe_load` accepts it, it's
  valid for v0.9.
- **Not a file watcher.** v0.9 scans on viewer startup + on
  explicit refresh. Live `inotify` / `watchdog` integration is
  deferred to v0.9.1+ if there's demand.
- **Not a binary file inspector.** Binary resources (PNG, SQLite,
  pickle) are out of scope. v1.0 might add "binary header sniff"
  but the v0.9 contract is text-based parseable formats only.

### 1.3 Target users (carried + new)

- **Marco** (carried) — solo dev with one `config.json` and a
  fixture-CSV. v0.9 catches the day his `config.json` gains a
  trailing comma during a merge.
- **Lin** (carried) — pipeline integrator running multi-format ETL.
  Has 30+ YAML pipeline defs. v0.9's sidebar shows which one a
  teammate broke in the last commit.
- **Sara** (carried) — library dev with versioned fixtures under
  `tests/fixtures/*.json`. v0.9 surfaces fixture corruption before
  the test suite blames the code under test.
- **Compliance officer Erika** (carried from v0.5) — auditing a
  forensic archive. v0.9 lets her assert "at the time these records
  were emitted, the project's tracked configs all parsed cleanly"
  by checking the resource-validation timestamp.

### 1.4 Success criteria

| ID  | Metric | Target |
|---|---|---|
| SC1 | Parse-validity catch rate on a curated 50-file zoo (10 broken, 40 valid) | 100% (no false positives, no false negatives) |
| SC2 | Viewer-startup scan time on 200-file project | ≤ 500 ms (NFR-PERF-90) |
| SC3 | CI mode (`ulog validate-resources --path .`) wall time on 200-file project | ≤ 1 s |
| SC4 | Zero new PyPI runtime deps for the **core** formats (JSON / CSV / TOML / INI) | yes (stdlib) |
| SC5 | YAML opt-in via `[validate-yaml]` extra installs PyYAML and only PyYAML | yes |
| SC6 | False-positive rate on the curated zoo | 0 |

---

## 2. Scope (v0.9)

### 2.1 In scope (8 features, ~ 450 LOC `ulog/` core estimate)

1. **`ResourceValidator` API** (`ulog/_resources.py`) — discovers
   resource files via glob, dispatches per-extension to a stdlib
   parser, returns a `ValidationResult(path, format, status,
   error_msg, scanned_at)` dataclass.
2. **Stdlib parsers wired**: `.json` → `json.load`, `.toml` →
   `tomllib.load` (3.11+; vendored polyfill for 3.10), `.csv` →
   `csv.reader` (count rows, sniff inconsistencies), `.ini` /
   `.cfg` → `configparser.ConfigParser.read`.
3. **YAML parser, opt-in**: `.yaml` / `.yml` → `yaml.safe_load`
   under the `[validate-yaml]` extra. Without the extra, YAML files
   show as `⚠ skipped (install ulog[validate-yaml])` — not red.
4. **CLI subcommand `ulog validate-resources`** — flags:
   `--path PATH` (default `.`), `--types FORMAT1,FORMAT2` (default
   all), `--exclude GLOB` (additive `.gitignore`-style), `--format
   text|json` output, `--fail-fast`, exit 0 (all valid) / 1 (any
   broken) / 2 (usage error).
5. **Web viewer sidebar panel "Resources"** — sits below
   "Authors" (v0.4 panel) and above "Time range". Lists each
   resource with: badge (✓ green / ✗ red / ⚠ amber), path
   (basename-truncated, full on hover), format, last scan time.
   Click → detail page `/resources/<path>/` with the parse-error
   message verbatim (or `✓ parses cleanly + N rows / keys`).
6. **Scan-on-startup with on-demand refresh** — the viewer scans
   the project root (`--repo` from v0.4) at boot. A "↻ Refresh"
   button in the panel re-scans without reload. Result cached for
   the viewer process lifetime; no persistent sidecar for v0.9.
7. **Filter axis**: "Show only records emitted while resource X
   was broken at the time" — joins ULog's `ts` against the
   validation history (kept in-memory for the viewer session, no
   DB schema impact).
8. **Doc page `/docs/resource-validity/`** covering: how the scan
   works, list of supported formats, the `[validate-yaml]` extra,
   the `--exclude` patterns, a CI example, and the "what this is NOT"
   section verbatim from §1.2 above.

### 2.2 Explicit non-goals (deferred to v0.9.1+ or later)

- **Schema validation** (JSON Schema, Pydantic, Cerberus) — out.
  v1.x might add a `ulog/_schemas/` plugin slot.
- **Live file-watching** (`inotify` / `watchdog`) — out. Refresh
  is manual or scan-on-startup only.
- **Binary file inspection** (PNG / SQLite / Parquet headers) —
  out. v1.0+ candidate.
- **`.env` / `.envrc` / shell-script parsing** — out. These are
  not formal grammars; out-of-scope.
- **Resource-validity history persisted to the SQLite DB** — the
  v0.9 contract is in-memory only. v0.9.1 may add a `<db>.resources.
  sqlite` sidecar mirroring v0.4's authors-sidecar pattern, but
  that's a deliberate later decision.
- **Auto-fixing broken resources** — out, forever. v0.9 reports;
  the user fixes.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| File is empty | `✓ valid` for JSON (`{}` no — empty file IS invalid JSON; `csv` empty = `✓ 0 rows`; `toml` empty = `✓ {}`; `yaml` empty = `✓ None`). Per-format default per parser convention. |
| File doesn't exist (race during scan) | Logged in stderr, marked `✗ vanished`, not crash. |
| File is a binary masquerading as `.json` (e.g. a SQLite DB renamed to `.json`) | `✗ broken` with the parser's actual error message (e.g. `JSONDecodeError: Expecting value`). |
| Permissions denied | `⚠ unreadable`, error msg = `PermissionError`. Not red — it's a transient/env issue. |
| Symlink loop | Detect via `os.path.realpath` + visited-set; skip with `⚠ symlink loop`. |
| File > 100 MB | Skip with `⚠ too large`. Parsing a 100 MB JSON for "validity" is a perf trap; spell it out. NFR-PERF-90 budget assumes typical sizes. |
| `.git/`, `node_modules/`, `__pycache__/`, `.venv/`, `dist/`, `build/` | Excluded by default via the `.gitignore`-style baseline. `--no-default-exclude` opts out. |
| `--exclude '*.tmp'` | Honored in addition to defaults. |
| YAML installed but `safe_load` chokes on a tag (`!!python/object`) | `✗ broken` with the yaml.constructor error message. Documented: v0.9 uses `safe_load` only — no arbitrary Python loading (security). |
| CI run on a repo with only `.txt` files (none of the supported types) | Exit 0, scan reports `0 files validated`. NOT an error. |

### 2.4 Protected invariants

- **I8 (new):** Zero PyPI runtime deps for the core (JSON / CSV /
  TOML / INI). YAML always opt-in.
- **I5 (carried from v0.1):** Logging API unchanged. v0.9 is
  ADDITIVE to the viewer; the `ulog.setup()` surface gains zero
  new mandatory params.
- **I9 (new):** Parse-validity only; no schema judgement. The
  `ValidationResult.status` enum is `VALID | BROKEN | SKIPPED |
  TOO_LARGE | VANISHED | UNREADABLE` — no `SCHEMA_INVALID`.

---

## 3. Functional Requirements

### 3.1 Discovery & dispatch

- **FR120**: `ResourceValidator(repo_root: Path, *, exclude: list[str] = None, types: set[str] = None)` walks `repo_root` recursively, applies `.gitignore` baseline excludes + user `--exclude` patterns + `--types` filter.
- **FR121**: Extension → parser dispatch lives in a module-level dict `_PARSERS: dict[str, Callable[[Path], ValidationResult]]`. Adding a new format = one entry + one function.
- **FR122**: Each parser returns a `ValidationResult` dataclass: `path` (relative to repo_root), `format` (str), `status` (enum), `error_msg` (str | None), `scanned_at` (ISO ts), `summary` (e.g. `"42 rows, 3 columns"` for CSV / `"7 top-level keys"` for JSON — short, optional).

### 3.2 Per-format parsers

- **FR123 (JSON)**: `json.load(f)` — top-level type can be dict/list/scalar/null. Status VALID unless `JSONDecodeError`.
- **FR124 (TOML)**: `tomllib.load(f)` on Py 3.11+. On 3.10, fall back to vendored `tomli` (already in `[storage]` via SQLAlchemy's deps? No — vendor under `ulog/_vendor/tomli/` or accept 3.11+ only for this feature).
- **FR125 (CSV)**: `csv.reader(f)`; iterate to detect inconsistent column counts. Status VALID if all rows have the same column count as the first row (mode); `⚠ inconsistent rows: N` otherwise (still ⚠ not ✗ — CSV with ragged rows is valid CSV, just suspicious).
- **FR126 (INI/CFG)**: `configparser.ConfigParser().read(path)` — empty result means parse failure for configparser. Status VALID if `len(parser.sections()) > 0` or file is empty.
- **FR127 (YAML, opt-in)**: try `import yaml`. If absent → `SKIPPED`. If present → `yaml.safe_load(f)` (NEVER `load(...)`).

### 3.3 CLI surface

- **FR128**: New `ulog/_cli/cmd_validate_resources.py` registered alongside `verify` / `repair` / `purge`. Subcommand: `ulog validate-resources [--path .] [--types t1,t2] [--exclude GLOB] [--format text|json] [--fail-fast]`.
- **FR129**: Text output (default): aligned table — `STATUS  FORMAT  PATH                 SUMMARY/ERROR`. Color via the existing ucolor optional dep (already wired in v0.1).
- **FR130**: JSON output: `{"scanned_at": "<iso>", "repo_root": "<abs>", "summary": {"valid": N, "broken": N, "skipped": N, ...}, "results": [<ValidationResult>...]}`. For CI piping into other tools.
- **FR131**: Exit 0 if zero `BROKEN`. Exit 1 if any `BROKEN`. Exit 2 on usage error (bad path, bad `--types`, etc.). `SKIPPED` / `UNREADABLE` / `VANISHED` / `TOO_LARGE` do NOT fail exit code by default.
- **FR132**: `--strict` flag promotes ALL non-VALID statuses to non-zero exit. For paranoid CI.

### 3.4 Web viewer integration

- **FR133**: New sidebar panel "Resources" between "Authors" and "Time range" sections in `list.html`. Hidden when `--no-resource-index` CLI flag is passed.
- **FR134**: Panel shows ≤ 8 resources by default with a "show all (N)" expand link. Sort: BROKEN first, then UNREADABLE/VANISHED, then VALID, alphabetic within each group.
- **FR135**: Each row: status badge (lucide icon ✓/✗/⚠), basename (full path on `<title>` tooltip), format pill, `<time>` (last scan).
- **FR136**: Detail page `/resources/<relpath>/` — full `ValidationResult` rendered: file path, format, status, scanned_at, error_msg (in `<pre>` with HTML escape), summary, file size. Plus a "← Back to records" link.
- **FR137**: Refresh button "↻ Re-scan" — fires `POST /api/resources/rescan` (returns 202), reloads the panel via `hx-swap` or full page reload.
- **FR138**: Optional records filter "show only records emitted while resource X was BROKEN" — join `ULog.ts` against the validation history kept in `RESOURCE_HISTORY: list[tuple[scanned_at, results]]`. Off by default; activated via clicking a BROKEN resource's row.

### 3.5 Documentation

- **FR139**: Doc page `/docs/resource-validity/`. Sections: Overview, Supported formats, The `[validate-yaml]` extra, Defaults & excludes, CLI usage, CI integration example (GitHub Actions snippet), What this is NOT (verbatim from PRD §1.2), Troubleshooting.
- **FR140**: Listed in `/docs/` index.

---

## 4. Non-Functional Requirements

- **NFR-PERF-90**: Viewer-startup scan on a 200-file project ≤ 500 ms (warm filesystem cache). Cold-cache target: ≤ 1.5 s.
- **NFR-PERF-91**: CLI mode on the same 200 files ≤ 1 s wall (no viewer overhead).
- **NFR-DEP-80**: Zero new PyPI deps for core formats. YAML strictly behind `[validate-yaml]`. Tomli for 3.10 either vendored (preferred) or feature-gated to 3.11+.
- **NFR-SEC-80**: YAML uses `safe_load` only. JSON uses `json.load` with default safe behaviour. No `pickle`, `marshal`, or `eval`-based parsers ever.
- **NFR-REL-90**: Scan never crashes the viewer. A parser raising an unexpected exception is caught at the dispatch layer and turned into `BROKEN` with the exception class + str.
- **NFR-DOC-90**: Doc page covers every supported format + CI example.
- **NFR-PORT-80**: Symlink-loop detection works on Linux, macOS, Windows.

---

## 5. API surface (sketch)

### 5.1 Programmatic

```python
from ulog._resources import ResourceValidator, ValidationStatus

validator = ResourceValidator(repo_root=Path('.'))
results = list(validator.scan())  # generator
broken = [r for r in results if r.status is ValidationStatus.BROKEN]
for r in broken:
    print(r.path, r.error_msg)
```

### 5.2 CLI

```bash
# All defaults
ulog validate-resources

# Only JSON and TOML, exclude vendored stuff
ulog validate-resources --types json,toml --exclude 'vendor/**'

# CI pipe-into-tool
ulog validate-resources --format json | jq '.results[] | select(.status == "BROKEN")'

# Paranoid CI — fail on skipped too
ulog validate-resources --strict
```

### 5.3 Setup (no change)

```python
ulog.setup(integrity='hash-chain', handlers=['sql'], sql_url=...)
# No new mandatory params. Resource validation is viewer-side
# + CLI-side — not part of the runtime logging pipeline.
```

---

## 6. Implementation sketch

| Story (proposed) | Scope | Est. LOC |
|---|---|---|
| 9.1 | `ResourceValidator` API + `ValidationResult` dataclass + dispatcher | 80 |
| 9.2 | JSON / TOML / CSV / INI parsers | 90 |
| 9.3 | YAML opt-in (`[validate-yaml]` extra) | 30 |
| 9.4 | `.gitignore`-style baseline excludes + `--exclude` glob | 50 |
| 9.5 | `ulog validate-resources` CLI subcommand | 80 |
| 9.6 | Web sidebar panel + `/resources/<path>/` detail view | 100 |
| 9.7 | "↻ Re-scan" button + POST endpoint | 30 |
| 9.8 | Doc page `/docs/resource-validity/` + index entry | n/a (markdown) |
| 9.9 | Edge cases (symlink loop, too-large, vanished) as dedicated tests | ~ test only |

Total core code estimate: ~ 460 LOC.

---

## 7. Decisions log

| ID | Decision | Trade-off accepted |
|---|---|---|
| D1 | Stdlib parsers only for core formats (JSON / TOML / CSV / INI) | No YAML in core; opt-in extra. Preserves zero-dep invariant. |
| D2 | YAML opt-in via `[validate-yaml]` | Users wanting YAML must `pip install ulog[validate-yaml]`. Discoverable from the `⚠ skipped` row's tooltip. |
| D3 | Parse-validity only, NO schema validation | Schema validation is a 10× larger feature; defer to a later PRD if demanded. |
| D4 | Scan-on-startup + manual refresh, NO file-watching | `inotify`/`watchdog` adds a dep + a thread; not worth it for v0.9. |
| D5 | In-memory history during viewer session, NO persistent sidecar | v0.9 keeps the DB schema untouched. v0.9.1 may add `<db>.resources.sqlite` if user feedback demands it. |
| D6 | `SKIPPED` / `UNREADABLE` / `VANISHED` do NOT fail the exit code by default | Avoid CI noise from missing YAML extras / transient FS issues. `--strict` for paranoid mode. |
| D7 | Inconsistent CSV row counts → `⚠ amber`, not `✗ red` | Ragged CSV is technically valid; warning preserves info without blocking CI. |
| D8 | YAML uses `safe_load` only | Loading arbitrary Python objects via YAML tags is a known RCE vector. Non-negotiable. |
| D9 | Resource history in viewer is per-session (memory), NOT per-record (DB column) | Avoid bloating every log record with resource-validity at emit time. The "filter records by resource state at emit time" filter (FR138) joins against in-memory history; pre-session records get treated as "unknown state". |

---

## 8. Open questions

| ID | Question | Owner |
|---|---|---|
| Q1 | Should `.lock` files (`poetry.lock`, `Cargo.lock`, `package-lock.json`) be excluded by default? Argument for: noise; against: a corrupted `package-lock.json` is exactly the bug v0.9 should catch. **Tentative: include.** | Johan |
| Q2 | Should we surface "config file changed since last log was emitted" as a record-level annotation? Likely yes, but in v0.9.1 once persistent history lands. | Johan |
| Q3 | `pyproject.toml`-style TOML allows duplicate keys in some parsers; `tomllib` rejects them. Should we warn (⚠) instead of fail (✗) on duplicate-key errors? **Tentative: ✗ — match tomllib's strictness.** | Johan |
| Q4 | XML support — out of v0.9, but in scope for v0.9.x? `xml.etree.ElementTree` is stdlib but XXE attack surface needs `defusedxml`. Probably v1.x. | TBD |

---

## 9. References

- [Source: docs/prds/PRD-v0.4-commit-author-filter.md] — sidebar-panel + per-record-enrichment pattern carried forward
- [Source: docs/prds/PRD-v0.5-forensic-archive.md] — invariant numbering (I1-I9), CLI subcommand convention (`ulog/_cli/cmd_<name>.py`)
- [Source: tomllib (stdlib, Py 3.11+)] — chosen TOML parser
- [Source: PyYAML safe_load() docs] — security justification for D8
