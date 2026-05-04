---
docType: prd
project_name: ulog-python
version: 0.5.0
date: 2026-05-04
author: jojo8356
status: draft v1
parent_prd: PRD-v0.4-commit-author-filter.md
input_session: ../../_bmad-output/brainstorming/brainstorming-session-2026-05-04-2051.md
---

# ULog v0.5 — Forensic Archive

> v0.4 enriches log records with their git author. v0.5 transforms
> ulog from a logger into a **forensic black box**: every error is
> part of an **immutable hash-chained ledger**, queryable by
> `correlate` (lift on tags), `bisect` (first occurrence), and
> `incidents` (open / closed state). The archive becomes
> self-describing — and self-verifying.

---

## 0. The 30-second pitch

After v0.4, ulog can answer "**who** wrote this code". v0.5 answers
two deeper questions: "**what** really happened" (immutable
replayable archive) and "**what did we do about it**" (incidents
ledger). The log archive stops being a graveyard and starts being a
forensic registry that learns over time.

The driver — Johan's own brainstorming statement: *"comprendre les
erreurs de mon histoire et ne pas avoir les mêmes problèmes"* —
maps directly to immutability + integrity + queryability +
resolution tracking, which is exactly what v0.5 ships.

The v1.0 freeze contract crystallizes here: **scribe local-first
ergonomic stdlib-compatible**. The 7 protected invariants in §2.4
are non-negotiable through v1.0 and forever.

---

## 1. Vision

### 1.1 Why this exists

After three minor releases, the ulog archive has grown from "log
dump" to "queryable history with author attribution". But it remains
a **passive collection** — you can read it, but you can't trust it
hasn't been silently tampered, you can't tell what's still bleeding
versus what's been resolved, and you can't quickly correlate a recent
spike to its underlying cause across multiple dimensions.

Three concrete pain points the v0.4 archive can't address:

1. **"Did I really fix that crash from 6 weeks ago?"** — the archive
   says it happened, says nothing about what was done.
2. **"This morning's spike — what's it about?"** — manual
   filter-clic-back-filter takes 5–30 minutes per axis. At 100K +
   records the cost grows linearly.
3. **"Has anything in this archive been silently rewritten?"** — no
   way to verify integrity. The DB is "trust the SGBD".

v0.5 closes all three.

### 1.2 What v0.5 isn't

- **Not an analyst.** ulog never auto-classifies records. Tagging
  is the app's act, never ulog's. (Invariant I1.)
- **Not a SaaS.** `ulog verify` runs 100 % offline. No account, no
  payment, no network. (I2/I3.)
- **Not a SecOps tool.** Security categorization is the app's job
  via `extra={"security": True, "attack": "..."}`. ulog provides
  the immutable-storage mechanism, not the heuristic.
- **Not a SIEM.** No alerting, no escalation policy. ulog records;
  external tools (PagerDuty, Sentry, OpsGenie) alert.
- **Not a successor break.** `logging.getLogger(__name__)` keeps
  working unchanged. v0.5 layers ON TOP. (I5.)

### 1.3 Target users (carried + new)

| Persona | Role | v0.5 use case |
|---|---|---|
| **Marco** (carried) | Solo dev / CLI consumer | Black-box archive of his app's history; `bisect` to find first error occurrence; one-click "open issue" when a log surprises him. |
| **Lin** (carried) | Pipeline integrator (CI) | Immutable archive for CI artefact retention; replay-to-pytest to convert prod incidents into regression tests. |
| **Sara** (carried) | Library developer | Hash-chain integrity gives confidence that her library's logs in a host app weren't tampered after she left the team. |
| **Johan** (carried) | Tech lead 5-person team | `correlate` on team-wide spike; `incidents` ledger for monthly postmortems without JIRA. |
| **Erika** (NEW) | Compliance officer in 50-dev shop | `min_retention_days` enforcement + `ulog verify` to satisfy SOC 2 Type II / GDPR Art. 30 audits without buying a SIEM. |
| **Diego** (NEW) | Micro-services platform engineer | OTel `trace_id` auto-bind for cross-service incident replay; one chain spanning 12 services. |

### 1.4 Success criteria

| SC | Description | Measurement |
|---|---|---|
| **SC1** | `ulog verify` reports an integrity status in **≤ 5 s on a 100 K-record DB** | `pytest-benchmark` median 5 runs, GitHub Actions `ubuntu-latest`, CPython 3.12, SQLite WAL mode |
| **SC2** | `ulog correlate <filter>` returns top-10 lifted dimensions in **≤ 500 ms** on a 10 K-filter / 1 M-baseline DB | Same harness as SC1, fixture in `tests/bench_correlate.py` |
| **SC3** | Incidents ledger : in **≥ 30 unit tests**, every `ulog.resolve()` correctly links the resolution to its parent error within the chain | Foreign-key validation + chain-walk verification |
| **SC4** | **Zero PyPI runtime dep added.** `pyproject.toml`'s `dependencies = []` stays unchanged. ucolor still vendored. | Regression gate in CI (`grep '^dependencies' pyproject.toml \| grep -q '\[\]'`) |
| **SC5** | **Stdlib `logging.getLogger(__name__).info(...)` continues to work unchanged.** | Existing v0.1 byte-stable test (`tests/test_qlnes_compat.py`) stays green |
| **SC6a** | **qlnes is migrated to ulog v0.5 within 30 days of tag** (existing v0.1 dependency upgraded). | Tag exists in `jojo8356/qlnes` repo with `pyproject.toml` pinned to ulog ≥ 0.5.0. Mechanically checkable. |
| **SC6b** | (best-effort) **At least 1 additional public adopter** identified within 30 days. | Manual check of GitHub `dependents` graph + reach-out tracking in `OUTREACH.md`. Best-effort — not a release-blocking gate. |
| **SC7** | Multi-track UI minimal renders **4 axes × 4 h window** in **≤ 200 ms** on 100 K records | Playwright TTI metric, fixture run on GitHub Actions |

---

## 2. Scope (v0.5)

### 2.1 In scope (12 features, ~ 1 280 LOC of ulog implementation)

#### 2.1.1 Storage architecture

Two-tier storage in a single SQLite DB :

- **`logs_immutable`** — records where `immutable_when(record)` returned
  `True`. SQL trigger blocks `UPDATE`/`DELETE` from any client. Default
  predicate : `lambda r: r.levelno >= ERROR`.
- **`logs_rotable`** — everything else. Subject to `min_retention_days`
  floor and standard rotation.

A shared `id` sequence + a unified `chain_pos` column lets the hash chain
walk both tables in order.

#### 2.1.2 Hash chain + `ulog verify`

At each write, ulog computes :
```
record_hash = sha256(canonical_json(record) + prev_record_hash)
```
where `canonical_json` = `json.dumps(record, sort_keys=True, separators=(',',':'))` (stdlib).

A per-DB write lock (`BEGIN IMMEDIATE` on SQLite) serializes the chain.
`ulog verify` walks the chain offline, reports `OK` / `BROKEN at #N`.
The UI shows an **Integrity ✓** badge on every page.

#### 2.1.3 Replay (regression test driver)

```python
ulog.replay(filter=..., on=callback)
```
re-injects records into a callback. The **primary use case** :
```python
ulog.replay_to_pytest(filter="resolves='3f7c12...'", output_path="tests/test_incident_3f7c12.py")
```
generates a pytest fixture that replays the records around an incident
and asserts the new code path resolves the bug. Auxiliary uses (UI
scrub, fuzz) postponed to v0.6.

#### 2.1.4 Query — `correlate` + `bisect`

- **`ulog correlate <filter>`** — for every (tag, value) in the records,
  computes the **lift** = `P(tag=v | filter) / P(tag=v | not filter)`.
  Sorts by lift, returns top 10 over and bottom 5 under. Single
  `GROUP BY tag, value` SQL with `COUNT(*) FILTER (...)`. Sample-size
  guard at `in_filter < 30`.
- **`ulog bisect <pattern>`** — binary search over the chain (which
  provides total ordering) to find the **first** record matching
  `pattern` (regex on msg + tags). Returns matched record + v0.4 commit
  context.

#### 2.1.5 Incidents ledger

```python
ulog.resolve(incident_hash, by, note)   # emits an immutable INFO record
ulog.reopen(incident_hash, reason)      # ditto
```
Resolution records reference the original by hash via a typed `resolves`
field. UI separates open vs closed errors. CLI :
```
ulog incidents --status open
ulog incidents --report --since 1m
```
Postmortem KPIs (opened / closed / net debt / mean time to resolve / P95
/ reopens) are computed from the chain itself — no external tracker
needed.

#### 2.1.6 Multi-track UI minimal

4 fixed tracks in the browse view : `level`, `service`, `author`, `file`.
Each track is a horizontal SVG strip (one tick per record) over the
shared time axis. Mute toggle hides records on that track from the main
list.

#### 2.1.7 Retention floor

```python
ulog.setup(min_retention_days=730)   # SOC 2 / GDPR Art. 30 hook
```
`ulog purge --before <date>` refuses operations that would drop records
younger than `today − N days`. Default N = 0 (off, opt-in).

#### 2.1.8 OTel cross-service binding

If contextvar `_OTEL_TRACE_CONTEXT` (or env `traceparent`) is present at
log time, ulog auto-attaches `trace_id` and `span_id`. Zero new dep —
ulog only reads stdlib contextvars. CLI : `ulog trace <id>` lists all
records sharing a trace_id chronologically across services.

#### 2.1.9 Issue button

```python
ulog.setup(
    issue_template_url="https://linear.app/team/new?title={msg}&assignee={author_handle}&body={body}",
)
```
UI button on the record detail panel populates the URL with placeholders
`{msg}` `{level}` `{service}` `{author}` `{author_handle}`
`{commit_sha}` `{record_hash}` `{labels}` `{body}` (latter = JSON dump
of record + 5 surrounding records). Tracker-agnostic.

#### 2.1.10 Documentation

New doc page `/docs/v0.5-forensic-archive.md` (in `ulog/web/docs/`) :
30-second pitch · the 7 invariants · the 6 worked examples (one per FR
cluster).

### 2.2 Explicit non-goals (deferred to v0.6+)

- **Jupyter notebook export** (`ulog notebook <filter>`) — wrapper on
  top of replay ; ships clean once `ulog.replay()` is mature.
- **Multi-track UI full** — configurable tracks, solo mode, scrubber
  overlay, canvas rendering for 1 M+ records.
- **Record lineage / chain-of-custody** — per-record `verified_at[]` /
  `replayed_at[]` / `exported_at[]` metadata.
- **TSA / RFC 3161 signing** — out of scope (violates zero-PyPI-dep).
  A user who needs it writes a `TSAHandler` outside ulog.
- **Auto-classification heuristics** (DDoS detection, brute-force
  pattern matching) — explicitly rejected (violates I1).

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| **Concurrent writers across processes** (multiprocess pytest, gunicorn workers) | Per-DB write lock at the SQL layer (`BEGIN IMMEDIATE`). Verified by `tests/test_chain_concurrency.py` (8 writers × 10 K records each). |
| **Chain corruption detected by `ulog verify`** | Hard fail — further writes blocked until the user runs `ulog repair`. Repair truncates the chain at the last valid record, archives orphaned content into `chain_break_<ts>.log` for forensics. I4 preserved : nothing silently dropped. |
| **`immutable_when(record)` raises** | Record is treated as immutable (fail-safe). Exception is logged via stderr (not via ulog itself, to avoid recursion). |
| **OTel SDK absent** | `trace_id` auto-bind is silently a no-op. No warning at setup. |
| **`ulog.resolve(hash)` references a record not in the DB** | `LookupError` raised at call time. Resolution record is NOT emitted. |
| **`ulog.resolve(hash)` references an already-resolved record** | Allowed — emits another resolution record. The chain shows a sequence of resolutions ; the UI shows the latest as the active state. Useful for "I thought I fixed it but didn't". |
| **`ulog purge` would violate `min_retention_days`** | Refuses with a non-zero exit code and a summary of how many records would have been dropped. |
| **`record_hash` collision** | Theoretical (sha256 collision = 2^128 work). If it ever happens, `ulog verify` reports it as `BROKEN`. We treat the chain as broken at the collision point. |

### 2.4 Protected invariants — v1.0 freeze contract

These 7 invariants are **non-negotiable through v1.0 and forever**.
Any future feature proposal that violates one is rejected by
construction.

| ID | Invariant |
|---|---|
| **I1** | Ulog never auto-classifies records. Tagging is the app's act, never ulog's. |
| **I2** | Ulog never opens a network socket without explicit user opt-in. Local-first by default. |
| **I3** | `ulog verify` runs offline against the local DB. No SaaS, no account, no auth, no payment. |
| **I4** | Records flagged immutable cannot be deleted, ever, by any path (API, SDK, CLI, admin). The predicate is hard. |
| **I5** | `logging.getLogger(__name__).info(...)` continues to work in all ulog versions, forever. No major-version break of this contract. |
| **I6** | Untagged log calls (`log.error("oops")`) work. Tagging is opt-in. The barrier to entry stays = stdlib. |
| **I7** | Ulog never phones home. No telemetry, no usage stats, no analytics. Ulog observes the app, never the user. |

Meta-principle : **ulog is a tool the user fully controls. It never
crosses the boundary "scribe local-first ergonomic stdlib-compatible".**

---

## 3. Functional Requirements

### 3.1 Storage & immutability

| FR | Description | Persona |
|---|---|---|
| **FR90** | `ulog.setup(immutable_when=callable)` accepts a predicate `(record) → bool`. `True` → record persisted in `logs_immutable` (SQL trigger blocks UPDATE/DELETE). `False` → `logs_rotable`. Default : `lambda r: r.levelno >= logging.ERROR`. | Marco, Erika |
| **FR91** | Both tables share a single monotonic `chain_pos` sequence so the hash chain (FR93) walks rows in append order regardless of which table they land in. | Sara |
| **FR92** | `ulog.setup(min_retention_days=N)` enforces a floor on rotable records — any rotation / purge operation refuses to drop records younger than `today − N days`. Default N = 0 (off). | Erika |
| **FR93** | `ulog.purge(before=<date>)` is the only sanctioned cleanup path for rotable records. It validates against `min_retention_days` and against `immutable_when`. Returns the count of records actually purged. | Erika |

### 3.2 Hash chain & verification

| FR | Description | Persona |
|---|---|---|
| **FR94** | At write, ulog computes `record_hash = sha256(canonical_json(record) + prev_record_hash)`. Both fields persisted on the row. The first record's `prev_hash` is `b"\x00" * 32`. Per-DB write lock (`BEGIN IMMEDIATE` on SQLite) serializes the chain. PostgreSQL backend is deferred to v0.7 (see §7 + §8.4). | Sara, Erika |
| **FR95** | `ulog verify [--range A-B]` walks the chain (or sub-range) and reports `OK` / `BROKEN at #N (expected hash X, got Y)`. Exit code 0 / 1. Runs offline. | Erika |
| **FR96** | UI integrity badge in the sidebar of every page : `Integrity ✓ verified up to #487,234 (last check: 2 min ago)` or `Integrity ✗ broken at #142,071`. Auto-refreshes on demand. | Sara, Marco |
| **FR97** | `ulog repair` truncates the chain at the last valid record and archives the orphaned content into `<db>.chain_break_<ts>.log`. Used only after `ulog verify` reports BROKEN. Refuses to run without `--confirm`. | Erika |

### 3.3 Replay

| FR | Description | Persona |
|---|---|---|
| **FR98** | `ulog.replay(filter=..., on=callback)` iterates records matching `filter` in chain order and calls `callback(record)` for each. The callback receives a frozen-dict view (read-only). | Marco, Lin |
| **FR99** | A `replay` invocation runs in a context where `ulog.is_replaying()` returns True ; new `log.error()` calls inside the callback are flagged with `is_replay=True` to prevent infinite loops at the next replay. | Lin |
| **FR100** | **Primary driver** : `ulog.replay_to_pytest(filter, output_path)` generates a `tests/test_incident_<hash>.py` fixture replaying the records and asserting the new code path resolves the incident. The generated test imports `pytest` and `ulog.testing`. | Lin, Marco |

### 3.4 Query & analysis

| FR | Description | Persona |
|---|---|---|
| **FR101** | `ulog correlate <filter>` computes `lift = P(tag=v | filter) / P(tag=v | not filter)` for every (tag, value) pair in the records. Returns top 10 over and bottom 5 under, sorted by lift. SQL : single `GROUP BY tag, value` with `COUNT(*) FILTER (...)`. Index on `(tag_name, tag_value)`. | Johan |
| **FR102** | `correlate` flags warnings inline when `in_filter < 30` (small-sample bias) and when the filter axis itself is included in the dimensions explored (lift forced to 0 or ∞). | Johan |
| **FR103** | `ulog bisect <pattern>` runs binary search over the chain to find the **first** record matching `pattern` (regex on `msg`, `extras`, and `tags`). Returns the matched record + v0.4 commit context (author + sha + diff link). | Marco |
| **FR104** | Both `correlate` and `bisect` are exposed as CLI subcommands AND as a Python API (`ulog.correlate(filter, db_path) → CorrelationReport`, `ulog.bisect(pattern, db_path) → Record`). | Johan, Marco |

### 3.5 Incidents ledger

| FR | Description | Persona |
|---|---|---|
| **FR105** | `ulog.resolve(incident_hash, by, note)` emits a new immutable record with `level=INFO`, `msg="RESOLVED"`, `resolves=<hash>`, `by=<user>`, `note=<str>`, `commit_sha=<HEAD>`. Foreign-key validated against the original record. | Johan |
| **FR106** | `ulog.reopen(incident_hash, reason)` emits a `msg="REOPENED"` record referencing the original. Incident state is computed by walking the chain (latest wins). | Johan |
| **FR107** | `ulog incidents --status {open,closed,all}` lists records with their resolution state. CLI exit code = number of open incidents (useful as a CI gate). | Erika |
| **FR108** | `ulog incidents --report --since <period>` outputs aggregated KPIs : opened / closed / net debt / mean time to resolve / P95 / reopens / top closers. Markdown output, pipeable to a postmortem doc. | Johan, Erika |

### 3.6 Cross-service & integrations

| FR | Description | Persona |
|---|---|---|
| **FR109** | If a contextvar `_OTEL_TRACE_CONTEXT` (or env `traceparent`) is set at log time, ulog auto-attaches `trace_id` and `span_id` to the record. No-op if absent. Zero new dep. | Diego |
| **FR110** | `ulog trace <id>` lists all records sharing a `trace_id` in chronological order, across services (assumes a shared DB or `--db <path>` flag for cross-service correlation). | Diego |
| **FR111** | `ulog.setup(issue_template_url="...")` accepts a URL with placeholders `{msg}` `{level}` `{service}` `{author}` `{author_handle}` `{commit_sha}` `{record_hash}` `{labels}` `{body}`. UI "Open issue" button populates and opens the URL in a new tab. Tracker-agnostic (Linear / GitHub / GitLab / Jira). | Johan, Marco |

### 3.7 UI

| FR | Description | Persona |
|---|---|---|
| **FR112** | Multi-track view : 4 fixed tracks (`level` / `service` / `author` / `file`). Each track is a horizontal SVG strip with one tick per record over the shared time axis. Mute toggle hides records on that track from the main list. | Johan, Marco |
| **FR113** | Integrity badge (FR96) is visible on every UI page header. | Sara, Erika |
| **FR114** | Detail panel for a record displays "Resolves : #N" / "Resolved by : #M" cross-links if applicable (FR105/FR106), with the resolution note inline. | Johan |
| **FR115** | Sidebar adds a new section "Incidents" with quick filters : `[ ] Open` / `[ ] Closed (last 7d)` / `[ ] Reopened`. | Johan, Erika |

### 3.8 Documentation

| FR | Description | Persona |
|---|---|---|
| **FR116** | New doc page `ulog/web/docs/v0.5-forensic-archive.md` covers : 30-second pitch · 7 protected invariants · 6 worked examples (one per FR cluster) · troubleshooting (`ulog verify` BROKEN, OTel binding silent, `min_retention_days` mismatched). | All |
| **FR117** | Existing doc pages (quickstart, storage, api, troubleshooting, sectors-and-files) updated to mention the new APIs without breaking v0.4 readers. | All |

---

## 4. Non-Functional Requirements

| NFR | Budget + measurement |
|---|---|
| **NFR-PERF-50** | `setup()` overhead remains ≤ 1 ms (one-time cost). `pytest-benchmark` median 5 runs, CPython 3.12, GitHub Actions `ubuntu-latest`. |
| **NFR-PERF-51** | Per-log-call overhead ≤ 1.3× v0.4 baseline (chain hash adds ~5 µs). `tests/bench_log.py`, results in `BENCHMARK.md`. |
| **NFR-PERF-52** | `ulog verify` walks 100 K records in **≤ 5 s**, single-thread, SQLite WAL mode, NVMe SSD, GitHub Actions runner. CI-gated. (= SC1.) |
| **NFR-PERF-53** | `ulog correlate` returns top-10 in **≤ 500 ms** on 10 K-filter / 1 M-baseline DB. (= SC2.) |
| **NFR-PERF-54** | `ulog bisect` over 1 M-record chain finds first match in ≤ 100 ms (≈ 20 binary probes × 5 ms each). |
| **NFR-PERF-55** | Multi-track UI renders 4 axes × 4 h on 100 K records in ≤ 200 ms TTI. (= SC7.) |
| **NFR-DEP-50** | `pyproject.toml` `dependencies = []` stays unchanged. ucolor stays vendored. (= SC4 regression gate.) |
| **NFR-COMPAT-50** | Python 3.10+ ; `mypy --strict` green ; stdlib `logging` compat preserved (= SC5 / I5 gate). |
| **NFR-PORT-50** | Linux + macOS + Windows. Hash chain works on all three (sha256 stdlib). |
| **NFR-REL-50** | Chain integrity preserved across multiprocess writers — verified by `tests/test_chain_concurrency.py` (8 writers × 10 K records each, no broken chain at the end). |
| **NFR-REL-51** | Replay is read-only on the chain. Any record emitted during replay is flagged `is_replay=True`. |
| **NFR-REL-52** | `ulog repair` is idempotent : running it twice on a healthy chain is a no-op. Running on a broken chain produces the same truncation point. |
| **NFR-DOC-50** | Doc page `v0.5-forensic-archive.md` ships with 6 worked examples covering each FR cluster. (= FR116.) |
| **NFR-SEC-50** | All CLI inputs (`bisect`, `verify --range`, `incidents`, `trace`) are validated against shell-injection. `record_hash` arguments must match `[0-9a-f]{4,64}`. `pattern` for bisect is compiled as Python regex (no shell expansion). |
| **NFR-SEC-51** | The issue-template URL placeholders are URL-encoded server-side ; the user template is not eval'd. |

---

## 5. API surface (sketch)

### 5.1 Setup with v0.5 options

```python
import ulog
import logging

ulog.setup(
    profile='prod',
    immutable_when=lambda r: (
        r.levelno >= logging.ERROR
        or r.attrs.get('security') is True
    ),
    integrity='hash-chain',           # or 'constraint-only' / 'none'
    min_retention_days=730,           # SOC 2 hook
    issue_template_url=(
        "https://linear.app/team/new"
        "?title={msg}"
        "&assignee={author_handle}"
        "&description={body}"
    ),
)
```

### 5.2 Logging is unchanged (I5 / I6)

```python
log = ulog.get_logger(__name__)

# Untagged still works
log.error("db.timeout")

# Tagged opens correlate / incidents / replay value
log.error(
    "db.timeout",
    extra={
        "service": "payment",
        "db_timeout": True,
        "http_status": 503,
    },
)
```

### 5.3 Resolving an incident

```python
ulog.resolve(
    incident_hash="3f7c12a09b8d...",
    by="Johan",
    note=(
        "connection pool max=20 in services/db.py:47, "
        "deployed b7866ee on 2026-05-04T18:30Z"
    ),
)
```

### 5.4 Replay → regression test

```python
# Generate a pytest fixture from a real prod incident
ulog.replay_to_pytest(
    filter="resolves='3f7c12a...'",
    output_path="tests/test_incident_3f7c12a.py",
)

# Or programmatic replay
def assert_no_timeout(record):
    assert "db_timeout" not in record["extras"]

ulog.replay(filter="trace_id='4bf92f...'", on=assert_no_timeout)
```

### 5.5 CLI

```bash
$ ulog verify                                      # offline integrity check
$ ulog verify --range 100000-100500                # partial range
$ ulog bisect "db.timeout"                         # first occurrence
$ ulog correlate 'level=ERROR AND date>-24h'       # lift on tags
$ ulog incidents --status open                     # open register
$ ulog incidents --report --since 1m               # KPIs to markdown
$ ulog trace 4bf92f3577b34da6                      # cross-service replay
$ ulog purge --before 2024-06-01                   # honors min_retention_days
$ ulog repair --confirm                            # post-BROKEN recovery
```

---

## 6. Worked examples

### 6.1 Friday-night incident — find the cause in 30 seconds

Spike of 800 errors in 30 min. Without `correlate` : 30–45 min of manual
filter-clic-back-filter. With `correlate` :

```
$ ulog correlate 'level=ERROR AND date>-30min' --db ./logs.sqlite

▲ OVER-REPRESENTED                  ▼ UNDER-REPRESENTED
db_node=replica-3  87.2× ⚡⚡        http_status=200  0.01× (axis)
query_type=join    14.1× ⚡          service=cache    0.05×
service=payment    11.8× ⚡          level=DEBUG      0.00× (axis)
author=Lin Wong     4.3×

⊕ Intersect [db_node=replica-3 × query_type=join]: 142×

⚠ Sample size 800 — interpret confidence ≥ in_filter / 30.
```

→ replica-3 lags on join queries. Page the DBA, fix in 5 min.

### 6.2 Verify the chain — has anything been touched?

```
$ ulog verify
✓ Integrity verified
  records: 487,234
  chain length: 487,234 (all reachable)
  span: 2024-12-01 09:14:00Z → 2026-05-04 22:51:00Z
  walk time: 4.3s (NFR-PERF-52: ≤ 5s ✓)
  last verified: 2026-05-04 22:51:00Z
```

If broken :
```
$ ulog verify
✗ BROKEN
  ok up to record #142,070
  record #142,071: expected prev_hash=8aef21..., got 0123ab...
  records affected: 142,071 → 487,234 (345,164 records)
  next step: review the orphaned content with `ulog repair --dry-run`
```

### 6.3 Customer-specific bug

A customer reports "it crashes only for me, can't repro". You filter on
`user_id=42` and run correlate :

```
feature_flag.experimental_billing=true   ∞× (only this user)
region=eu-west-3                         18.2×
```

→ they enabled a feature flag + are in EU. Repro in 30 s on your dev
box with the flag set, EU region simulated.

### 6.4 Close an incident with a fix reference

```python
# 6 weeks after the original error fired — you've shipped the fix
ulog.resolve(
    incident_hash="3f7c12a09b8d4f...",
    by="Johan",
    note="connection pool max=20, services/db.py:47, deployed b7866ee",
)

# Now ulog incidents --status open shows one fewer entry:
$ ulog incidents --status open
#168,302  2026-03-21  ssl.cert_expired                 45d
#189,520  2026-04-08  api.rate_limit billing.com       27d
#201,331  2026-04-15  null_pointer checkout.py:412     20d

(was 4 open · 1 just resolved · 3 remain)
```

The original error record is **still there**, immutable. The
resolution is appended next to it in the chain, referenced by hash.

### 6.5 Generate a regression test from a real incident

```python
# Convert an incident into a permanent test
ulog.replay_to_pytest(
    filter="resolves='3f7c12a...'",
    output_path="tests/test_incident_3f7c12a_db_timeout.py",
)
```

Generated file (excerpt) :
```python
# Auto-generated by ulog v0.5 from incident 3f7c12a... on 2026-05-04
import pytest
import ulog
from ulog.testing import replay_records

INCIDENT_RECORDS = [
    # ... 12 records snapshotted from the chain, frozen-dict form ...
]

def test_incident_3f7c12a_db_timeout():
    """Regression test for db.timeout on services.payment.billing.

    Original incident: 2026-03-14 09:47:22Z
    Resolved by:       Johan, 2026-05-04 18:30Z
    Fix commit:        b7866ee
    """
    with replay_records(INCIDENT_RECORDS) as session:
        # Replay must NOT trigger any record where db_timeout=True
        assert not session.matches(lambda r: r.extras.get("db_timeout"))
```

→ the production incident becomes a permanent test. If the bug ever
returns, CI catches it immediately.

### 6.6 Cross-service replay for a distributed bug

```
$ ulog trace 4bf92f3577b34da6 --db ./shared/logs.sqlite

Replaying trace · 12 records · 3 services · 2 errors

  api-gateway       09:47:22.000  INFO   request received
  api-gateway       09:47:22.001  INFO   forwarded to payment
  services.payment  09:47:22.103  ERROR  db.timeout on charge_card()
  services.payment  09:47:22.150  WARN   retry attempt 1/3
  services.billing  09:47:22.180  INFO   reconciliation triggered
  services.payment  09:47:23.180  ERROR  db.timeout (retry 1)
  ...
```

→ Diego sees the full causal chain across 3 services without joining
logs by hand.

---

## 7. Roadmap continuation

### v0.6
- Jupyter notebook export (`ulog notebook <filter>`).
- Multi-track UI full : configurable tracks, solo, scrubber overlay,
  canvas rendering for ≥ 1 M records.
- Record lineage / chain-of-custody (`verified_at[]`, `replayed_at[]`,
  `exported_at[]`).
- Subclassable `ResolutionRecord` for typed resolutions.

### v0.7
- Multi-DB federation (`ulog trace --across server-a.sqlite,server-b.sqlite`).
- Streaming verify (Merkle tree per N records → O(log n) partial verify).
- ChainWriter abstraction for PostgreSQL backend.

### v0.8 / v0.9
- Webhook integration for incidents (`on_resolve` / `on_reopen` hooks).
- Diff-aware filtering ("show records first emitted after commit X").

### v1.0
- API freeze + `Stable` PyPI classifier + benchmark CI gate.
- The 7 invariants (§2.4) become a written contract documented in
  `STABILITY.md`.

---

## 8. Open questions

1. **Two physical tables (`logs_immutable` + `logs_rotable`) vs one with
   `immutable` column ?** Trade-off: column = simpler schema, single
   trigger handles the policy. Two tables = clearer mental model + index
   locality. **Recommend : column-flag** for v0.5, two-table optimization
   in v0.6 if perf demands it.

2. **`ulog.resolve()` body validation.** Do we accept arbitrary
   markdown, or enforce a schema (`note: str ≤ 1000 chars, links: list`) ?
   **Recommend : accept arbitrary** for v0.5 ; allow a user to subclass
   `ResolutionRecord` for typed resolutions in v0.6.

3. **Hash canonical form.** How do we serialize `extras={...}` for
   hashing ? Sorted JSON ? msgpack ? **Recommend : sorted JSON** via
   stdlib `json.dumps(sort_keys=True, separators=(',',':'))`. msgpack
   would be faster but adds dependency concerns.

4. **PostgreSQL backend.** SQLite has `BEGIN IMMEDIATE` ; PostgreSQL
   uses different lock semantics (`SELECT ... FOR UPDATE`).
   **Recommend : abstract behind a `ChainWriter` class**, default
   impl = SQLite (`BEGIN IMMEDIATE`), PG = `SELECT ... FOR UPDATE` on a
   chain-marker row. PG version ships in v0.7.

5. **Chain corruption recovery.** Hard fail or graceful degrade ?
   **Recommend : `ulog verify` reports BROKEN at exact #N ;
   subsequent writes blocked until the user runs `ulog repair --confirm`,
   which truncates the chain at the last valid record + archives
   orphaned content into `chain_break_<ts>.log` for forensics.** I4
   preserved : nothing silently dropped.

6. **OTel auto-bind in absence of OTel SDK.** Should ulog warn once at
   setup that "OTel binding inactive" ? **Recommend : silent no-op** —
   the feature is naturally opt-in by mere presence of OTel context. No
   warning needed.

---

## 9. Definition of Done — v0.5

- [ ] **Storage**
  - [ ] `logs_immutable` + `logs_rotable` tables with shared `chain_pos`
        sequence (FR90, FR91).
  - [ ] SQL trigger blocks `UPDATE`/`DELETE` on `logs_immutable`.
  - [ ] `ulog.setup(immutable_when=...)` plumbed end to end.
  - [ ] `ulog.setup(min_retention_days=N)` plumbed (FR92, FR93).
- [ ] **Hash chain**
  - [ ] `record_hash` + `prev_hash` computed at write under per-DB lock
        (FR94).
  - [ ] `ulog verify` CLI returns OK / BROKEN, exit code 0/1 (FR95).
  - [ ] UI integrity badge on every page (FR96, FR113).
  - [ ] `ulog repair --confirm` (FR97, NFR-REL-52).
- [ ] **Replay**
  - [ ] `ulog.replay(filter, on)` (FR98).
  - [ ] `ulog.is_replaying()` + `is_replay` flag (FR99, NFR-REL-51).
  - [ ] `ulog.replay_to_pytest(filter, path)` (FR100).
- [ ] **Query**
  - [ ] `ulog correlate <filter>` CLI + Python API (FR101–FR102, FR104).
  - [ ] `ulog bisect <pattern>` CLI + Python API (FR103, FR104).
  - [ ] Sample-size warnings + axis-skip behavior (FR102).
- [ ] **Incidents ledger**
  - [ ] `ulog.resolve()` / `ulog.reopen()` (FR105–FR106).
  - [ ] `ulog incidents --status` / `--report` CLI (FR107–FR108).
  - [ ] UI cross-links + incidents sidebar section (FR114, FR115).
- [ ] **Cross-service**
  - [ ] OTel `trace_id` auto-bind from contextvars (FR109).
  - [ ] `ulog trace <id>` CLI (FR110).
  - [ ] Issue button + URL template (FR111).
- [ ] **UI**
  - [ ] Multi-track minimal (4 fixed tracks, mute) (FR112).
- [ ] **Tests**
  - [ ] ≥ 30 unit tests for `resolve` + chain referential integrity
        (SC3).
  - [ ] `tests/test_chain_concurrency.py` 8 writers × 10 K records
        (NFR-REL-50).
  - [ ] `tests/test_qlnes_compat.py` v0.1 byte-stable test stays green
        (SC5 / I5 gate).
  - [ ] `tests/bench_*.py` for SC1 / SC2 / SC7 perf gates.
- [ ] **Type & quality**
  - [ ] `mypy --strict` green on the package (NFR-COMPAT-50).
  - [ ] `pyproject.toml dependencies = []` regression CI gate
        (SC4 / NFR-DEP-50).
- [ ] **Doc**
  - [ ] `ulog/web/docs/v0.5-forensic-archive.md` page (FR116, NFR-DOC-50).
  - [ ] Existing doc pages updated (FR117).
  - [ ] `BENCHMARK.md` with SC1/SC2/SC7 numbers.
  - [ ] `STABILITY.md` documenting the 7 invariants (will become
        official contract at v1.0).
- [ ] **Release**
  - [ ] Tag `v0.5.0` + push.
  - [ ] Migrate qlnes to v0.5 (`SC6` first reference user).
  - [ ] Identify + reach out to a second adopter (`SC6`).

---

## 10. Reference

- **Brainstorming session** : [`../../_bmad-output/brainstorming/brainstorming-session-2026-05-04-2051.md`](../../_bmad-output/brainstorming/brainstorming-session-2026-05-04-2051.md)
- **Predecessor PRDs** : [v0.4](./PRD-v0.4-commit-author-filter.md), [v0.3](./PRD-v0.3-test-integration.md), [v0.2.1](./PRD-v0.2.1-ui-bugfixes.md), [v0.2](./PRD-v0.2-storage-and-ui.md), [v0.1](./PRD-v0.1-core.md).
- **Validation reports of prior PRDs** : [`./validation/`](./validation/). The patterns flagged as `MAJOR` there (missing Success Criteria, persona ↔ FR traceability, NFRs without measurement methods) are explicitly addressed in this PRD (§1.4, §3 Persona column, §4 measurement methods).
