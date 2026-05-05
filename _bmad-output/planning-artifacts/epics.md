---
stepsCompleted: [1, 2, 3, 4]
lastStep: 4
status: 'complete'
completedAt: '2026-05-05'
workflowType: 'epics-and-stories'
project_name: 'ulog-python'
user_name: 'Johan'
date: '2026-05-05'
scope: 'drafts v0.3 → v0.5 (v0.1/v0.2/v0.2.1 shipped — out of scope)'
inputDocuments:
  - docs/prds/PRD-v0.3-test-integration.md
  - docs/prds/PRD-v0.4-commit-author-filter.md
  - docs/prds/PRD-v0.5-forensic-archive.md
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/project-context.md
---

# ulog-python — Epic Breakdown

## Overview

This document decomposes the v0.3 → v0.5 requirements (PRDs) and the
companion architecture decisions (architecture.md) into epics and
stories implementable by AI agents. Shipped versions (v0.1 / v0.2 /
v0.2.1) are out-of-scope — their architecture is substrate.

## Requirements Inventory

### Functional Requirements

**v0.3 — Test integration (PRD-v0.3 §3, FR51 → FR69):**

- **FR51:** Pytest plugin registered via `[project.entry-points.pytest11]` in `pyproject.toml`, auto-discovered when `pip install ulog[testing]` runs.
- **FR52:** Plugin OFF by default unless (a) `setup()` was called in host's `conftest.py`, OR (b) `--ulog-db PATH` passed on pytest CLI.
- **FR53:** `pytest --ulog-disable` short-circuits the plugin even when setup or `--ulog-db` is present.
- **FR54:** Each test emits ≥2 records: `test.started` (INFO) at logstart, `test.outcome` (INFO/ERROR) at logfinish.
- **FR55:** `test_id` = pytest nodeid (`tests/test_foo.py::test_bar`) for non-parametrized; `nodeid + parametrize_id` for parametrized. Stable across runs.
- **FR56:** Failures produce ERROR record with full traceback (`exc.tb`) sourced from `report.longrepr`.
- **FR57:** Test phases (setup/call/teardown) recorded as `phase` field on outcome record. Teardown failures emit a separate ERROR with `phase="teardown"`.
- **FR58:** Test duration (`duration_s`) computed from `report.duration`.
- **FR59:** Plugin pushes `test_id` via `ulog.bind(test_id=...)` at logstart, calls `ulog.unbind('test_id')` at logfinish.
- **FR60:** Records emitted by application code DURING the test inherit `test_id` automatically.
- **FR61:** Pytest fixture setup/teardown records carry the fixture's owning test's `test_id` (scope = entire `pytest_runtest_protocol`).
- **FR62:** New "Tests" sidebar section above "Sectors" in viewer. Lists collected tests grouped by file, with outcome badges.
- **FR63:** "Failed only" filter checkbox toggles `outcome IN ('failed', 'errored')`.
- **FR64:** "Slowest top 10" sorts by `duration_s DESC LIMIT 10`.
- **FR65:** Click a test name filters records to that `test_id`. Persisted in URL query string.
- **FR66:** Detail view for a record with `test_id` shows a "Test context" panel with file:line, outcome, duration, phase + 2 links (all records for this test, errors+warnings only).
- **FR67:** `pytest --ulog-db PATH` overrides the destination DB; setup auto-configured if no host setup exists.
- **FR68:** `pytest --ulog-disable` short-circuits the plugin entirely.
- **FR69:** `pytest --ulog-summary` prints a one-line stderr summary after the session (default ON; `-q` suppresses).

**v0.4 — Commit author filter (PRD-v0.4 §3, FR70 → FR83):**

- **FR70:** `ulog.web.viewer.blame.AuthorIndex(repo_root)` exposes `author_for(file, line) -> Author | None`. Uses `git blame --porcelain` + stdlib parse (no GitPython dep).
- **FR71:** Index built lazily: first `ulog-web` (or `ulog web` post-C1) load walks unique `(file, line)` pairs and runs `git blame` per file (one process per file, batched by `-L`). Progress printed to stderr.
- **FR72:** Cache table `authors(file, line, author_name, author_email, commit_sha, commit_ts)` PK = `(file, line)`. Persisted in same SQLite as logs, or in sidecar `<logs>.authors.sqlite` for JSONL/CSV sources.
- **FR73:** `--no-author-index` skips the indexer; sidebar section hides.
- **FR74:** `--repo PATH` sets git root explicitly. Default: walk parents of cwd until `.git/` is found; if none, treat all records as `<unknown>` + warn.
- **FR75:** Files in records not present in the repo → `<unknown>` author. Count `(<unknown>: N)` shown.
- **FR76:** New "Authors" sidebar section between "Files" and "Time range". Lists every distinct author (name + email truncated to 20 chars + ghost-count).
- **FR77:** Multi-select with OR. URL query string: `?author=johan@example.com&author=lin@example.com`.
- **FR78:** "Show unknown" checkbox toggles `<unknown>` records (default: ON).
- **FR79:** Author counts ghost-mode (per v0.2.1) — counts ignore own filter axis.
- **FR80:** Detail view "Authored by" panel: name + email + commit short-sha + relative date + 2 links (all records from this author, view diff).
- **FR81:** "View diff" link triggers `git show <sha>` in server-side handler `/diff/<sha>`. Server validates sha is reachable in `--repo` (via `git rev-parse --verify`); rejects non-hex chars.
- **FR82:** Indexer caches per `(file, line)` pair; subsequent runs reuse cache when file mtime unchanged. Re-blame on file change.
- **FR83:** One `git blame` invocation per (unique-file, repo) — uses `-L` ranges to minimize forks. For 100K records spanning ~30 files: ≤30 forks at startup.

**v0.5 — Forensic archive (PRD-v0.5 §3, FR90 → FR117):**

- **FR90:** `ulog.setup(immutable_when=callable)` accepts predicate `(record) → bool`. True → immutable storage (UPDATE/DELETE blocked by SQL trigger). Default: `lambda r: r.levelno >= logging.ERROR`.
- **FR91:** Both immutable and rotable storage share single monotonic `chain_pos` sequence so hash chain (FR94) walks rows in append order.
- **FR92:** `ulog.setup(min_retention_days=N)` enforces floor on rotable records. Rotation/purge refuses to drop records younger than `today − N days`. Default N = 0 (off).
- **FR93:** `ulog.purge(before=<date>)` is the only sanctioned cleanup path. Validates against `min_retention_days` and `immutable_when`. Returns count of records actually purged.
- **FR94:** At write, ulog computes `record_hash = sha256(canonical_json(record) + prev_record_hash)`. First record's `prev_hash = b"\x00" * 32`. Per-DB `BEGIN IMMEDIATE` lock serializes the chain.
- **FR95:** `ulog verify [--range A-B]` walks chain (or sub-range), reports OK / BROKEN at #N (expected hash X, got Y). Exit code 0/1. Runs offline.
- **FR96:** UI integrity badge in sidebar of every page: `Integrity ✓ verified up to #N (last check: 2 min ago)` or `Integrity ✗ broken at #N`. Auto-refreshes on demand.
- **FR97:** `ulog repair` truncates chain at last valid record, archives orphaned content into `<db>.chain_break_<ts>.log`. Refuses without `--confirm`.
- **FR98:** `ulog.replay(filter=..., on=callback)` iterates records matching filter in chain order, calls `callback(record)` per record. Callback receives frozen-dict view (read-only).
- **FR99:** During replay, `ulog.is_replaying()` returns True. New `log.error()` calls inside callback are flagged with `is_replay=True` to prevent infinite loops.
- **FR100:** `ulog.replay_to_pytest(filter, output_path)` generates `tests/test_incident_<hash>.py` fixture replaying records and asserting new code path resolves the incident.
- **FR101:** `ulog correlate <filter>` computes `lift = P(tag=v | filter) / P(tag=v | not filter)` for every (tag, value) pair. Returns top 10 over and bottom 5 under, sorted by lift. SQL: single `GROUP BY tag, value` with `COUNT(*) FILTER`. Index on `(tag_name, tag_value)`.
- **FR102:** `correlate` flags warnings inline when `in_filter < 30` (small-sample bias) and when filter axis is included in dimensions explored (lift forced to 0 or ∞).
- **FR103:** `ulog bisect <pattern>` runs binary search over chain to find first record matching pattern (regex on `msg`, `extras`, `tags`). Returns matched record + v0.4 commit context.
- **FR104:** `correlate` and `bisect` exposed as CLI subcommands AND as Python API (`ulog.correlate(...)`, `ulog.bisect(...)`).
- **FR105:** `ulog.resolve(incident_hash, by, note)` emits new immutable record with `level=INFO`, `msg="RESOLVED"`, `resolves=<hash>`, `by=<user>`, `note=<str>`, `commit_sha=<HEAD>`. Foreign-key validated.
- **FR106:** `ulog.reopen(incident_hash, reason)` emits `msg="REOPENED"` record referencing original. Incident state computed by walking chain (latest wins).
- **FR107:** `ulog incidents --status {open,closed,all}` lists records with resolution state. CLI exit code = number of open incidents (CI gate-friendly).
- **FR108:** `ulog incidents --report --since <period>` outputs aggregated KPIs (opened/closed/net debt/MTTR/P95/reopens/top closers). Markdown output.
- **FR109:** If contextvar `_OTEL_TRACE_CONTEXT` (or env `traceparent`) set at log time, ulog auto-attaches `trace_id` and `span_id`. No-op if absent. Zero new dep.
- **FR110:** `ulog trace <id>` lists all records sharing `trace_id` chronologically across services (assumes shared DB or `--db <path>` flag).
- **FR111:** `ulog.setup(issue_template_url="...")` accepts URL with placeholders `{msg}`/`{level}`/`{service}`/`{author}`/`{author_handle}`/`{commit_sha}`/`{record_hash}`/`{labels}`/`{body}`. UI "Open issue" button populates and opens URL in new tab.
- **FR112:** Multi-track view: 4 fixed tracks (level/service/author/file). Each track is horizontal SVG strip with one tick per record over shared time axis. Mute toggle hides records on that track from main list.
- **FR113:** Integrity badge (FR96) visible on every UI page header.
- **FR114:** Detail panel for a record shows "Resolves: #N" / "Resolved by: #M" cross-links if applicable, with resolution note inline.
- **FR115:** Sidebar adds "Incidents" section with quick filters: Open / Closed (last 7d) / Reopened.
- **FR116:** New doc page `ulog/web/docs/v0.5-forensic-archive.md`: 30-second pitch, 7 invariants, 6 worked examples, troubleshooting section.
- **FR117:** Existing doc pages (quickstart, storage, api, troubleshooting, sectors-and-files) updated to mention new APIs without breaking v0.4 readers.

### NonFunctional Requirements

**v0.3:**

- **NFR-PERF-20:** Plugin overhead < 5 ms per test. Bind + 2-3 record inserts on batched SQL handler.
- **NFR-COMPAT-10:** Pytest 7.0+. xdist supported via SQL handler batch queue.
- **NFR-DOC-10:** New `/docs/test-integration.md` page covering plugin install, CLI flags, schema, "find failed tests" worked example.
- **NFR-REL-10:** Plugin opt-in by default — installing `ulog[testing]` MUST NOT change pytest behavior until user passes a flag or configures setup.
- **NFR-PORT-10:** Linux + macOS + Windows. xdist on Windows trickiest (file locking on SQLite); fallback to JSONL if xdist + sqlite + NFS detected.

**v0.4:**

- **NFR-PERF-30:** Indexer adds ≤ 5 s to startup for 100K-record DB on 30-file repo. `--no-author-index` opts out.
- **NFR-PERF-31:** UI page-load with author filter active stays ≤ 500 ms (JOIN on indexed `authors` table).
- **NFR-DEP-30:** No new Python dep (subprocess + stdlib only). `git` binary on PATH required if `--repo` set or auto-detected.
- **NFR-COMPAT-30:** Linux + macOS + Windows. Windows: `git` from Git for Windows is enough.
- **NFR-DOC-30:** New `/docs/author-filter.md` page covering: how it works, what `<unknown>` means, "code author vs commit author" distinction, "find errors in code Lin wrote this week" worked example.
- **NFR-SEC-30:** `/diff/<sha>` validates sha is reachable in `--repo` via `git rev-parse --verify <sha>` before invoking `git show`. Sha must match `[0-9a-f]{4,40}`.

**v0.5:**

- **NFR-PERF-50:** `setup()` overhead remains ≤ 1 ms (one-time cost). pytest-benchmark median 5 runs, CPython 3.12, GitHub Actions ubuntu-latest.
- **NFR-PERF-51:** Per-log-call overhead ≤ 1.3× v0.4 baseline (chain hash adds ~5 µs). `tests/bench_log.py`.
- **NFR-PERF-52:** `ulog verify` walks 100K records in ≤ 5 s, single-thread, SQLite WAL mode, NVMe SSD, GitHub Actions runner. CI-gated. (= SC1.)
- **NFR-PERF-53:** `ulog correlate` returns top-10 in ≤ 500 ms on 10K-filter / 1M-baseline DB. (= SC2.)
- **NFR-PERF-54:** `ulog bisect` over 1M-record chain finds first match in ≤ 100 ms (≈20 binary probes × 5 ms each).
- **NFR-PERF-55:** Multi-track UI renders 4 axes × 4 h on 100K records in ≤ 200 ms TTI. (= SC7.)
- **NFR-DEP-50:** `pyproject.toml dependencies = []` stays unchanged. ucolor stays vendored. (= SC4 regression gate.)
- **NFR-COMPAT-50:** Python 3.10+; `mypy --strict` green; stdlib `logging` compat preserved (= SC5 / I5 gate).
- **NFR-PORT-50:** Linux + macOS + Windows. Hash chain works on all three (sha256 stdlib).
- **NFR-REL-50:** Chain integrity preserved across multiprocess writers — `tests/test_chain_concurrency.py` (8 writers × 10 K records each, no broken chain).
- **NFR-REL-51:** Replay is read-only on chain. Any record emitted during replay flagged `is_replay=True`.
- **NFR-REL-52:** `ulog repair` is idempotent: running twice on healthy chain = no-op; running on broken chain = same truncation point.
- **NFR-DOC-50:** Doc page `v0.5-forensic-archive.md` ships with 6 worked examples covering each FR cluster. (= FR116.)
- **NFR-SEC-50:** All CLI inputs (`bisect`, `verify --range`, `incidents`, `trace`) validated against shell-injection. `record_hash` arguments must match `[0-9a-f]{4,64}`. `pattern` for bisect compiled as Python regex (no shell expansion).
- **NFR-SEC-51:** Issue-template URL placeholders are URL-encoded server-side. User template not eval'd.

### Additional Requirements

_From `_bmad-output/planning-artifacts/architecture.md` (the HOW-source-of-truth)._

**Frozen invariants (PRD-v0.5 §2.4 — non-negotiable through v1.0 and forever):**

- **I1:** ulog never auto-classifies records. Tagging is the app's act, never ulog's.
- **I2 / I3 / I7:** Local-first by default. `ulog verify` runs offline. No SaaS, no account, no telemetry, no phone-home.
- **I4:** Records flagged immutable cannot be deleted, ever, by any path (API, SDK, CLI, admin).
- **I5:** `logging.getLogger(__name__).info(...)` continues to work in all ulog versions, forever.
- **I6:** Untagged log calls (`log.error("oops")`) work. Tagging is opt-in. Barrier to entry stays = stdlib.

**Critical architectural decisions (architecture.md step-04):**

- **A1:** Storage shape — column-flag `immutable BOOLEAN` on single `logs` table (not two-table split). SQL trigger blocks UPDATE/DELETE WHERE immutable=1.
- **A2:** Schema upgrade v0.4 → v0.5 — `SchemaError` with explicit ALTER TABLE in error message. New DBs auto-create; existing v0.4 DBs raise SchemaError; existing v0.5 DBs proceed.
- **A3:** Authors cache for JSONL/CSV inputs — sidecar `<logs>.authors.sqlite`. Indexed `(file, line)` PK.
- **B1:** Hash chain hook — encapsulated inside SQL handler, delegated to a `ChainWriter` instance. Hash computed under `BEGIN IMMEDIATE` at INSERT time. JSONL/CSV handlers do NOT participate in chain.
- **B3:** `ChainWriter` abstraction — defined now in `ulog/_chain.py` (Protocol), SQLite impl in v0.5, Postgres impl deferred to v0.7.
- **C1:** CLI consolidation — single `ulog` binary with subcommands. `ulog-web` console_script removed in v0.5.
- **C2:** Pytest plugin packaging — sub-package `ulog/testing/` with `__init__.py` + `pytest_plugin.py`.
- **D1:** Multi-track UI aggregation — server-side bucket aggregation per track, light JSON payload, client-side SVG.
- **E2:** CI gate `dependencies = []` — shell `grep` step in GitHub Actions workflow.

**Implementation patterns (architecture.md step-05) — also locked decisions:**

- **A4:** `chain_pos` is dedicated `INTEGER NOT NULL` column with `ix_logs_chain_pos` index (NOT reusing `id`).
- **B2:** SQLite WAL mode + `BEGIN IMMEDIATE` per chain insert. WAL set once at handler init via `PRAGMA journal_mode=WAL`.
- **B4:** CLI input validators — argparse `type=` callables for simple inputs; multi-step validators in `ulog/_cli/_validators.py`.
- **B5:** `immutable_when()` exception — try/except inside `SQLiteChainWriter.append()`. On exception: stderr (NOT via ulog), treat record as immutable (fail-safe).
- **C3:** `replay()` callback receives `types.MappingProxyType` over the record dict (read-only frozen view).
- **C4:** `_RESERVED` frozenset centralized in `ulog/_reserved.py` (single source). Replaces v0.2 triplication.
- **C5:** `correlate` filter DSL — small grammar, parsed (NOT eval'd), compiled to SQL WHERE / Python predicate. Parser in `ulog/_filter_dsl.py`.
- **D2:** Integrity badge cache — sidecar `<db>.verify_state.json` with `{verified_up_to_chain_pos, last_check_ts, status, broken_at, walk_time_s}`.
- **D3:** Tailwind production migration — stay on CDN through v0.5; standalone CLI build deferred to v0.6.
- **D4:** `/diff/<sha>` rendering — raw `git show` output, HTML-escaped, in `<pre class="font-mono whitespace-pre overflow-x-auto">`. No syntax highlighting (Pygments forbidden by NFR-DEP-50).
- **E1:** Python version matrix — stay 3.10/3.11/3.12/3.13 through v0.5.
- **E3:** Benchmark gating — `pytest-benchmark` in `[dev]` extras; CI advisory mode for first 2 runs to establish baseline.

**Gaps to resolve during v0.5 first sprint (architecture.md step-07):**

- **G1:** Pre-chain records on v0.4→v0.5 upgrade — backfilled records get `chain_pos = id` with NULL `record_hash`/`prev_hash`; first NEW chain record uses `prev_hash = b"\x00"*32`. `ulog verify` walks only non-NULL hash records.
- **G2:** `is_replay=True` flag — new contextvar `_REPLAY_ACTIVE: ContextVar[bool]` in `ulog/replay.py`. Set inside `replay()` context manager.
- **G3:** Issue template `{body}` placeholder — symmetric window: 2 records before + 2 after target by `chain_pos`, JSON list of MappingProxyType views.
- **G4:** OTel detection scope — OTel SDK only via `_OTEL_TRACE_CONTEXT` / `traceparent`. Other tracers bind manually via `ulog.bind(trace_id=...)`. Documented.
- **G5:** `replay_to_pytest` generated test signature — imports `from ulog.testing import replay_records`. Stable signature: `replay_records(records: Sequence[Mapping]) -> ReplaySession`.
- **G6:** `ulog-web` removal transition — RELEASE_NOTES.md prominent entry; no shell stub.
- **G7:** Filter DSL precedence — AND binds tighter than OR. Parentheses supported.
- **G8:** Chain integrity on `min_retention_days` purge of pre-chain records — `purge` only operates on rotable records (immutable=0). Pre-chain backfilled records (NULL record_hash) treated as rotable by default.

**Locked-out libraries (must NOT be added by AI agents):**

- CLI parsing: NOT click/typer/fire → use argparse (stdlib).
- Git: NOT GitPython/pygit2 → use subprocess + porcelain parse.
- Migrations: NOT alembic/yoyo → use SchemaError mechanism.
- Markdown: NOT markdown-it-py/mistune → use `_markdown_to_html` in-house.
- Canonical JSON / hashing: NOT msgpack/orjson/ujson → use `json.dumps(sort_keys=True, separators=(',',':'))`.
- Crypto hash: NOT cryptography → use `hashlib.sha256` (stdlib).
- OTel SDK: NOT opentelemetry-sdk/api → read contextvar / env directly.
- Django tests: NOT pytest-django → use `django.test.Client`.
- Multi-track viz: NOT d3.js/plotly/chart.js → use inline SVG.
- Tailwind production: NOT npm + @tailwindcss/cli → use Tailwind standalone CLI binary (deferred to v0.6).
- Truecolor: NOT colorama/blessed/rich → vendored `ucolor` submodule.
- Datetime: NOT arrow/pendulum → use `datetime` + `zoneinfo` (stdlib).
- Concurrency: NOT trio/anyio → use `threading` + stdlib lock + `BEGIN IMMEDIATE`.
- Issue-tracker SDKs: NOT linear-sdk/github3.py/jira-python → use URL template.
- HTTP client: NOT requests/httpx → use `urllib.request` (stdlib) only if needed.
- Test parametrization helpers: NOT hypothesis/factory_boy → plain pytest.

**Edge case coverage requirements (each MUST have ≥1 test, per SC3):**

- PRD-v0.4 §2.3: 4 edge cases (line deleted, file renamed, squashed/rebased commit, submodule path, no git repo at `--repo`).
- PRD-v0.5 §2.3: 8 edge cases (concurrent writers across processes, chain corruption, `immutable_when` raises, OTel SDK absent, `resolve` references unknown record, `resolve` already-resolved record, `purge` violates retention, hash collision).

**Coverage matrix:** new file `tests/coverage_matrix.md` lists each FR/edge case → test name (SC3 secondary indicator).

### UX Design Requirements

**N/A — no formal UX design specification document exists for ulog-python.** UI requirements are captured directly within the FRs above:

- v0.3 sidebar/detail UI: FR62, FR63, FR64, FR65, FR66.
- v0.4 sidebar/detail UI: FR76, FR77, FR78, FR79, FR80, FR81.
- v0.5 viewer extensions: FR96, FR111, FR112, FR113, FR114, FR115.

The existing v0.2 viewer's UX patterns (Tailwind via CDN, lucide icons, dark-mode bootstrap, ghost-count contract from PRD-v0.2.1) are inherited unchanged. New sidebar sections (Tests / Authors / Incidents) and the multi-track strip follow the existing visual idiom — no new design system work.

### FR Coverage Map

| FR | Epic | Note |
|---|---|---|
| FR51 | Epic 1 | Plugin entry-point registration |
| FR52 | Epic 1 | Plugin OFF by default |
| FR53 | Epic 1 | `--ulog-disable` short-circuit |
| FR54 | Epic 1 | test.started / test.outcome records |
| FR55 | Epic 1 | `test_id` = nodeid (+parametrize) |
| FR56 | Epic 1 | Failure records with traceback |
| FR57 | Epic 1 | Phase field on outcome record |
| FR58 | Epic 1 | Duration from `report.duration` |
| FR59 | Epic 1 | bind/unbind `test_id` at boundaries |
| FR60 | Epic 1 | Application records inherit test_id |
| FR61 | Epic 1 | Fixture records carry test_id |
| FR62 | Epic 1 | Tests sidebar section |
| FR63 | Epic 1 | "Failed only" filter |
| FR64 | Epic 1 | "Slowest top 10" |
| FR65 | Epic 1 | Click test → filter records |
| FR66 | Epic 1 | Detail view "Test context" panel |
| FR67 | Epic 1 | `--ulog-db PATH` flag |
| FR68 | Epic 1 | `--ulog-disable` flag |
| FR69 | Epic 1 | `--ulog-summary` flag |
| FR70 | Epic 2 | `AuthorIndex` API |
| FR71 | Epic 2 | Lazy index build at viewer load |
| FR72 | Epic 2 | `authors` cache table (sidecar A3) |
| FR73 | Epic 2 | `--no-author-index` flag |
| FR74 | Epic 2 | `--repo PATH` resolution |
| FR75 | Epic 2 | `<unknown>` author for off-repo files |
| FR76 | Epic 2 | Authors sidebar section |
| FR77 | Epic 2 | Multi-select OR + URL query |
| FR78 | Epic 2 | "Show unknown" toggle |
| FR79 | Epic 2 | Author ghost counts |
| FR80 | Epic 2 | Detail "Authored by" panel |
| FR81 | Epic 2 | `/diff/<sha>` endpoint with sha validation |
| FR82 | Epic 2 | mtime-based cache invalidation |
| FR83 | Epic 2 | One blame invocation per (file, repo) |
| FR90 | Epic 3 | `immutable_when` predicate plumbing |
| FR91 | Epic 3 | Shared `chain_pos` sequence |
| FR92 | Epic 3 | `min_retention_days` floor |
| FR93 | Epic 3 | `ulog purge --before` |
| FR94 | Epic 3 | sha256 hash chain at write under BEGIN IMMEDIATE |
| FR95 | Epic 3 | `ulog verify [--range]` |
| FR96 | Epic 3 | UI integrity badge (data plumbing) — UI display in Epic 6 |
| FR97 | Epic 3 | `ulog repair --confirm` |
| FR98 | Epic 4 | `ulog.replay()` |
| FR99 | Epic 4 | `is_replaying()` + `is_replay=True` flag |
| FR100 | Epic 4 | `replay_to_pytest()` |
| FR101 | Epic 4 | `ulog correlate <filter>` |
| FR102 | Epic 4 | Correlate small-sample warnings |
| FR103 | Epic 4 | `ulog bisect <pattern>` |
| FR104 | Epic 4 | CLI + Python API for correlate/bisect |
| FR105 | Epic 5 | `ulog.resolve()` |
| FR106 | Epic 5 | `ulog.reopen()` |
| FR107 | Epic 5 | `ulog incidents --status` |
| FR108 | Epic 5 | `ulog incidents --report --since` |
| FR109 | Epic 6 | OTel auto-bind from contextvars |
| FR110 | Epic 6 | `ulog trace <id>` |
| FR111 | Epic 6 | Issue-template URL button (with G3 body shape) |
| FR112 | Epic 6 | Multi-track UI minimal (4 axes SVG) |
| FR113 | Epic 6 | Integrity badge in every page header (UI rendering of FR96) |
| FR114 | Epic 6 | Detail "Resolves/Resolved by" cross-links |
| FR115 | Epic 6 | Sidebar "Incidents" section |
| FR116 | Epic 7 | Doc page `v0.5-forensic-archive.md` |
| FR117 | Epic 7 | Existing doc pages updated (quickstart/storage/api/troubleshooting) |

**NFR & cross-cutting coverage (NFRs apply to multiple epics; primary verification venue listed):**

| Concern | Primary epic | Verification |
|---|---|---|
| NFR-PERF-20 (plugin overhead < 5ms) | Epic 1 | `tests/test_pytest_plugin.py` benchmark |
| NFR-PERF-30 / 31 (indexer + page-load) | Epic 2 | `tests/test_author_index.py` + page-load assert |
| NFR-PERF-50 / 51 (setup + per-log) | Epic 3 | `tests/bench_log.py` |
| NFR-PERF-52 / SC1 (verify ≤5s) | Epic 3 | `tests/bench_verify.py` |
| NFR-PERF-53 / SC2 (correlate ≤500ms) | Epic 4 | `tests/bench_correlate.py` |
| NFR-PERF-54 (bisect ≤100ms / 1M) | Epic 4 | `tests/bench_bisect.py` |
| NFR-PERF-55 / SC7 (multi-track ≤200ms) | Epic 6 | `tests/bench_multitrack.py` |
| NFR-DEP-50 / SC4 (deps = []) | Epic 7 | `.github/workflows/ci.yml` grep gate (E2) |
| NFR-COMPAT-* (pytest 7.0+, mypy strict, I5/SC5) | Epic 1 (pytest) + Epic 7 (qlnes-compat byte-stable) | existing CI + new `test_qlnes_compat.py` |
| NFR-PORT-* (Linux/macOS/Windows) | Epic 1 (xdist) + Epic 2 (git PATH) + Epic 6 (locale fallback) | CI matrix |
| NFR-REL-50 (chain concurrency) | Epic 3 | `tests/test_chain_concurrency.py` (8 writers × 10K) |
| NFR-REL-51 / 52 (replay read-only, repair idempotent) | Epic 4 / Epic 3 | `tests/test_replay.py` / `test_verify.py` |
| NFR-SEC-30 (`/diff/<sha>` validation) | Epic 2 | `tests/test_diff_view.py` |
| NFR-SEC-50 (CLI input validation) | Epic 4 (DSL parser) + Epic 7 (cross-CLI audit) | `tests/test_filter_dsl.py` + `_cli/_validators.py` |
| NFR-SEC-51 (issue URL placeholder encoding) | Epic 6 | template render assertion |
| NFR-DOC-10 (`/docs/test-integration.md`) | Epic 1 | doc file shipped |
| NFR-DOC-30 (`/docs/author-filter.md`) | Epic 2 | doc file shipped |
| NFR-DOC-50 (`v0.5-forensic-archive.md`) | Epic 7 | doc file shipped |
| Invariants I1–I7 | Epic 7 | `STABILITY.md` written + I5/SC5 byte-stable test gate |
| Decisions A1, A2, A4, B1, B2, B3 | Epic 3 | implementation + tests |
| Decision A3 | Epic 2 | sidecar SQLite |
| Decision C2 | Epic 1 | sub-package layout |
| Decisions C3, C5 | Epic 4 | MappingProxyType + DSL parser |
| Decision C4 | Epic 7 | `_RESERVED` centralization refactor |
| Decisions D1, D2, D4 | Epic 6 (D1) + Epic 3 (D2 cache) + Epic 2 (D4) | impl + tests |
| Decisions D3, E1, E3 | Epic 7 | timing notes / matrix / pytest-benchmark setup |
| Decisions C1, E2 | Epic 7 | `ulog` consolidation + grep gate |
| Gap G1 (pre-chain records on upgrade) | Epic 3 | `tests/test_v04_to_v05_upgrade.py` |
| Gap G2 (`_REPLAY_ACTIVE`) | Epic 4 | replay implementation |
| Gap G3 (issue body window) | Epic 6 | issue URL plumbing |
| Gap G4 (OTel scope documented) | Epic 7 | troubleshooting doc |
| Gap G5 (`replay_records` signature) | Epic 1 (sub-package) + Epic 4 (replay impl) | `ulog.testing.replay_records` |
| Gap G6 (`ulog-web` removal RELEASE_NOTES) | Epic 7 | RELEASE_NOTES.md |
| Gap G7 (DSL AND/OR precedence) | Epic 4 | DSL parser tests |
| Gap G8 (purge on pre-chain rows) | Epic 3 | `tests/test_purge.py` |
| Edge cases PRD-v0.4 §2.3 (4 cases) | Epic 2 | `tests/test_author_index.py` |
| Edge cases PRD-v0.5 §2.3 (8 cases) | Epic 3 (5 storage/chain), Epic 4 (1 replay edge), Epic 5 (2 incident edges), Epic 6 (1 OTel absent) | distributed across test files |
| Locked-out libraries audit | Epic 7 | code review checklist + grep gate |

## Epic List

### Epic 1: v0.3 — Test integration

**User outcome:** A pytest user can install `ulog[testing]` and immediately get every test's lifecycle (`test.started`, outcome, duration, traceback) recorded as structured ulog records, with the test's `test_id` propagated to every application log emitted during the test. The viewer adds a "Tests" sidebar with failed-only/slowest-top-10 quick filters and a detail-view "Test context" panel — collapsing the "what did this failing test log?" workflow from grep-CI-output to two clicks.

**FRs covered:** FR51, FR52, FR53, FR54, FR55, FR56, FR57, FR58, FR59, FR60, FR61, FR62, FR63, FR64, FR65, FR66, FR67, FR68, FR69 (19 FRs).

**Standalone:** depends only on v0.2 substrate. Establishes the `ulog/testing/` sub-package convention used by Epic 4 (`replay_records` lives in this same sub-package per Gap G5).

**Implementation notes:**
- New sub-package `ulog/testing/` (Decision C2).
- Pytest plugin auto-discovered via `[project.entry-points.pytest11]`.
- Reuses existing `ulog.context.bind/unbind` (no changes to v0.1 context module).
- UI extends existing `list.html` / `detail.html` / `adapters.py` ghost-count contract.
- xdist on Windows + NFS edge case → fallback to JSONL handler if combination detected (NFR-PORT-10).

---

### Epic 2: v0.4 — Author attribution

**User outcome:** When opening a log file in the viewer with a known git repo, every record gets enriched with the git author of the source line (`git blame`-derived). The user can filter the record list by author (multi-select OR), see "Authored by Lin Wong (commit a3f7c12, 6 days ago)" in the detail panel, and click "view diff" to see the originating commit — collapsing the "who wrote this?" workflow from manual `git blame -L line,line file` to a sidebar tick.

**FRs covered:** FR70, FR71, FR72, FR73, FR74, FR75, FR76, FR77, FR78, FR79, FR80, FR81, FR82, FR83 (14 FRs).

**Standalone:** independent of Epic 1 conceptually. Composes with Epic 1 if both extras are installed (author + test_id can stack on the same record).

**Implementation notes:**
- New module `ulog/web/viewer/blame.py:AuthorIndex`.
- Sidecar `<logs>.authors.sqlite` for JSONL/CSV inputs (Decision A3).
- New `/diff/<sha>` Django view with sha validation (NFR-SEC-30, Decision D4).
- Adapter shape extended (cross-cutting concern #5).
- 4 edge cases of PRD-v0.4 §2.3 each get a test in `tests/test_author_index.py`.
- Subprocess to `git` only — NEVER `os.system` or `shell=True` (locked-out: GitPython).

---

### Epic 3: v0.5 — Storage core & chain integrity

**User outcome:** A compliance officer or library author can verify the cryptographic integrity of the entire log archive offline (`ulog verify` returns OK / BROKEN at #N). Records crossing the immutable threshold (`level >= ERROR` by default) are sealed at write — no API, CLI, admin path can delete them (I4). After upgrade from v0.4, existing records are preserved and a fresh chain begins from the next emit. Schema changes surface via `SchemaError` with literal ALTER TABLE SQL.

**FRs covered:** FR90, FR91, FR92, FR93, FR94, FR95, FR96 (data plumbing — UI rendering in Epic 6), FR97 (8 FRs).

**Standalone:** depends only on v0.2/v0.4 substrate. Foundation for Epics 4, 5, 6 (which all read or write chain).

**Implementation notes:**
- New module `ulog/_chain.py` (Decision B3 ChainWriter Protocol + SQLiteChainWriter impl).
- Extension of `ulog/handlers/sql.py` with chain mode (Decision B1).
- Extension of `ulog/setup.py` with `integrity`, `immutable_when`, `min_retention_days` params.
- New CLI subcommands `cmd_verify.py`, `cmd_repair.py`, `cmd_purge.py` under `ulog/_cli/`.
- WAL + BEGIN IMMEDIATE concurrency (Decision B2). Verified by 8-writer × 10K-record stress test (NFR-REL-50).
- 5 of 8 PRD-v0.5 §2.3 edge cases land here: concurrent writers, chain corruption, `immutable_when` raises, `min_retention_days` violations, hash collision.
- Gap G1 (pre-chain records discontinuity) and G8 (purge on pre-chain rows) resolved here with `tests/test_v04_to_v05_upgrade.py`.

---

### Epic 4: v0.5 — Queryability (replay, correlate, bisect)

**User outcome:** A developer investigating an incident can: (a) replay the records around the incident through a callback or auto-generated pytest fixture (`ulog.replay_to_pytest`), turning a real production incident into a permanent regression test; (b) correlate a filter with all tag dimensions to surface the cause in seconds (`ulog correlate 'level=ERROR AND date>-30min'`); (c) binary-search the chain for the first occurrence of a pattern (`ulog bisect 'db.timeout'`).

**FRs covered:** FR98, FR99, FR100, FR101, FR102, FR103, FR104 (7 FRs).

**Standalone after Epic 3:** depends on chain being live (chain order is what makes bisect deterministic). Independent of Epics 5, 6.

**Implementation notes:**
- New modules `ulog/replay.py`, `ulog/correlate.py`, `ulog/bisect.py`, `ulog/_filter_dsl.py`.
- New CLI subcommands `cmd_replay.py`, `cmd_correlate.py`, `cmd_bisect.py`.
- DSL parser ≤200 LOC, hand-written, NEVER `eval()` (Decision C5, NFR-SEC-50, Gap G7 precedence locked AND tighter than OR).
- `MappingProxyType` callback (Decision C3).
- New contextvar `_REPLAY_ACTIVE` (Gap G2).
- `replay_records` exported from `ulog.testing` (Gap G5 — bridges with Epic 1's sub-package).
- 1 of 8 PRD-v0.5 §2.3 edge cases lands here: replay write attempt blocked.

---

### Epic 5: v0.5 — Incident lifecycle

**User outcome:** A team lead can mark an error record as resolved (`ulog.resolve(hash, by, note)`) emitting an immutable INFO record that references the original by hash. The `ulog incidents --status open` CLI lists all unresolved errors with exit code = open count (CI-gate-friendly). `ulog incidents --report --since 1m` outputs aggregated KPIs (opened/closed/MTTR/P95/reopens) as markdown — postmortems without JIRA. Reopens are first-class.

**FRs covered:** FR105, FR106, FR107, FR108 (4 FRs).

**Standalone after Epic 3:** depends on chain being live (resolution records are themselves chain records).

**Implementation notes:**
- New module `ulog/incidents.py`.
- New CLI subcommand `cmd_incidents.py`.
- UI hooks into Epic 6 (Resolves cross-links + Incidents sidebar — listed under Epic 6 FR114/115 since UI is consolidated there).
- 2 of 8 PRD-v0.5 §2.3 edge cases land here: resolve on unknown record (LookupError), resolve on already-resolved record (allowed, append).

---

### Epic 6: v0.5 — Cross-service & UI extensions

**User outcome:** A platform engineer running multiple services through ulog can correlate a single OTel `trace_id` across all of them (`ulog trace 4bf92f...`). The viewer renders a 4-axis multi-track strip (level/service/author/file) over the time window, with mute toggles for noise reduction. Every record's detail panel has a one-click "Open issue" button populating a tracker-agnostic URL template. The integrity badge is visible on every page header.

**FRs covered:** FR109, FR110, FR111, FR112, FR113, FR114, FR115 (7 FRs).

**Standalone after Epic 3:** depends on chain (for trace_id queries and integrity badge rendering). FR114/115 (UI cross-links + Incidents sidebar) require Epic 5 data flow but UI rendering belongs here for cohesion.

**Implementation notes:**
- OTel detection via stdlib contextvars / env (NEVER `opentelemetry-sdk` import — NFR-DEP-50). Documented as OTel-only scope (Gap G4).
- Multi-track aggregation server-side per Decision D1; new template `multi_track.html` + ~30 LOC vanilla JS.
- Issue button placeholders URL-encoded server-side (NFR-SEC-51); `{body}` window = 2 records before + 2 after by chain_pos (Gap G3).
- Integrity badge reads `<db>.verify_state.json` sidecar (Decision D2).
- Locale fallback for multi-track glyphs (NFR-PORT-50): ▲▼⚡⊕⚠ → `>>` `<<` `!` `+` `WARN` when non-UTF-8 locale.
- 1 of 8 PRD-v0.5 §2.3 edge cases lands here: OTel SDK absent → silent no-op.

---

### Epic 7: v0.5 release — consolidation, documentation & tag

**User outcome:** The v0.5.0 release ships as a coherent, documented, contract-frozen unit. Users get a single `ulog` binary (replacing `ulog-web`) with all v0.3-v0.5 subcommands; doc pages cover every new feature with worked examples; STABILITY.md documents the 7 invariants becoming the v1.0 contract; BENCHMARK.md captures the SC1/SC2/SC7 baselines; RELEASE_NOTES.md guides the `ulog-web → ulog web` transition. The `dependencies = []` regression gate runs in CI on every PR.

**FRs covered:** FR116, FR117 (2 FRs).

**Standalone after Epics 1-6:** consolidation epic — final assembly, no new functional surface.

**Implementation notes:**
- CLI consolidation per Decision C1: `ulog/_cli/__init__.py:main` argparse subparser dispatcher; remove `ulog-web` from `[project.scripts]`.
- `_RESERVED` centralization refactor (Decision C4) — replaces v0.2 triplication with `from ulog._reserved import RESERVED` in 3 importers.
- New top-level docs: `STABILITY.md`, `BENCHMARK.md`, `OUTREACH.md`, `RELEASE_NOTES.md`.
- New in-app doc: `ulog/web/docs/v0.5-forensic-archive.md` (FR116, NFR-DOC-50). Existing 5 doc pages touched (FR117).
- E2 grep gate added to `.github/workflows/ci.yml`.
- Tailwind stays on CDN (Decision D3 — explicit comment in `base.html`).
- pytest-benchmark in `[dev]` extras (Decision E3 — first 2 CI runs advisory).
- I5/SC5 byte-stable regression test `tests/test_qlnes_compat.py` ships as part of this epic.
- Tag `v0.5.0`, push, migrate qlnes (SC6a).

**Sequence within Epic 7:** STABILITY.md & BENCHMARK.md drafted in parallel with prior epics; CLI consolidation lands LAST (after every subcommand introduced in Epics 3-6 exists).

---

## Epic 1: v0.3 — Test integration

A pytest user installs `ulog[testing]` and immediately gets every test's lifecycle recorded as structured ulog records, with `test_id` propagated to every application log emitted during the test. The viewer adds a "Tests" sidebar with quick filters and a detail-view "Test context" panel.

### Story 1.1: Pytest plugin entry-point registration

As a pytest user,
I want `ulog[testing]` to register the pytest plugin via the standard pytest11 entry-point,
So that `pip install ulog[testing]` followed by `pytest` auto-discovers the plugin without manual config.

**Acceptance Criteria:**

**Given** a fresh project with `pip install ulog[testing]`
**When** pytest is invoked
**Then** the plugin module `ulog.testing.pytest_plugin` is loaded automatically
**And** `pytest --trace-config` lists `ulog` in the registered plugins.

**Given** the plugin is loaded but no host `setup()` was called and no `--ulog-db` was passed
**When** pytest runs the test suite
**Then** the plugin is OFF — no `test.started` records are emitted (FR52).

**Given** the plugin is enabled (host `setup()` or `--ulog-db`)
**When** the user passes `--ulog-disable`
**Then** the plugin short-circuits — no `test.started` records emitted (FR53).

---

### Story 1.2: Test event recording (start, outcome, finish)

As a pytest user,
I want every test to emit at least 2 structured records (`test.started`, `test.outcome`) plus an ERROR record on failure with full traceback,
So that I can reconstruct what happened during any test run from the log archive alone.

**Acceptance Criteria:**

**Given** a test that passes
**When** the test runs
**Then** an INFO record `msg="test started"` is emitted at logstart with `test_id` bound
**And** an INFO record `msg="test passed"` with `outcome="passed"`, `duration_s=<float>`, `phase="call"` is emitted at logfinish (FR54, FR58).

**Given** a test that fails on assertion
**When** the test runs
**Then** an ERROR record is emitted with `exc.type`, `exc.msg`, `exc.tb` populated from `report.longrepr` (FR56).

**Given** a teardown failure
**When** pytest finalizes the test
**Then** a separate ERROR record with `phase="teardown"` is emitted (FR57).

---

### Story 1.3: Test ID stability for parametrized tests

As a pytest user,
I want `test_id` to be stable across runs and uniquely identify parametrized variants,
So that filtering by `test_id` returns the same set of records on every run of the same test.

**Acceptance Criteria:**

**Given** a non-parametrized test `tests/test_foo.py::test_bar`
**When** the plugin records its lifecycle
**Then** `test_id == "tests/test_foo.py::test_bar"` (FR55).

**Given** a parametrized test `test_foo[True-1]`
**When** the plugin records its lifecycle
**Then** `test_id == "tests/test_foo.py::test_foo[True-1]"` (FR55).

**Given** the same test run twice
**When** records from both runs are inspected
**Then** the `test_id` values are identical.

---

### Story 1.4: Bound-context propagation of test_id

As a developer instrumenting application code,
I want every `log.info()` / `log.error()` emitted DURING a test to inherit `test_id` automatically,
So that I can filter the viewer to "all records this test produced" without instrumenting each log call.

**Acceptance Criteria:**

**Given** a test `test_audio_render` that calls `log.info("rendering rom")`
**When** the test runs with the plugin enabled
**Then** the application's INFO record carries `test_id="tests/test_audio.py::test_audio_render"` (FR60).

**Given** a fixture's setup or teardown emits a record
**When** the fixture is scoped to a specific test
**Then** the record carries that test's `test_id` (FR61).

**Given** the test has finished
**When** post-test code (other tests' fixtures) emits records
**Then** records do NOT carry the previous `test_id` (unbind happens at logfinish — FR59).

---

### Story 1.5: Pytest CLI flags

As a pytest user,
I want `--ulog-db PATH`, `--ulog-disable`, and `--ulog-summary` flags exposed via pytest's standard option machinery,
So that I can override DB destination, opt out, or get a summary line without modifying conftest.

**Acceptance Criteria:**

**Given** no `setup()` was called by the host
**When** `pytest --ulog-db ./mytests.sqlite` is invoked
**Then** the plugin auto-configures `ulog.setup(handlers=['sql'], sql_url=...)` to that path (FR67).

**Given** the plugin is enabled
**When** `pytest --ulog-disable` is invoked
**Then** no records are emitted by the plugin (FR68).

**Given** `pytest --ulog-summary` (default ON)
**When** the session ends
**Then** a one-line summary appears on stderr: `ulog: N tests, X passed, Y failed, Z skipped → ulog-web ./logs.sqlite to triage` (FR69).

**Given** `pytest -q` is used
**When** the session ends
**Then** the summary line is suppressed (FR69).

---

### Story 1.6: Tests sidebar — list + Failed-only + Slowest-top-10

As a pytest viewer user,
I want a "Tests" sidebar section above "Sectors" listing collected tests grouped by file, with quick filters for "Failed only" and "Slowest top 10",
So that I can triage failures or latency outliers in two clicks.

**Acceptance Criteria:**

**Given** the loaded log file contains test records
**When** the viewer renders `/`
**Then** a "TESTS" sidebar section appears above "Sectors" listing tests grouped by file with outcome badge (✓/✗/⊘) and duration (FR62).

**Given** "Failed only" is ticked
**When** the page reloads
**Then** the records list filters to `outcome IN ('failed', 'errored')` (FR63).

**Given** "Slowest top 10" is ticked
**When** the page reloads
**Then** the records list shows tests sorted by `duration_s DESC LIMIT 10` (FR64).

---

### Story 1.7: Click test name to filter records by test_id

As a pytest viewer user,
I want clicking a test name in the sidebar to filter the record list to that `test_id`, with the filter persisted in the URL,
So that I can share the URL of a specific failing test's records with a colleague.

**Acceptance Criteria:**

**Given** the Tests sidebar is rendered
**When** the user clicks `test_render_alter_ego`
**Then** the record list filters to `test_id="tests/test_audio.py::test_render_alter_ego"`
**And** the URL contains `?test_id=tests%2Ftest_audio.py%3A%3Atest_render_alter_ego` (FR65).

**Given** the URL is opened in a fresh tab
**When** the page renders
**Then** the same filter is applied (URL is the source of truth).

---

### Story 1.8: Detail-view "Test context" panel

As a pytest viewer user inspecting a single record,
I want the detail page to show a "Test context" sub-section for any record that has `test_id`,
So that I can jump from one record to all records for that test or to errors+warnings only.

**Acceptance Criteria:**

**Given** a record's detail view (`/r/<id>/`) where `test_id` is set
**When** the page renders
**Then** a "Test context" panel shows: file:line, outcome badge, duration, phase, total records count, "view all records for this test" link, "view errors+warnings only" link (FR66).

**Given** a record with no `test_id`
**When** the detail view renders
**Then** the "Test context" panel is absent.

---

### Story 1.9: Programmatic `test_event()` API for non-pytest runners

As a developer running tests via a custom runner (not pytest),
I want a programmatic `test_event(name)` context manager exported from `ulog.testing`,
So that I can record test lifecycle events from any test framework without relying on pytest hooks.

**Acceptance Criteria:**

**Given** `from ulog.testing import test_event`
**When** the user wraps test code: `with test_event("custom_test_42") as ev: ... ev.outcome("passed", duration_s=0.42)`
**Then** the same 2-3 records are emitted as for a pytest test (FR54-58).

**Given** the user does not call `ev.outcome(...)` before exiting the context
**When** the context exits
**Then** an `outcome="errored"` record is auto-emitted with the exception info if the block raised, or `outcome="passed"` if no exception.

**Given** the `ulog.testing` sub-package is installed
**When** `from ulog.testing import test_event, replay_records, TestSession` is invoked
**Then** all three names resolve (Gap G5 stable signature anchor).

---

### Story 1.10: xdist + Windows + NFS edge cases

As a CI integrator running tests with `pytest-xdist` on Windows / NFS,
I want the plugin to detect xdist + SQLite + NFS combinations and fall back to JSONL,
So that I don't hit SQLite locking issues silently corrupting the test log.

**Acceptance Criteria:**

**Given** xdist is detected (worker env vars present) AND the SQL handler points at a path on NFS
**When** the plugin initializes
**Then** the SQL handler is silently swapped for JSONL on the same path stem
**And** a warning is printed to stderr (NFR-PORT-10).

**Given** xdist is detected on a local filesystem
**When** the plugin initializes
**Then** SQLite WAL mode is enabled and writes proceed normally.

---

### Story 1.11: Doc page `/docs/test-integration.md`

As a new pytest+ulog user,
I want a doc page covering plugin install, CLI flags, schema, and a "find failed tests" worked example,
So that I can adopt the plugin without reading the PRD.

**Acceptance Criteria:**

**Given** the viewer is running
**When** the user navigates to `/docs/test-integration/`
**Then** the page renders covering: install (`pip install ulog[testing]`), CLI flags (`--ulog-db`, `--ulog-disable`, `--ulog-summary`), test event schema, "find failed tests" worked example (NFR-DOC-10).

**Given** the page is markdown source
**When** the in-house renderer processes it
**Then** it renders without syntax errors (no markdown-it-py dependency).

---

## Epic 2: v0.4 — Author attribution

When opening a log file in the viewer with a known git repo, every record is enriched with the git author of the source line. The user can filter records by author, see "Authored by Lin Wong (commit a3f7c12, 6 days ago)" in the detail panel, and click "view diff" to see the originating commit.

### Story 2.1: `AuthorIndex` API + git blame --porcelain parsing

As a developer integrating author attribution programmatically,
I want `AuthorIndex(repo_root).author_for(file, line) -> Author | None` to resolve any (file, line) pair to a git author via `git blame --porcelain`,
So that I can query authorship without using the viewer.

**Acceptance Criteria:**

**Given** a valid git repo and `(file, line)` referring to tracked code
**When** `idx.author_for("path/to/file.py", 42)` is called
**Then** an `Author(name, email, sha, ts)` is returned (FR70).

**Given** the same `(file, line)` is queried twice
**When** the file's mtime hasn't changed
**Then** the second call uses the cached result (FR82) — no `subprocess.run(['git', 'blame'])` invocation.

**Given** a repo with 100K records spanning 30 unique files
**When** `idx.build()` is invoked
**Then** ≤ 30 forks of `git blame` are observed (FR83).

**Given** the implementation
**When** the source is reviewed
**Then** no `import git` (GitPython) appears anywhere — only `subprocess` + stdlib parsing.

---

### Story 2.2: CLI flags `--repo`, `--no-author-index`, `--rebuild-author-index`

As a viewer user,
I want CLI flags to control author indexing (auto-detect / override / skip / force-rebuild),
So that I can adapt the viewer to different repo layouts and refresh strategies.

**Acceptance Criteria:**

**Given** `ulog web ./logs.sqlite` (no flag)
**When** the viewer starts
**Then** it walks parents of cwd until `.git/` is found and uses that as repo root (FR74).

**Given** no `.git/` is found in cwd parents
**When** the viewer starts
**Then** all records' author resolves to `<unknown>` and stderr prints a one-line warning (FR74).

**Given** `ulog web --repo /path/to/qlnes ./logs.sqlite`
**When** the viewer starts
**Then** `/path/to/qlnes` is used as the git root (FR74).

**Given** `ulog web --no-author-index ./logs.sqlite`
**When** the viewer starts
**Then** the indexer is skipped and the Authors sidebar section is hidden (FR73).

**Given** `ulog web --rebuild-author-index ./logs.sqlite`
**When** the viewer starts
**Then** the cache is invalidated and rebuilt from scratch.

---

### Story 2.3: Lazy index build with stderr progress

As a viewer user opening a 100K-record DB for the first time,
I want the index to build lazily on viewer load with progress printed to stderr,
So that I see what's happening during the ≤5s startup budget.

**Acceptance Criteria:**

**Given** a fresh viewer launch with `--repo` set and no existing cache
**When** the index builds
**Then** progress lines are printed to stderr like `ulog: indexing authors... 30 files, 12500/100000 records (12%)` (FR71).

**Given** the index build completes
**When** the budget is measured
**Then** total wall-time ≤ 5s on a 100K-record DB / 30-file repo (NFR-PERF-30).

---

### Story 2.4: `authors` cache table + sidecar SQLite for JSONL/CSV

As a viewer user opening a JSONL or CSV log file,
I want author cache to live in a sidecar `<logs>.authors.sqlite` next to the source file,
So that subsequent loads reuse the cache without re-blaming.

**Acceptance Criteria:**

**Given** an SQLite log DB at `./logs.sqlite` with author indexing enabled
**When** the index builds
**Then** an `authors` table exists in the SAME DB with PK `(file, line)` and columns `(author_name, author_email, commit_sha, commit_ts)` (FR72).

**Given** a JSONL log file at `./logs.jsonl` with author indexing enabled
**When** the index builds
**Then** a sidecar SQLite `./logs.jsonl.authors.sqlite` is created with the same schema (Decision A3).

**Given** the same JSONL file is reloaded after a fresh build
**When** the viewer starts
**Then** no new `git blame` invocation occurs (cache reused, mtime checked).

---

### Story 2.5: `<unknown>` author handling

As a viewer user with logs that reference files not in the current repo,
I want those records to show `<unknown>` in the Authors sidebar with a count,
So that I can include or exclude them deliberately.

**Acceptance Criteria:**

**Given** a record references `external/lib.py:42` which is not present in `--repo`
**When** the index queries for that pair
**Then** `idx.author_for(...)` returns `None`
**And** the record's author display is `<unknown>` (FR75).

**Given** records with `<unknown>` author exist
**When** the Authors sidebar renders
**Then** an `<unknown> (N)` entry appears with the count of such records.

---

### Story 2.6: Authors sidebar section with ghost counts

As a viewer user filtering by author,
I want a multi-select Authors sidebar section that honors the v0.2.1 ghost-count contract,
So that ticking authors doesn't zero out other authors' counts.

**Acceptance Criteria:**

**Given** the Authors section shows 4 authors with counts (412, 89, 24, 3)
**When** the user ticks "Lin Wong" alone
**Then** the records list filters to Lin's records, but the OTHER authors' counts remain non-zero (computed against all-filters-EXCEPT-author per PRD-v0.2.1) (FR79).

**Given** the section
**When** rendered
**Then** it sits between "Files" and "Time range" sections (FR76).

---

### Story 2.7: Multi-select OR + URL query string + "Show unknown"

As a viewer user combining author filters,
I want multi-select with OR semantics (tick Johan + Sara → records by either), persisted in URL,
So that I can share the URL of a specific author combination.

**Acceptance Criteria:**

**Given** "Johan" and "Sara" are ticked
**When** the page reloads
**Then** records filter to `author IN (johan@..., sara@...)`
**And** the URL contains `?author=johan@...&author=sara@...` (FR77).

**Given** "Show unknown" checkbox (default ON)
**When** unchecked
**Then** records with `<unknown>` author are hidden from the list (FR78).

---

### Story 2.8: Detail-view "Authored by" panel

As a viewer user investigating a specific record,
I want a detail-view sub-section with the author's name, email, commit short-sha, relative date, and links to "all records from this author" + "view diff",
So that I can pivot from one record to context.

**Acceptance Criteria:**

**Given** a record's detail view with author resolved
**When** the page renders
**Then** the "Authored by" panel shows: name + truncated email + 7-char short-sha + relative date (`6 days ago`) + 2 links (FR80).

**Given** the "view diff" link
**When** clicked
**Then** it navigates to `/diff/<commit_sha>`.

---

### Story 2.9: `/diff/<sha>` view with sha validation

As a viewer user clicking "view diff",
I want the server to validate the sha (hex regex + `git rev-parse --verify`) and render `git show <sha>` output safely,
So that no shell injection or arbitrary command is possible.

**Acceptance Criteria:**

**Given** a request to `/diff/a3f7c12abc`
**When** the server handles it
**Then** the sha is validated against `[0-9a-f]{4,40}` first (NFR-SEC-30, FR81).

**Given** an invalid sha (e.g. `abc; rm -rf /`)
**When** the server validates it
**Then** the request returns 400 Bad Request without invoking any subprocess.

**Given** a valid sha
**When** the server runs `git rev-parse --verify <sha>` followed by `git show <sha>`
**Then** the output is HTML-escaped and rendered in `<pre class="font-mono whitespace-pre overflow-x-auto">` (Decision D4).

**Given** the sha is valid hex but unreachable in the repo
**When** the server runs `rev-parse --verify`
**Then** it returns 404 with a friendly message.

---

### Story 2.10: 4 PRD-v0.4 §2.3 edge cases as tests

As a release manager,
I want each of the 4 PRD-v0.4 §2.3 edge cases (line deleted, file renamed, squashed/rebased, submodule, no-git) covered by ≥1 test in `tests/test_author_index.py`,
So that the indexer's behavior on git pathologies is regression-protected.

**Acceptance Criteria:**

**Given** a synthetic repo where a file shrunk and a record references a now-out-of-range line
**When** `idx.author_for(...)` is called
**Then** it returns `None` and the record gets `blame_skip_reason="line-out-of-range"` (PRD-v0.4 §2.3).

**Given** a synthetic repo with `git mv` of a file
**When** `idx.author_for(...)` is called on the new path with a record from the old path
**Then** `git blame --follow -C -M` is used and resolves the author correctly.

**Given** a cached `commit_sha` no longer reachable after `git gc`
**When** `/diff/<sha>` is requested
**Then** `git rev-parse --verify` fails and a 404 is returned with the cached author/date still visible in the detail panel.

**Given** a file under a `.gitmodules`-tracked path
**When** `idx.author_for(...)` is called
**Then** the blame runs against the submodule's git history.

**Given** `--repo` points at a directory with no `.git`
**When** the viewer starts
**Then** all records get `<unknown>` author and a stderr warning is printed (FR74).

---

### Story 2.11: Doc page `/docs/author-filter.md`

As a new author-filter user,
I want a doc page covering how it works, what `<unknown>` means, the "code author vs commit author" distinction, and a worked example,
So that I understand the feature without reading the PRD.

**Acceptance Criteria:**

**Given** the viewer is running
**When** the user navigates to `/docs/author-filter/`
**Then** the page renders covering: indexer mechanics, `<unknown>` semantics, code-author-vs-commit-author note, "find errors in code Lin wrote this week" worked example (NFR-DOC-30).

---

## Epic 3: v0.5 — Storage core & chain integrity

A compliance officer or library author can verify the cryptographic integrity of the entire log archive offline. Records crossing the immutable threshold are sealed at write — no API, CLI, admin path can delete them. After upgrade from v0.4, existing records are preserved and a fresh chain begins from the next emit.

### Story 3.1: Schema extension — immutable + chain_pos + record_hash + prev_hash columns

As a developer running the v0.5 SQL handler against a fresh DB,
I want the `logs` table to include `immutable BOOLEAN`, `chain_pos INTEGER`, `record_hash BLOB(32)`, `prev_hash BLOB(32)` columns with proper indexes,
So that chain integrity and immutability are first-class schema concerns.

**Acceptance Criteria:**

**Given** a fresh SQLite DB
**When** `SQLHandler` initializes with `integrity='hash-chain'`
**Then** `metadata.create_all()` creates the `logs` table with the 4 new columns plus `ix_logs_chain_pos` and `ix_logs_immutable` indexes (Decision A1, A4).

**Given** the `chain_pos` column
**When** records are inserted
**Then** values are unique and monotonic (verified by SQL constraint or insertion logic, see Story 3.4).

**Given** the `immutable` column
**When** records are inserted
**Then** value is `INTEGER` (0 or 1), NOT `BOOLEAN` (Decision: explicit INTEGER for SQL DDL clarity).

---

### Story 3.2: SQL trigger blocking UPDATE/DELETE on immutable rows

As a compliance officer (Erika persona),
I want a SQL trigger to block any UPDATE or DELETE on a row where `immutable=1`,
So that invariant I4 is enforced at the storage layer regardless of who connects to the DB.

**Acceptance Criteria:**

**Given** an immutable record (immutable=1) exists
**When** any client attempts `UPDATE logs SET msg='tampered' WHERE id=<n>`
**Then** the trigger raises (SQL error) and the UPDATE is rolled back.

**Given** an immutable record (immutable=1) exists
**When** any client attempts `DELETE FROM logs WHERE id=<n>`
**Then** the trigger raises and the DELETE is rolled back.

**Given** a rotable record (immutable=0)
**When** UPDATE/DELETE is attempted
**Then** the operation succeeds (rotation/purge path).

---

### Story 3.3: `SchemaError` upgrade message with literal ALTER TABLE SQL

As a v0.4 user upgrading to v0.5,
I want `SchemaError` to fire with the exact ALTER TABLE statements I need to run,
So that I can copy-paste the SQL without consulting external docs.

**Acceptance Criteria:**

**Given** a v0.4 SQLite DB (no `chain_pos`/`record_hash`/`prev_hash`/`immutable` columns)
**When** v0.5 `SQLHandler` initializes against it
**Then** `SchemaError` is raised with msg containing the literal SQL: `ALTER TABLE logs ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0; ALTER TABLE logs ADD COLUMN record_hash BLOB; ALTER TABLE logs ADD COLUMN prev_hash BLOB; ALTER TABLE logs ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0; CREATE INDEX ix_logs_chain_pos ON logs(chain_pos); CREATE INDEX ix_logs_immutable ON logs(immutable);` (Decision A2, Gap G1 documents discontinuity).

**Given** the user runs the suggested SQL
**When** v0.5 `SQLHandler` re-initializes
**Then** it proceeds. Backfilled rows have `chain_pos = id` (default 0 then UPDATE), NULL `record_hash`/`prev_hash`. The first NEW chain record uses `prev_hash = b"\x00" * 32` (Gap G1).

---

### Story 3.4: `ChainWriter` Protocol + `SQLiteChainWriter` impl

As a v0.5 implementer,
I want a small `ChainWriter` Protocol in `ulog/_chain.py` with a SQLite impl,
So that chain-related tests can mock the backend and v0.7 can swap in Postgres without touching `SQLHandler`.

**Acceptance Criteria:**

**Given** `ulog/_chain.py`
**When** the file is imported
**Then** it exports a `ChainWriter` Protocol with `get_last_hash() -> bytes` and `append(record: dict, record_hash: bytes, prev_hash: bytes) -> int` (Decision B3).

**Given** `SQLiteChainWriter(engine, table_name)`
**When** `append(...)` is called
**Then** the row is inserted with the next `chain_pos` and the hash columns populated, all under a single `BEGIN IMMEDIATE` transaction (Decision B1, B2).

**Given** unit tests for chain logic
**When** they run
**Then** they use a mock `ChainWriter` and never require an actual SQLite DB.

---

### Story 3.5: `SQLHandler` chain integration + WAL mode + BEGIN IMMEDIATE

As a v0.5 user enabling chain mode,
I want `setup(integrity='hash-chain')` to wire the `SQLiteChainWriter` into the SQL handler's emit path under WAL + BEGIN IMMEDIATE,
So that multi-process writers serialize on the chain without blocking readers.

**Acceptance Criteria:**

**Given** `setup(integrity='hash-chain', handlers=['sql'])`
**When** the SQL handler is constructed
**Then** `PRAGMA journal_mode=WAL` is executed once at engine init (Decision B2).

**Given** a record passed to `emit()`
**When** the handler decides to flush (batch full or atexit)
**Then** the canonical JSON is computed via `json.dumps(sort_keys=True, separators=(',',':'))` (Decision: stdlib json, no msgpack/orjson).

**Given** the canonical JSON bytes
**When** the hash is computed
**Then** `record_hash = hashlib.sha256(canonical + prev_hash).digest()` is used (no external crypto lib).

**Given** 8 concurrent writer processes each emitting 10K records
**When** the chain is verified post-run
**Then** the chain is unbroken (NFR-REL-50).

---

### Story 3.6: `setup()` new params (integrity, immutable_when, min_retention_days)

As a developer configuring v0.5,
I want `ulog.setup()` to accept `integrity`, `immutable_when`, and `min_retention_days` parameters,
So that I can opt into chain mode and immutability with a single call.

**Acceptance Criteria:**

**Given** `setup(integrity='hash-chain')`
**When** the chain mode is active
**Then** records are persisted with chain hash columns populated (FR94).

**Given** `setup(integrity='none')`
**When** records are emitted
**Then** chain columns remain NULL — the handler runs in v0.4-compatible mode.

**Given** `setup(immutable_when=lambda r: r.levelno >= logging.ERROR)`
**When** an ERROR record is emitted
**Then** the row is persisted with `immutable=1` (FR90).

**Given** `setup(min_retention_days=730)`
**When** any rotation/purge is attempted
**Then** records younger than `today − 730 days` are refused (FR92).

---

### Story 3.7: `ulog verify [--range A-B]` CLI subcommand

As a compliance officer,
I want `ulog verify` to walk the chain offline and report OK or BROKEN at #N with the expected and actual hashes,
So that I can include integrity attestation in audit reports.

**Acceptance Criteria:**

**Given** an unbroken chain of N records
**When** `ulog verify` runs
**Then** stdout shows `✓ Integrity verified` with `records: N`, walk time, exit code 0 (FR95).

**Given** a broken chain at record #142,071
**When** `ulog verify` runs
**Then** stdout shows `✗ BROKEN at record #142,071: expected prev_hash=8aef21..., got 0123ab...`, exit code 1 (FR95).

**Given** `ulog verify --range 100000-100500`
**When** invoked
**Then** only that sub-range is walked and reported on.

**Given** a 100K-record DB on GitHub Actions ubuntu-latest
**When** `ulog verify` runs
**Then** wall time ≤ 5s (NFR-PERF-52, SC1).

---

### Story 3.8: `ulog repair --confirm` CLI subcommand

As a compliance officer responding to a verify-BROKEN result,
I want `ulog repair --confirm` to truncate the chain at the last valid record and archive orphans into a sidecar log,
So that I can recover write capability without losing forensic evidence.

**Acceptance Criteria:**

**Given** a broken chain
**When** `ulog repair --confirm` runs
**Then** all records after the last valid `chain_pos` are moved into `<db>.chain_break_<ts>.log` (one JSON per line) and removed from the live DB (FR97).

**Given** `ulog repair` is invoked without `--confirm`
**When** the user runs it
**Then** the command refuses with "Use --confirm to proceed; this is destructive of the live chain" (FR97).

**Given** a healthy chain
**When** `ulog repair --confirm` runs
**Then** it is a no-op (NFR-REL-52 — idempotent).

---

### Story 3.9: `ulog purge --before <date>` CLI subcommand

As an operator running disk-cleanup against rotable records,
I want `ulog purge --before <date>` to drop only rotable records older than the given date, refusing if `min_retention_days` would be violated,
So that I can clean up safely without breaching compliance.

**Acceptance Criteria:**

**Given** records with `immutable=0` older than the given date
**When** `ulog purge --before 2024-06-01` runs
**Then** those records are deleted and the count is printed (FR93).

**Given** records with `immutable=1` older than the given date
**When** `ulog purge --before` runs
**Then** they are NOT deleted (I4 enforced).

**Given** `min_retention_days=730` is set and the date would drop records younger than `today − 730 days`
**When** purge runs
**Then** it refuses with non-zero exit code and a summary of how many records would have been dropped (PRD-v0.5 §2.3 edge case).

**Given** pre-chain backfilled records (NULL record_hash) older than the given date
**When** purge runs
**Then** they are treated as rotable by default and dropped (Gap G8).

---

### Story 3.10: Integrity badge data plumbing — `<db>.verify_state.json` sidecar

As a backend for the UI integrity badge,
I want `ulog verify` to write its result to `<db>.verify_state.json` next to the SQLite DB,
So that the viewer can read the cached state cheaply on every page-load.

**Acceptance Criteria:**

**Given** `ulog verify` completes successfully
**When** it exits
**Then** `<db>.verify_state.json` is written with `{verified_up_to_chain_pos, last_check_ts, status: "OK", broken_at: null, walk_time_s}` (Decision D2).

**Given** `ulog verify` reports BROKEN at #N
**When** it exits
**Then** the JSON has `status: "BROKEN", broken_at: N`.

**Given** the JSON file is missing
**When** the viewer reads it
**Then** the badge shows "never verified" without raising (graceful degrade).

---

### Story 3.11: Concurrency stress test (8 writers × 10K records)

As a release manager,
I want a stress test that spawns 8 concurrent writer processes each emitting 10K records,
So that the chain integrity is empirically validated under contention before tagging v0.5.0.

**Acceptance Criteria:**

**Given** `tests/test_chain_concurrency.py` is invoked
**When** 8 subprocesses each emit 10K records to a shared SQLite DB
**Then** total record count = 80K and the chain is unbroken (NFR-REL-50).

**Given** the test runs on Linux/macOS/Windows
**When** observed
**Then** no SQLite "database is locked" error escapes (BEGIN IMMEDIATE retries are handled).

---

### Story 3.12: PRD-v0.5 §2.3 edge cases for storage/chain (5 of 8)

As a release manager,
I want each of 5 PRD-v0.5 §2.3 storage/chain edge cases covered by ≥1 test,
So that exotic conditions don't cause silent corruption.

**Acceptance Criteria:**

**Given** chain corruption is detected by `ulog verify`
**When** a subsequent `setup()` attempts to write
**Then** writes are blocked until `ulog repair --confirm` runs (PRD-v0.5 §2.3).

**Given** an `immutable_when` predicate that raises an exception on a record
**When** the SQL handler processes it
**Then** the record is treated as immutable (fail-safe) and the exception is logged to stderr via `print(..., file=sys.stderr)` (NOT via ulog, to avoid recursion) (Decision B5).

**Given** a hash collision is theoretically observed (no realistic test, but logic check)
**When** `ulog verify` walks the colliding pair
**Then** it reports BROKEN at the collision point (PRD-v0.5 §2.3).

**Given** `min_retention_days=N` and `ulog purge --before <date>` would violate it
**When** purge runs
**Then** non-zero exit code + summary (PRD-v0.5 §2.3).

**Given** 8 concurrent writers (covered by Story 3.11) — referenced.

---

## Epic 4: v0.5 — Queryability (replay, correlate, bisect)

A developer investigating an incident can replay records through a callback or auto-generated pytest fixture, correlate a filter with all tag dimensions to surface the cause, or binary-search the chain for a pattern.

### Story 4.1: `replay()` core + MappingProxyType callback

As a developer reproducing a production incident locally,
I want `ulog.replay(filter=..., on=callback)` to iterate matching records in chain order and call my callback with a read-only frozen view,
So that I can analyze the records without risk of mutation.

**Acceptance Criteria:**

**Given** a filter and a callback
**When** `ulog.replay(filter='resolves="abc"', on=callback)` is invoked
**Then** matching records are iterated in chain order (`chain_pos ASC`) and each is wrapped in `types.MappingProxyType` before being passed to `callback` (FR98, Decision C3).

**Given** the callback attempts `record["msg"] = "modified"`
**When** the line executes
**Then** `TypeError` is raised (immutable proxy).

---

### Story 4.2: `_REPLAY_ACTIVE` contextvar + `is_replaying()` + `is_replay=True` flag

As an observer of replay-emitted records,
I want any record emitted during a replay to be marked `is_replay=True` automatically,
So that I can distinguish replay-induced records from production records and prevent infinite-loop scenarios.

**Acceptance Criteria:**

**Given** new contextvar `_REPLAY_ACTIVE: ContextVar[bool]` defined in `ulog/replay.py`
**When** `replay()` enters its body
**Then** `_REPLAY_ACTIVE.set(True)` is called; on exit, the prior value is restored (Gap G2).

**Given** `_REPLAY_ACTIVE` is True
**When** any code calls `log.error(...)` inside the callback
**Then** the resulting record carries `is_replay=True` (stamped by the SQL handler at insert time per FR99, NFR-REL-51).

**Given** `ulog.is_replaying()` is called
**When** outside a replay context
**Then** it returns `False`.

---

### Story 4.3: `replay_to_pytest()` generator

As a developer turning a real incident into a permanent regression test,
I want `ulog.replay_to_pytest(filter, output_path)` to generate a `tests/test_incident_<hash>.py` file with the records snapshotted and an assertion stub,
So that the production incident becomes a CI-gated test.

**Acceptance Criteria:**

**Given** `ulog.replay_to_pytest(filter='resolves="3f7c12a..."', output_path="tests/test_incident_3f7c12a.py")`
**When** invoked
**Then** the file is written with: header comment (auto-generated, hash, date), `import pytest`, `from ulog.testing import replay_records`, `INCIDENT_RECORDS = [...]` (frozen-dict literal of matching records), and a `def test_incident_3f7c12a_<topic>():` stub asserting the new code path (FR100).

**Given** the generated file is run as `pytest tests/test_incident_3f7c12a.py`
**When** the test executes
**Then** `replay_records(INCIDENT_RECORDS)` works (Gap G5 stable signature: `replay_records(records: Sequence[Mapping]) -> ReplaySession`).

---

### Story 4.4: Filter DSL parser

As a CLI user composing filters,
I want a small grammar (`level=ERROR AND date>-30min`, `key~regex`, parentheses, etc.) parsed (NOT eval'd) and compiled to SQL or Python predicate,
So that I can express queries without shell-injection risk.

**Acceptance Criteria:**

**Given** the filter `level=ERROR AND date>-30min`
**When** `_filter_dsl.parse(...)` is called
**Then** an AST is returned (no `eval()` ever called) (NFR-SEC-50, Decision C5).

**Given** the AST
**When** compiled to SQL
**Then** a parameterized SQLAlchemy expression is produced (no string concatenation of user input).

**Given** `level=ERROR OR level=WARN AND service=payment`
**When** parsed
**Then** AND binds tighter than OR (precedence: AND > OR, Gap G7).

**Given** `(level=ERROR OR level=WARN) AND service=payment`
**When** parsed
**Then** parentheses override precedence as expected.

**Given** an injection attempt `level=ERROR; DROP TABLE logs`
**When** parsed
**Then** a parse error is raised before any SQL is generated.

---

### Story 4.5: `correlate()` core (lift formula + GROUP BY SQL)

As a developer investigating a spike,
I want `ulog.correlate(filter)` to compute lift = P(tag=v | filter) / P(tag=v | not filter) for every (tag, value) pair in the records,
So that I can find the over-represented dimensions in the spike in seconds.

**Acceptance Criteria:**

**Given** a filter `level=ERROR AND date>-30min` against a 10K-filter / 1M-baseline DB
**When** `correlate()` is called
**Then** a `CorrelationReport` is returned with `top_over` (10 entries by lift DESC) and `bottom_under` (5 entries by lift ASC) (FR101).

**Given** the SQL produced
**When** inspected
**Then** it is a single `GROUP BY tag_name, tag_value` with `COUNT(*) FILTER (WHERE filter)` clauses.

**Given** an index on `(tag_name, tag_value)` is needed for perf
**When** the schema is set up by Story 3.1's chain mode
**Then** that index exists (or is added in this story).

**Given** the 10K/1M DB on GitHub Actions
**When** correlate runs
**Then** wall time ≤ 500ms (NFR-PERF-53, SC2).

---

### Story 4.6: `correlate()` small-sample warnings + axis-skip

As a user interpreting correlate output,
I want explicit warnings when the in-filter sample is < 30 (small-sample bias) and when an axis is included but is the filter axis itself (lift forced to 0/∞),
So that I don't draw wrong conclusions from spurious lifts.

**Acceptance Criteria:**

**Given** `in_filter < 30` for a tag/value pair
**When** correlate emits its report
**Then** a warning row is included: `⚠ Sample size N — interpret confidence ≥ in_filter / 30` (FR102).

**Given** the filter is `level=ERROR` and the report includes `level=ERROR` as a dimension
**When** the lift would be 0 or ∞
**Then** the row is annotated `(axis)` and excluded from the rank (FR102).

---

### Story 4.7: `bisect()` binary search over chain

As a developer wanting to know when a pattern first appeared,
I want `ulog.bisect(pattern)` to binary-search the chain and return the first matching record + v0.4 commit context,
So that I can correlate a regression to a specific commit.

**Acceptance Criteria:**

**Given** a pattern (regex) and a 1M-record chain
**When** `bisect()` runs
**Then** the first record matching the pattern (regex over `msg`, `extras`, `tags`) is returned (FR103).

**Given** the operation
**When** measured
**Then** wall time ≤ 100ms on the 1M chain (NFR-PERF-54).

**Given** the matched record exists
**When** the result is rendered
**Then** the v0.4 commit context (author + sha + diff link) is included (FR103).

**Given** the pattern compiles as a Python `re.compile(...)`
**When** the user passes `'.*[a-z]+'`
**Then** no shell expansion occurs (pattern is treated as Python regex literal — NFR-SEC-50).

---

### Story 4.8: `ulog correlate` / `bisect` / `replay` CLI subcommands

As a CLI user,
I want each query operation exposed as a subcommand under the consolidated `ulog` binary,
So that I can run them from a shell without writing Python.

**Acceptance Criteria:**

**Given** the `ulog` binary
**When** `ulog correlate 'level=ERROR AND date>-30min' --db ./logs.sqlite` is invoked
**Then** the report is printed in the formatted text shown in PRD-v0.5 §6.1 with locale-aware glyphs (FR104).

**Given** `ulog bisect 'db.timeout' --db ./logs.sqlite`
**When** invoked
**Then** the first matching record + commit context is printed (FR104).

**Given** `ulog replay --filter 'resolves="abc"' --to-pytest tests/test_inc.py --db ./logs.sqlite`
**When** invoked
**Then** the test file is generated as in Story 4.3.

---

### Story 4.9: `replay_records` context manager in `ulog/testing/`

As a generated regression test,
I want `from ulog.testing import replay_records` to import a context manager that replays a frozen list of records and tracks emitted records for assertions,
So that the generated tests have a stable, simple API.

**Acceptance Criteria:**

**Given** `with replay_records(INCIDENT_RECORDS) as session:`
**When** the body runs
**Then** records are emitted as if from production, with `is_replay=True` flag, and `session.matches(predicate)` returns True iff any emitted record matches (Gap G5).

**Given** the test asserts `assert not session.matches(lambda r: r.extras.get("db_timeout"))`
**When** no record carries `db_timeout=True`
**Then** the assertion passes.

---

### Story 4.10: PRD-v0.5 §2.3 edge case — replay write attempt

As a developer chasing an infinite-loop scenario,
I want any write to the chain DURING replay to be flagged `is_replay=True` and NOT participate in chain integrity,
So that replay records don't pollute the production chain.

**Acceptance Criteria:**

**Given** `_REPLAY_ACTIVE.get() == True`
**When** the SQL handler processes a record
**Then** the record is persisted with `is_replay=True` extra AND its `record_hash`/`prev_hash` columns are NULL (does not advance chain) (NFR-REL-51).

---

## Epic 5: v0.5 — Incident lifecycle

A team lead can mark an error record as resolved emitting an immutable INFO record. The `ulog incidents` CLI lists open incidents with exit code = open count and outputs aggregated KPIs as markdown.

### Story 5.1: `ulog.resolve()` API + foreign-key validation

As a team lead closing an incident,
I want `ulog.resolve(incident_hash, by, note)` to emit a new immutable INFO record with `resolves=<hash>`,
So that the resolution is part of the chain and references the original.

**Acceptance Criteria:**

**Given** a record with hash `3f7c12a...` exists in the chain
**When** `ulog.resolve(incident_hash="3f7c12a...", by="Johan", note="...")` is called
**Then** a new record is emitted with `level=INFO`, `msg="RESOLVED"`, `resolves="3f7c12a..."`, `by="Johan"`, `note="..."`, `commit_sha=<HEAD>` (FR105).

**Given** the new record
**When** persisted
**Then** it is in the chain with chain_pos = previous max + 1 and is `immutable=1`.

**Given** `incident_hash` references a record NOT in the DB
**When** `resolve()` is called
**Then** `LookupError` is raised; no record is emitted (PRD-v0.5 §2.3 edge case).

---

### Story 5.2: `ulog.reopen()` API

As a team lead discovering that "the fix didn't work",
I want `ulog.reopen(incident_hash, reason)` to emit a `msg="REOPENED"` record referencing the original,
So that the incident lifecycle accurately reflects reality.

**Acceptance Criteria:**

**Given** a record `3f7c12a...` was previously resolved
**When** `ulog.reopen(incident_hash="3f7c12a...", reason="recurrence at 2026-05-04")` is called
**Then** a new record is emitted with `msg="REOPENED"`, `resolves="3f7c12a..."`, `reason="..."` (FR106).

**Given** an incident that was resolved then reopened then resolved again
**When** the chain is walked
**Then** the incident's current state is "resolved" (latest resolution wins per FR106).

**Given** `resolve()` is called on an already-resolved record
**When** invoked
**Then** it is allowed — emits another resolution record. The chain shows a sequence of resolutions (PRD-v0.5 §2.3 edge case).

---

### Story 5.3: Incident state walk (chain-derived latest-wins)

As a UI or CLI consumer needing the open/closed state,
I want a pure function that walks the chain and returns the current state of each incident,
So that the latest-wins semantics is implemented in one place.

**Acceptance Criteria:**

**Given** a chain with mixed RESOLVED / REOPENED records
**When** `incidents.compute_states(adapter)` is called
**Then** a dict `{incident_hash: ("open"|"closed"|"reopened", last_action_record)}` is returned, where state is determined by the latest action referencing that hash.

**Given** a record never resolved
**When** the walk completes
**Then** it appears as `"open"` in the result.

---

### Story 5.4: `ulog incidents --status` CLI + exit code

As a CI gate enforcer,
I want `ulog incidents --status open` to print all open incidents and return an exit code = open count,
So that I can fail the build if open incidents exceed a threshold.

**Acceptance Criteria:**

**Given** 3 open incidents
**When** `ulog incidents --status open --db ./logs.sqlite` runs
**Then** stdout lists the 3 incidents (one per line: `#<chain_pos>  <date>  <msg>  <age>`) and exit code = 3 (FR107).

**Given** `--status closed` and 5 closed incidents in the last week
**When** invoked
**Then** the closed list is shown.

**Given** `--status all`
**When** invoked
**Then** every incident-bearing record is shown with its current state.

---

### Story 5.5: `ulog incidents --report --since` markdown KPIs

As a tech lead writing a postmortem,
I want `ulog incidents --report --since 1m` to output aggregated KPIs (opened/closed/net debt/MTTR/P95/reopens/top closers) as markdown,
So that I can paste it directly into a postmortem doc.

**Acceptance Criteria:**

**Given** 1 month of incident records
**When** `ulog incidents --report --since 1m --db ./logs.sqlite` runs
**Then** stdout contains a markdown table with: opened count, closed count, net debt, MTTR, P95 time-to-close, reopens count, top closers list (FR108).

**Given** the output is piped to a file
**When** opened in a markdown viewer
**Then** it renders correctly without escapes.

---

### Story 5.6: PRD-v0.5 §2.3 edge cases — resolve unknown / already-resolved

As a release manager,
I want both incident edge cases covered by ≥1 test in `tests/test_incidents.py`,
So that surprising user inputs don't silently corrupt the chain.

**Acceptance Criteria:**

**Given** `ulog.resolve(incident_hash="0000...not-in-db")`
**When** invoked
**Then** `LookupError` is raised, no record emitted (PRD-v0.5 §2.3, FR105 FK validation).

**Given** `ulog.resolve(incident_hash="3f7c12a...")` was called previously
**When** `ulog.resolve(incident_hash="3f7c12a...")` is called again with new args
**Then** it is allowed — emits another RESOLVED record, the chain shows both, and the latest wins (PRD-v0.5 §2.3).

---

## Epic 6: v0.5 — Cross-service & UI extensions

A platform engineer can correlate a single OTel trace_id across services. The viewer renders a 4-axis multi-track strip with mute toggles, an Issue button populating a tracker-agnostic URL, and an integrity badge on every page.

### Story 6.1: OTel auto-bind from contextvar / env

As a platform engineer running services with OTel,
I want ulog to auto-attach `trace_id` and `span_id` to every record when an OTel context is present,
So that I get cross-service correlation for free without instrumenting each `log.error` call.

**Acceptance Criteria:**

**Given** the contextvar `_OTEL_TRACE_CONTEXT` is set with `{trace_id, span_id}`
**When** any record is emitted
**Then** `trace_id` and `span_id` are attached to the record's context (FR109).

**Given** the env var `traceparent` is set (W3C Trace Context)
**When** a record is emitted with no contextvar set
**Then** `trace_id` is parsed from `traceparent` and attached (FR109).

**Given** neither contextvar nor env is set
**When** a record is emitted
**Then** no `trace_id` is attached, no warning printed (silent no-op — Gap G4 documented).

**Given** the implementation
**When** the source is reviewed
**Then** no `import opentelemetry` appears (NFR-DEP-50; reads contextvars/env directly).

---

### Story 6.2: `ulog trace <id>` CLI subcommand

As an engineer debugging a distributed bug,
I want `ulog trace <id>` to list all records sharing a trace_id chronologically,
So that I see the full causal chain across services in one view.

**Acceptance Criteria:**

**Given** a `trace_id` shared across records from 3 services
**When** `ulog trace 4bf92f3577b34da6 --db ./shared/logs.sqlite` runs
**Then** records are listed chronologically with service / level / msg / ts columns (FR110).

**Given** `--db <path>` is omitted
**When** invoked
**Then** the default `ulog.default_db_path('prod')` is used.

---

### Story 6.3: Issue-template URL with placeholder URL-encoding + body window

As a viewer user clicking "Open issue" on a record,
I want the URL template's placeholders ({msg}, {level}, {body}, etc.) to be URL-encoded server-side, with `{body}` = JSON of 2 records before + record + 2 records after by chain_pos,
So that the URL is safe to share and the issue tracker gets actionable context.

**Acceptance Criteria:**

**Given** `setup(issue_template_url="https://linear.app/team/new?title={msg}&description={body}")`
**When** the user clicks "Open issue" on a record
**Then** the URL has all placeholders URL-encoded (e.g. `%20` for spaces, `%22` for quotes) — NFR-SEC-51.

**Given** the target record
**When** `{body}` is resolved
**Then** it contains a JSON list of 5 records: 2 before + target + 2 after by `chain_pos` (Gap G3).

**Given** the user clicks the link
**When** the new tab opens
**Then** the issue tracker pre-fills the title/description/labels from the populated URL.

---

### Story 6.4: Multi-track adapter method + `MultiTrackResult` dataclass

As a viewer backend,
I want each adapter (SQLite/JSONL/CSV) to expose `multi_track(filters, tracks, window_start, window_end, bucket_size_s) -> MultiTrackResult`,
So that the multi-track view stays storage-agnostic.

**Acceptance Criteria:**

**Given** `MultiTrackResult(tracks: dict[str, list[BucketCount]], window: tuple[datetime, datetime], bucket_size_s: int)` is defined
**When** an adapter's `multi_track(filters, ['level','service','author','file'], ...)` is called
**Then** a `MultiTrackResult` is returned with one entry per track (Decision D1).

**Given** the SQLite adapter
**When** it computes the bucketing
**Then** it uses `GROUP BY strftime('%Y-%m-%dT%H:%M', ts), <track>` for speed.

**Given** the JSONL/CSV adapters
**When** they compute the bucketing
**Then** they use `collections.Counter` per bucket (in-Python).

**Given** a track with no records in the window
**When** the result is rendered
**Then** the entry is `[]` (UI shows `(no data)` placeholder per PRD-v0.5 §2.1.6).

---

### Story 6.5: Multi-track Django view + template + vanilla JS

As a viewer user,
I want a `/multi-track` page rendering 4 horizontal SVG strips (level/service/author/file) over the shared time axis with mute toggles,
So that I can see traffic patterns across multiple dimensions at a glance.

**Acceptance Criteria:**

**Given** `/multi-track?from=...&to=...` is requested
**When** the view renders
**Then** the page shows 4 SVG strips, one tick per record bucket, mute toggle per track (FR112).

**Given** muting "level"
**When** the page reloads
**Then** records on that track are hidden from the main list below (FR112).

**Given** the page renders on a 100K-record DB
**When** TTI is measured
**Then** ≤ 200ms (NFR-PERF-55, SC7).

**Given** the JS code
**When** linted
**Then** it is < 50 LOC vanilla JS (no d3/plotly/chart.js — NFR-DEP-50, Decision D1).

---

### Story 6.6: Integrity badge UI rendering in `base.html` header

As any viewer user,
I want an integrity badge in the page header showing `Integrity ✓ verified up to #N (last check: T)` or `Integrity ✗ broken at #N`,
So that I always know whether the archive is currently trustworthy.

**Acceptance Criteria:**

**Given** `<db>.verify_state.json` exists with `status: "OK"`
**When** any page renders (extends `base.html`)
**Then** the header shows the green ✓ badge with verified count + relative last-check timestamp (FR113).

**Given** the JSON status is "BROKEN"
**When** any page renders
**Then** the header shows the red ✗ badge with `broken_at: #N`.

**Given** the JSON file is absent
**When** the page renders
**Then** the badge shows "never verified" (graceful degrade).

**Given** the badge has a "Re-verify" link
**When** clicked
**Then** `POST /api/verify-trigger` returns HTTP 202 and the badge gets refreshed on the next page-load.

---

### Story 6.7: Detail "Resolves / Resolved by" cross-links

As a viewer user inspecting an incident-bearing record,
I want the detail panel to show "Resolves: #N" / "Resolved by: #M" cross-links with the resolution note inline,
So that I navigate the incident lifecycle without writing SQL.

**Acceptance Criteria:**

**Given** an ERROR record that has been resolved
**When** the detail page renders
**Then** the panel shows `Resolved by: #M (Johan, 2026-05-04, "connection pool max=20...")` linking to record M (FR114).

**Given** a RESOLVED record (M)
**When** the detail page renders
**Then** the panel shows `Resolves: #N` linking to the original record (FR114).

---

### Story 6.8: Sidebar "Incidents" section quick filters

As a viewer user wanting to triage incidents,
I want a sidebar "Incidents" section with quick filters: Open / Closed (last 7d) / Reopened,
So that I can focus on what needs attention.

**Acceptance Criteria:**

**Given** the sidebar
**When** the page renders
**Then** an "INCIDENTS" section appears with three checkboxes (Open / Closed last 7d / Reopened) (FR115).

**Given** "Open" is ticked
**When** the page reloads
**Then** the records list filters to currently-open incidents.

**Given** the section has a count next to each checkbox
**When** rendered
**Then** the counts honor the v0.2.1 ghost-count contract (count ignores its own filter axis).

---

### Story 6.9: Locale fallback for multi-track CLI glyphs

As a Windows `cmd.exe` or no-locale CI user running `ulog correlate`,
I want UTF-8 glyphs (▲▼⚡⊕⚠) to fall back to ASCII (`>>` `<<` `!` `+` `WARN`),
So that the output is readable without unicode mojibake.

**Acceptance Criteria:**

**Given** `locale.getpreferredencoding() == 'utf-8'`
**When** `ulog correlate` prints its report
**Then** unicode glyphs are used.

**Given** `locale.getpreferredencoding() != 'utf-8'`
**When** the same command runs
**Then** glyphs are replaced by ASCII equivalents per PRD-v0.5 §6.1 (NFR-PORT-50).

---

### Story 6.10: PRD-v0.5 §2.3 edge case — OTel SDK absent

As a user without OTel installed,
I want OTel auto-bind to be a silent no-op,
So that ulog imposes zero requirement on tracing infrastructure.

**Acceptance Criteria:**

**Given** no `_OTEL_TRACE_CONTEXT` contextvar and no `traceparent` env
**When** records are emitted
**Then** they have no `trace_id` or `span_id` fields (PRD-v0.5 §2.3, FR109).

**Given** no warning is printed at setup
**When** the user runs `ulog --help`
**Then** OTel is not mentioned anywhere unless explicitly enabled.

---

## Epic 7: v0.5 release — consolidation, documentation & tag

The v0.5.0 release ships as a coherent, documented, contract-frozen unit. Single `ulog` binary, 7 invariants documented in STABILITY.md, BENCHMARK.md baselines, RELEASE_NOTES.md transition guide, `dependencies = []` regression gate in CI.

### Story 7.1: `_RESERVED` frozenset centralization refactor

As an AI agent adding a new extra-merging code path,
I want a single `from ulog._reserved import RESERVED` import instead of three duplicated frozensets,
So that adding a stdlib reserved attribute (next: when?) is a one-line change.

**Acceptance Criteria:**

**Given** `ulog/_reserved.py` exists
**When** the file is read
**Then** it exports a single `RESERVED: frozenset[str]` containing the canonical set (Decision C4).

**Given** `ulog/formatters.py`, `ulog/handlers/sql.py`, `ulog/handlers/csv_file.py`
**When** the source is read
**Then** each imports `RESERVED` from `ulog._reserved` (no inline frozenset literal).

**Given** the existing v0.2 tests
**When** they run after the refactor
**Then** they all pass (no behavior change).

---

### Story 7.2: `ulog/_cli/__init__.py` argparse subparser dispatcher

As a CLI user running v0.5,
I want a single `ulog` binary that dispatches to subcommands (`web`, `verify`, `repair`, `bisect`, `correlate`, `incidents`, `trace`, `purge`, `replay`),
So that I have one entrypoint for everything.

**Acceptance Criteria:**

**Given** `ulog --help`
**When** invoked
**Then** all subcommands are listed with one-line descriptions (Decision C1).

**Given** `ulog <subcommand> --help`
**When** invoked
**Then** subcommand-specific help is shown.

**Given** the dispatcher
**When** the source is read
**Then** it discovers subcommands via the `cmd_<name>.py` module convention (one `register(subparsers)` + one `run(args)` per module).

**Given** an unknown subcommand
**When** invoked
**Then** argparse prints the help and exits 2.

---

### Story 7.3: Remove `ulog-web` console_script + RELEASE_NOTES.md transition entry

As a v0.4 user upgrading to v0.5,
I want a clear RELEASE_NOTES.md entry explaining the `ulog-web` → `ulog web` rename,
So that I can update my scripts without surprise.

**Acceptance Criteria:**

**Given** `pyproject.toml`
**When** the file is read
**Then** `[project.scripts]` contains only `ulog = "ulog._cli:main"`. The previous `ulog-web` entry is removed (Decision C1, Gap G6).

**Given** `RELEASE_NOTES.md` exists at repo root
**When** read
**Then** it has a prominent v0.5 section titled "Breaking: `ulog-web` is now `ulog web`" with a one-line migration command (Gap G6).

---

### Story 7.4: Doc page `ulog/web/docs/v0.5-forensic-archive.md`

As a new v0.5 user,
I want a doc page covering the 30-second pitch, 7 invariants, 6 worked examples (one per FR cluster), and troubleshooting,
So that I learn v0.5 without reading the PRD.

**Acceptance Criteria:**

**Given** the viewer is running v0.5
**When** the user navigates to `/docs/v0.5-forensic-archive/`
**Then** the page renders with: 30-sec pitch, 7 invariants section, 6 worked examples (one per: storage/integrity, replay, query, incidents, cross-service, UI), troubleshooting section (verify BROKEN, OTel binding silent, retention mismatch) (FR116, NFR-DOC-50).

---

### Story 7.5: Update existing in-app doc pages

As a v0.4 user reading the existing docs,
I want quickstart / storage / api / troubleshooting pages updated to mention the new APIs without breaking v0.4 readers,
So that v0.5 features are discoverable from where I already look.

**Acceptance Criteria:**

**Given** `ulog/web/docs/quickstart.md`
**When** updated
**Then** it adds a "v0.5 quick tour" section pointing to chain mode, replay, incidents, without removing v0.4 content (FR117).

**Given** `storage.md`, `api.md`, `troubleshooting.md`
**When** updated
**Then** each adds the new APIs (chain, replay, incidents) to its relevant section (FR117).

---

### Story 7.6: STABILITY.md — 7 invariants written contract

As a v1.0 user (future),
I want STABILITY.md at the repo root listing the 7 invariants (I1-I7) with rationale and the v0.5+ contract scope,
So that I can rely on ulog's stability guarantees in production.

**Acceptance Criteria:**

**Given** `STABILITY.md` exists at repo root
**When** read
**Then** it lists invariants I1-I7 with full prose (no auto-class / local-first / verify-offline / immutable-hard / stdlib-compat / untagged-works / no-phone-home), each with one-sentence rationale.

**Given** the file
**When** referenced from `pyproject.toml` description or README
**Then** the link is correct.

---

### Story 7.7: BENCHMARK.md — SC1/SC2/SC7 baseline numbers

As a release manager,
I want BENCHMARK.md at the repo root with the measured baselines for SC1 (verify ≤5s/100K), SC2 (correlate ≤500ms), SC7 (multi-track ≤200ms),
So that future regressions are detectable against documented numbers.

**Acceptance Criteria:**

**Given** `BENCHMARK.md` exists
**When** read
**Then** it has 3 numbered sections (SC1/SC2/SC7), each with the median of 5 runs measured on GitHub Actions ubuntu-latest CPython 3.12.

**Given** a future PR that regresses one of these by >20%
**When** the benchmark CI step runs
**Then** the regression is visible in the BENCHMARK.md diff (advisory mode for first 2 runs per Decision E3).

---

### Story 7.8: `tests/test_qlnes_compat.py` — I5/SC5 byte-stable regression test

As a release manager protecting invariant I5 (stdlib `logging` compat forever),
I want a byte-stable test that calls `logging.getLogger(__name__).info("hello")` and asserts the formatter output is exactly the v0.1 byte sequence,
So that any future change breaking I5 is caught immediately by CI.

**Acceptance Criteria:**

**Given** the test
**When** invoked
**Then** it calls `logging.getLogger("test").info("hello")` after `ulog.setup(format='qlnes')` and asserts the captured stream output is exactly the byte string defined as the v0.1 baseline (SC5, I5 gate).

**Given** any v0.5 change
**When** the test runs in CI
**Then** it passes.

---

### Story 7.9: CI gate — `dependencies = []` grep step

As a release engineer,
I want a CI step that fails the build if `pyproject.toml` ever lists a runtime dep,
So that NFR-DEP-50 / SC4 is mechanically enforced.

**Acceptance Criteria:**

**Given** `.github/workflows/ci.yml`
**When** read
**Then** it contains a step `regression-gate-zero-deps` running `grep '^dependencies' pyproject.toml | grep -q '\[\]'` (Decision E2).

**Given** a PR adds `dependencies = ["requests"]` to `pyproject.toml`
**When** CI runs
**Then** the step fails the build.

---

### Story 7.10: pytest-benchmark in `[dev]` extras + advisory CI

As a maintainer,
I want `pytest-benchmark` declared in `[dev]` extras and the benchmark CI step in advisory mode for the first 2 runs,
So that perf regressions are visible without prematurely failing the build before baselines stabilize.

**Acceptance Criteria:**

**Given** `pyproject.toml`
**When** read
**Then** `[project.optional-dependencies]` `dev` includes `pytest-benchmark` (Decision E3).

**Given** the CI workflow
**When** read
**Then** the benchmark step runs but does NOT fail the build during the first 2 v0.5 CI runs (advisory).

**Given** the third v0.5 CI run
**When** baselines are stable
**Then** a follow-up PR enables strict mode (gate hardens).

---

### Story 7.11: `tests/coverage_matrix.md` — FR/edge-case → test mapping

As a release manager wanting to certify SC3,
I want a coverage matrix listing each FR/edge case from the PRDs with its test name(s),
So that I can certify ≥1 passing test per requirement at release time.

**Acceptance Criteria:**

**Given** `tests/coverage_matrix.md` exists
**When** read
**Then** it has a markdown table mapping every FR (FR51-FR117) and every PRD §2.3 edge case (4 in v0.4 + 8 in v0.5) to ≥1 test name (SC3 secondary indicator).

**Given** the matrix
**When** verified against the test suite
**Then** every named test exists and passes.

---

### Story 7.12: Tag v0.5.0 + push + qlnes migration

As Johan releasing v0.5,
I want to tag `v0.5.0`, push, and migrate qlnes to ulog ≥ 0.5.0 within 30 days,
So that SC6a is satisfied and the first reference adopter validates the release.

**Acceptance Criteria:**

**Given** all prior stories of all 7 epics are merged
**When** `git tag v0.5.0 && git push origin v0.5.0` runs
**Then** the tag exists and the GitHub release is published.

**Given** the qlnes repo
**When** within 30 days of the tag
**Then** its `pyproject.toml` is updated to pin ulog ≥ 0.5.0 (SC6a — mechanically checkable).

**Given** OUTREACH.md exists
**When** populated
**Then** ≥1 additional public adopter is identified (SC6b — best-effort, not release-blocking).

---

## Final Validation Results

### 1. FR Coverage Validation ✅

All 61 FRs (FR51 → FR117) are mapped to stories with testable acceptance criteria:

| Epic | FR range | Count | Stories |
|---|---|---|---|
| Epic 1 (v0.3) | FR51-FR69 | 19/19 | Stories 1.1-1.11 |
| Epic 2 (v0.4) | FR70-FR83 | 14/14 | Stories 2.1-2.11 |
| Epic 3 (v0.5 storage) | FR90-FR97 | 8/8 | Stories 3.1-3.12 |
| Epic 4 (queryability) | FR98-FR104 | 7/7 | Stories 4.1-4.10 |
| Epic 5 (incidents) | FR105-FR108 | 4/4 | Stories 5.1-5.6 |
| Epic 6 (cross-service & UI) | FR109-FR115 | 7/7 | Stories 6.1-6.10 |
| Epic 7 (release) | FR116-FR117 | 2/2 | Stories 7.1-7.12 |
| **Total** | | **61/61** | **71 stories** |

### 2. NFR Coverage Validation ✅

| NFR | Coverage |
|---|---|
| NFR-PERF-20 (plugin overhead < 5ms) | Verified by benchmark step inside Story 1.2's pytest_plugin tests + Epic 7 BENCHMARK.md (Story 7.7) |
| NFR-PERF-30 / 31 (indexer + page-load) | Stories 2.3, 2.4 |
| NFR-PERF-50 / 51 (setup + per-log) | Verified via `tests/bench_log.py` ─ created in Story 7.10 |
| NFR-PERF-52 / SC1 | Story 3.7 |
| NFR-PERF-53 / SC2 | Story 4.5 (after renumber 4.6) |
| NFR-PERF-54 | Story 4.7 (after renumber 4.8) |
| NFR-PERF-55 / SC7 | Story 6.5 |
| NFR-DEP-50 / SC4 | Story 7.9 |
| NFR-COMPAT-* / I5/SC5 | Story 7.8 |
| NFR-PORT-* | Stories 1.10, 6.9 + CI matrix |
| NFR-REL-50 | Story 3.11 |
| NFR-REL-51 / 52 | Stories 4.10, 3.8 |
| NFR-SEC-30 | Story 2.9 |
| NFR-SEC-50 | Story 4.4 (after renumber 4.5) |
| NFR-SEC-51 | Story 6.3 |
| NFR-DOC-10 / 30 / 50 | Stories 1.11, 2.11, 7.4 |

### 3. Architecture Compliance ✅

- **No starter template** required — brownfield project. Epic 1 Story 1.1 is correctly "Plugin entry-point registration" (the lowest-blast-radius starting point), not "Set up initial project from starter template" (which would be wrong for brownfield).
- **Database/entity creation lazy** — Story 3.1 creates v0.5 schema extensions ONLY (immutable + chain_pos + record_hash + prev_hash columns + their indexes); Story 2.4 creates the `authors` cache table ONLY. No "create all 50 tables upfront" anti-pattern.
- **Locked-out libraries respected** — every story explicitly references stdlib alternatives where temptation exists (Story 2.1 forbids GitPython; Story 2.9 forbids shell-injection; Story 4.4 forbids `eval()`; Story 6.1 forbids opentelemetry-sdk import; Story 6.5 forbids d3/plotly).

### 4. Story Quality ✅

- Every story uses Given/When/Then acceptance criteria.
- Every story references the FRs / NFRs / decisions / gaps it implements.
- No story exceeds single-dev-session scope (each is ~1 PR).
- Edge cases get dedicated stories (Story 2.10, 3.12, 4.10, 5.6, 6.10) ensuring SC3 coverage matrix populated by Story 7.11.

### 5. Epic Structure ✅

- All 7 epics deliver discrete user value (test integration / author attribution / chain integrity / queryability / incident lifecycle / cross-service+UI / release).
- No epic is a technical layer (no "Database Setup", no "API Development").
- File churn check: Epics 3-6 share `ulog/handlers/sql.py` (read access) but each introduces **distinct new files** (`_chain.py`, `replay.py`, `correlate.py`, `bisect.py`, `incidents.py`, `_otel.py`). Templates `list.html` / `detail.html` are extended by multiple epics in **different sections** (Tests sidebar in Epic 1, Authors sidebar in Epic 2, Incidents sidebar + multi-track strip in Epic 6) — incidental sharing, not same-component-end-to-end churn. Justified split.

### 6. Epic Dependency Validation ✅

| Epic | Depends on | Standalone after deps? |
|---|---|---|
| Epic 1 (v0.3) | v0.2 substrate only | ✅ |
| Epic 2 (v0.4) | v0.2 substrate only | ✅ |
| Epic 3 (v0.5 storage) | v0.2 + v0.4 substrate | ✅ |
| Epic 4 (queryability) | Epic 3 (chain) | ✅ |
| Epic 5 (incidents) | Epic 3 (chain) | ✅ |
| Epic 6 (cross-service & UI) | Epic 3 (chain) + Epic 5 (incident data) | ✅ |
| Epic 7 (release) | All prior | ✅ (consolidation epic by design) |

No circular dependencies. No epic depends on a LATER epic. Each is independently valuable after its predecessors land.

### 7. Within-Epic Story Dependency Validation — 1 anomaly to correct ⚠️

All within-epic story sequences pass the "no forward dependency" rule **except one in Epic 4**:

**Anomaly:** Story 4.3 (`replay_to_pytest()` generator) generates a test file that imports `from ulog.testing import replay_records`. The `replay_records` context manager itself is defined in Story 4.9. Story 4.3's acceptance criteria assume `replay_records` exists — that's a forward dependency.

**Resolution (apply during sprint planning):** swap the implementation order of Stories 4.3 and 4.9. Concretely, treat the implementation sequence within Epic 4 as:

```
4.1 replay() core
4.2 _REPLAY_ACTIVE contextvar
4.9 replay_records context manager   ← move BEFORE 4.3
4.3 replay_to_pytest() generator     ← uses 4.9
4.4 Filter DSL parser
4.5 correlate() core
4.6 correlate() warnings + axis-skip
4.7 bisect() binary search
4.8 ulog correlate / bisect / replay CLI subcommands
4.10 edge case — replay write attempt
```

Story numbering in this document is preserved as-is for traceability; sprint planning consumes this implementation-order list rather than the lexical numbering. Sprint planning skill (`bmad-sprint-planning`) will re-sequence accordingly.

### 8. Coverage of Architectural Decisions / Patterns / Gaps ✅

All 9 critical decisions (A1-E2) and 12 patterns (B2-E3 from architecture.md step-05) have implementing stories. All 8 Important Gaps (G1-G8) have dedicated coverage:

| Gap | Story | Resolution |
|---|---|---|
| G1 (pre-chain records on upgrade) | Story 3.3 | Backfilled rows have NULL hashes; first new chain record uses `b"\x00"*32` |
| G2 (`_REPLAY_ACTIVE`) | Story 4.2 | New contextvar in `ulog/replay.py` |
| G3 (issue body window) | Story 6.3 | Symmetric 2-before + 2-after by chain_pos |
| G4 (OTel scope) | Story 6.1 + 6.10 | OTel SDK only; documented limitation |
| G5 (`replay_records` signature) | Story 1.9 + Story 4.9 | Stable API exported from `ulog.testing` |
| G6 (`ulog-web` removal) | Story 7.3 | RELEASE_NOTES.md prominent entry |
| G7 (DSL precedence) | Story 4.4 | AND > OR; parentheses supported |
| G8 (purge on pre-chain rows) | Story 3.9 | Pre-chain rows treated as rotable by default |

### Overall Status

**READY FOR DEVELOPMENT** with one pre-implementation reorder noted above (Epic 4 Stories 4.3 ↔ 4.9 swap during sprint sequencing).

- **Confidence:** high. All 61 FRs traced to stories. All NFRs have a verification path (story or benchmark CI). All 7 invariants (I1-I7) have either a regression test (Story 7.8) or a structural enforcement (Story 7.9 grep gate, Story 3.2 SQL trigger, etc.). All 8 architectural gaps have dedicated stories.
- **Total story count:** 71 stories across 7 epics.
- **Implementation entry point:** Story 1.1 (Pytest plugin entry-point registration) — lowest blast radius, validates the `ulog/testing/` sub-package convention used downstream by Epic 4.

---

## Implementation Handoff

This document is the source of truth for v0.3 → v0.5 development. Pair it with:

- **`_bmad-output/planning-artifacts/architecture.md`** — the HOW (decisions, patterns, structure).
- **`docs/prds/PRD-v0.3-test-integration.md`**, **`PRD-v0.4-commit-author-filter.md`**, **`PRD-v0.5-forensic-archive.md`** — the WHAT (canonical FRs/NFRs).

**Recommended next workflows:**

1. `/bmad-sprint-planning` — sequences these 71 stories into sprint slots, applying the Epic 4 reorder noted above.
2. `/bmad-create-story` (per story) — produces the dedicated context-rich story spec file each AI dev agent will execute against.
3. `/bmad-dev-story <story-id>` — execute a single story.
