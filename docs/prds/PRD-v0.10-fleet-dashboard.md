---
docType: prd
project_name: ulog-python
version: 0.10.0
date: 2026-05-12
author: jojo8356
status: draft v1
parent_prd: PRD-v0.3-test-integration.md
related_prd:
  - PRD-v0.4-commit-author-filter.md
  - PRD-v0.5-forensic-archive.md
---

# ULog v0.10 — Fleet dashboard for remote endpoint tests

> Until now, ULog's tests target the local app. v0.10 generalises
> them: a test can hit a **remote URL / IP** (your own microservice,
> a partner's API, a TCP port). Results aggregate into a
> **hierarchical fleet dashboard** — parent/child service tree,
> cross-panel links, drill-down per endpoint. Synthetic monitoring
> built on the same pytest plumbing as v0.3.

---

## 0. 30-second pitch

You ship 20 microservices. Today, you have:

1. 20 GitHub Actions running 20 per-service test suites.
2. A separate uptime-monitoring SaaS pinging `/health` on each.
3. No correlation between the two, no parent/child tree, no shared timeline.

v0.10 unifies it:

```python
# tests/fleet/test_payments.py
import pytest
from ulog.fleet import probe

@probe(target='https://payments.internal/health',
       parents=['auth.internal', 'db.internal'])
def test_payments_health(client):
    r = client.get(timeout=2)
    assert r.status_code == 200
    assert r.json()['db'] == 'ok'
```

Run `ulog fleet run` → all probes execute → results land in the DB
with `target`, `parents`, `latency_ms`. The web viewer's new **Fleet
panel** renders a tree: `auth` ← `payments` ← `checkout`. Click a node
→ that service's records, last 24h uptime sparkline, parent/child
status, **cross-links to the Tests panel (v0.3) and the Authors panel
(v0.4)**.

---

## 1. Vision

### 1.1 Why this exists

Three observations:

1. **The pytest plugin (v0.3) already records test outcomes**. What's missing is the notion that a test can target a *remote endpoint*, and that endpoints have *dependency relationships*. Adding `target` + `parents` to the test schema unlocks a whole new UI.
2. **Synthetic monitoring (Pingdom, Statuscake, BetterUptime) lives in a different tool**. Engineers context-switch between "test results" and "uptime". Same record stream, same chain (v0.5), same UI = less cognitive load.
3. **Dependency graphs are how engineers think about systems**. Listing services flat is fine for 5; useless for 50. Parent/child + cross-panel links match the mental model.

### 1.2 What v0.10 isn't

- **Not a replacement for PagerDuty / Opsgenie.** No alerting, no escalation, no on-call rotation. v0.10 records + visualizes; you wire your own alerting hook (a v0.10.1 webhook callback maybe).
- **Not an APM.** No deep tracing, no flame graphs, no auto-instrumentation. Just probe-style health checks + their results.
- **Not a service catalog** (Backstage, Cortex). Targets are declared in code (`@probe(target=...)`), not in a YAML registry. Parent/child = nominal dependencies, not a runtime service mesh.
- **Not a load-test tool.** Probes are 1-shot. No concurrent fan-out, no ramp-up. k6 / Locust own that space.

### 1.3 Target users

- **Lin** (carried) — runs a 30-service CI fleet. Today, 30 separate `pytest.yml` workflows. After v0.10: one `ulog fleet run` per environment, one dashboard.
- **Marco** (carried) — solo dev with 3 services. Doesn't really need parent/child but does benefit from "one place to see if everything's green".
- **Sara** (carried) — library dev. Probes her library's CDN cache + the test fixture endpoints she ships. v0.10 is overkill for her — she'd use the simpler `@probe` decorator without the dashboard.
- **NEW persona: Maria** — site reliability engineer. Needs the parent/child tree to triage cascading failures. "Payments down → check auth (its parent) first."

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | Define a probe in 3 lines of code (`@probe(target=...)` + test body + assert) | yes |
| SC2 | `ulog fleet run` executes 50 probes in parallel; total wall time ≤ slowest probe + 1 s overhead | yes |
| SC3 | Fleet dashboard renders 50 nodes in ≤ 500 ms cold (NFR-PERF-110) | yes |
| SC4 | Parent/child cycle detected at registration time (not at runtime) | yes |
| SC5 | Cross-panel link from a fleet node → records filtered to that target works in 1 click | yes |
| SC6 | Probe targets accept HTTPS URL, HTTP URL, raw IP+port (e.g. `tcp://192.168.1.50:5432`), and Unix domain socket paths | yes |
| SC7 | Probe results inherit v0.5 chain integrity when the SQL backend is chain-mode | yes |

---

## 2. Scope (v0.10)

### 2.1 In scope (12 features, ~ 1 100 LOC `ulog/` core estimate)

1. **`@probe(target, parents=None, timeout=5, interval=None)` decorator** in `ulog/fleet/__init__.py`. Wraps a pytest function, registers the probe in a process-wide `_PROBE_REGISTRY`, adds `target` + `parents` to the emitted test records.
2. **Target adapters**: `HttpsProbeClient`, `HttpProbeClient`, `TcpProbeClient` (raw socket, returns latency + connection-OK boolean), `UnixSocketProbeClient`. Injected as the `client` fixture argument.
3. **`ulog fleet run [--target GLOB] [--parallel N] [--out DB]` CLI**. Runs all registered probes (or a subset), serialises results to the configured DB.
4. **Cycle detection** at `@probe` registration time — raises `FleetTopologyError` if adding the probe would create a cycle in the parent/child DAG.
5. **DB schema extension** — `targets` table (PK = `target` string, columns: `kind` http|tcp|unix, `parents` JSON list, `latest_status` enum, `latest_latency_ms` float). `logs` table gains nullable `target` column referencing it. Compatible with v0.5 chain (the new column is opt-in via the `[fleet]` extra).
6. **Fleet web panel** — new `/fleet/` page rendering a top-down tree. Each node: name + status badge (✓ pass / ✗ fail / ⚠ degraded / ⊘ never run) + last-run timestamp + latency. Click → drill-down `/fleet/<target>/`.
7. **Drill-down view `/fleet/<target>/`** — 24h uptime sparkline (SQL count GROUP BY hour), recent runs table, "view all records from this target" link to `/?target=<target>`, parent + child nodes listed with their statuses.
8. **Records-panel filter axis**: `?target=https://payments.internal/...`. Multi-select OR (consistent with v0.4 author filter). Plays nicely with existing filters.
9. **Cross-panel links**: from a fleet node, "view tests" links to v0.3 Tests panel filtered by `target`; "view authors" links to v0.4 Authors panel for any code-side records that emitted under this target's probes.
10. **`ulog fleet list`** + **`ulog fleet show <target>`** CLI sub-subcommands for shell-side introspection.
11. **Probe interval scheduler** (optional, for daemon mode) — `ulog fleet daemon` reads `interval=...` per probe and runs them on a `sched`-based loop. Out of v0.10 if dep cost is too high; deferred to v0.10.1.
12. **Doc page `/docs/fleet/`** + `/docs/fleet-quickstart/` with the 3-line example, parent/child tree explanation, cycle-detection example, and the daemon-mode preview.

### 2.2 Explicit non-goals (deferred to v0.10.x+ or never)

- **Alerting / escalation** — out forever (PagerDuty's domain).
- **gRPC / GraphQL probes** — out (HTTP / TCP / Unix covers 95% of use cases; gRPC is a v1.x extension).
- **Probe authentication** beyond `Authorization` header / mTLS via stdlib `ssl` — out. Complex auth flows = wrap your own client.
- **Multi-region probing** (run from N edge locations) — out. v0.10 runs locally; "multi-region" = run on N runners and merge DBs.
- **A WebSocket probe** — out. v0.10.x candidate.
- **Probe SLO tracking** (99.9% over 30 days) — out. v0.11+ candidate.
- **A read-write API for the targets table** (REST CRUD) — out. Targets are declared in code, not in the DB.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Probe registers with a parent that doesn't exist | Lazy: parent is registered as an "unknown" target with status `⊘ never run`. Allows out-of-order registration. |
| Probe registers and would create a cycle (A → B → A) | `FleetTopologyError` at import time. Test collection fails fast. |
| HTTPS probe target uses a self-signed cert | Default: fail with TLS error. `@probe(verify=False)` opts out (documented as DANGER). |
| Probe times out | Recorded as `✗ failed` with `reason=timeout`. Not a Python-level test failure unless the assertion catches it. |
| Network unreachable | Recorded as `✗ failed` with `reason=unreachable`. |
| Parallel run with 100 probes, network saturated | `--parallel N` caps concurrency. Default `N=10`. Documented. |
| Same target referenced by N probes | The `targets` table stores one row per target. The `logs` table has N records linking back to it. Status field reflects the WORST recent outcome (failed if any failed). |
| Daemon mode (v0.10.1) — system clock jumps | Use `time.monotonic()` for intervals, not `datetime.now()`. |

### 2.4 Protected invariants

- **I5 (carried):** Logging API unchanged. v0.10 is additive — probe decorator is a NEW import path (`ulog.fleet`).
- **I11 (new):** The fleet `targets` table is independent of the chain. Chain integrity (v0.5) operates on `logs`; v0.10's added `target` column on `logs` is part of the chain hash (canonical JSON includes it).

---

## 3. Functional Requirements

### 3.1 Probe decorator

- **FR151**: `@probe(target: str, parents: list[str] = None, timeout: float = 5.0, verify: bool = True, headers: dict = None)` on a pytest function. Registers in `_PROBE_REGISTRY`. Adds `target` + `parents` to records emitted by the test.
- **FR152**: `target` URI scheme dispatches the client fixture: `https://` → `HttpsProbeClient`, `http://` → `HttpProbeClient`, `tcp://host:port` → `TcpProbeClient`, `unix:///path/to/sock` → `UnixSocketProbeClient`.
- **FR153**: Each probe execution emits at minimum: `test.started` + `test.outcome` (v0.3) + a NEW `probe.result` record carrying `target`, `latency_ms`, `status_code` (HTTP) or `connected` (TCP/Unix), `error_msg` (None on success).
- **FR154**: `parents=[...]` registers edges in the topology DAG. Cycle → `FleetTopologyError` at decorator time.

### 3.2 CLI

- **FR155**: `ulog fleet run [--target GLOB] [--parallel N=10] [--out DB] [--timeout-override SECS]`. Runs all matching registered probes via `pytest -k <target>` under the hood; results materialise in the DB.
- **FR156**: `ulog fleet list` — prints targets + parents + last status as a table. `--format json` for piping.
- **FR157**: `ulog fleet show <target>` — single-target detail (last 24h status, last error, parent + child statuses).
- **FR158**: `ulog fleet validate` — registers all probes without running them, reports cycles / missing-parents.

### 3.3 Web viewer

- **FR159**: New `/fleet/` page rendered as a tree (Tailwind + minimal SVG / `<ul><ol>` nested). Top-level = nodes with no parents.
- **FR160**: Each tree node: badge + name + 24h-uptime sparkline (8 cells, 3h each).
- **FR161**: `/fleet/<target>/` drill-down: same data as `ulog fleet show` + full records list (filtered to that target) + parent + child links.
- **FR162**: Records panel sidebar gains "Targets" section (sortable by name / status, multi-select OR, `?target=...` URL).
- **FR163**: Cross-panel pivots: from a fleet node, links to v0.3 Tests panel and v0.4 Authors panel filtered to records emitted by that probe.

### 3.4 Documentation

- **FR164**: `/docs/fleet/` quickstart with 3-line example + parent/child explanation + cycle-detection demo + daemon-mode preview note.
- **FR165**: `/docs/fleet-targets/` — the 4 target schemes (HTTP, HTTPS, TCP, Unix) with one example each.

---

## 4. Non-Functional Requirements

- **NFR-PERF-110**: Fleet tree page on 100 nodes ≤ 500 ms cold (warm filesystem cache).
- **NFR-PERF-111**: `ulog fleet run` on 50 probes, `--parallel 10`, network latency 100 ms each: total ≤ 1 s (slowest batch) + 1 s overhead.
- **NFR-DEP-100**: Core probe clients use stdlib `urllib.request` (HTTP/HTTPS), `socket` (TCP/Unix). NO `requests` / `httpx` runtime dep. (Tests in the suite MAY use `requests` under `[dev]`.)
- **NFR-SEC-100**: HTTPS clients validate certs by default. `verify=False` is documented as DANGER + emits a stderr warning per probe run.
- **NFR-REL-100**: `FleetTopologyError` is raised at decorator-import time (test collection phase), NEVER mid-run.
- **NFR-DOC-100**: 3 doc pages: `/docs/fleet/`, `/docs/fleet-targets/`, `/docs/fleet-quickstart/`.

---

## 5. API surface (sketch)

### 5.1 Probe declaration

```python
from ulog.fleet import probe

@probe(
    target='https://payments.internal/health',
    parents=['https://auth.internal/health', 'tcp://db.internal:5432'],
    timeout=2.0,
)
def test_payments_health(client):
    r = client.get()
    assert r.status_code == 200
    assert r.json()['db'] == 'ok'
```

### 5.2 CLI

```bash
ulog fleet validate                       # cycle check, dry-run
ulog fleet run --parallel 20              # spawns workers
ulog fleet run --target '*payments*'      # filter
ulog fleet list --format json | jq '.[] | select(.status == "failed")'
ulog fleet show https://payments.internal/health
```

### 5.3 Setup (no change)

```python
ulog.setup(integrity='hash-chain', ...)
# Fleet is opt-in via `from ulog.fleet import probe` + `[fleet]` extra.
```

---

## 6. Implementation sketch

| Story | Scope | Est. LOC |
|---|---|---|
| 10.1 | `@probe` decorator + `_PROBE_REGISTRY` + topology DAG + cycle detection | 120 |
| 10.2 | `HttpsProbeClient` + `HttpProbeClient` (stdlib urllib) | 80 |
| 10.3 | `TcpProbeClient` + `UnixSocketProbeClient` (stdlib socket) | 70 |
| 10.4 | DB schema extension — `targets` table + `target` col on `logs` | 60 |
| 10.5 | `ulog fleet {run, list, show, validate}` CLI subcommands | 200 |
| 10.6 | `/fleet/` tree page (Django template + minimal CSS) | 150 |
| 10.7 | `/fleet/<target>/` drill-down + 24h sparkline | 130 |
| 10.8 | Targets sidebar in records list + `?target=` filter | 80 |
| 10.9 | Cross-panel links (Tests / Authors) | 60 |
| 10.10 | Edge cases (cycle, missing parent, TLS failure, timeout) as tests | ~ tests |
| 10.11 | Daemon-mode preview / deferred to v0.10.1 | DEFERRED |
| 10.12 | Doc pages `/docs/fleet/`, `/docs/fleet-targets/`, `/docs/fleet-quickstart/` | n/a |

Total ~ 950 LOC core (excludes templates + tests + docs).

---

## 7. Decisions log

| ID | Decision | Trade-off |
|---|---|---|
| D1 | Probes are declared in CODE via decorator, NOT in a YAML / DB | No runtime registry; CI-friendly; gitops compatible. Trade-off: no "add a probe via the UI". |
| D2 | Parent/child = nominal dependencies, NOT runtime topology | We don't introspect service meshes. User declares parents manually. Simple, predictable. |
| D3 | Stdlib `urllib` + `socket` for probe clients | Zero runtime dep. Trade-off: no fancy HTTP/2 / connection pooling. Adequate for health-check probes. |
| D4 | `parallel` via `concurrent.futures.ThreadPoolExecutor` | Threads are enough for I/O-bound probes; asyncio would force an `[async]` extra. |
| D5 | Target included in chain hash (v0.5 chain mode) | Forensic completeness: tampering with target field invalidates the chain. |
| D6 | Cycle detection at decorator-import time | Fail fast — broken topology never reaches `pytest_collection_finish`. |
| D7 | NO alerting | Out of scope forever. Webhook callback is a future v0.10.x extension. |
| D8 | NO incremental `target` column for non-chain users | The column is always present on a v0.10 DB; just NULL when no probe touched it. Trade-off: small storage cost vs schema-version proliferation. |
| D9 | Probe interval daemon DEFERRED to v0.10.1 | Daemon needs robust scheduling + shutdown + signal handling; lots of bug surface. Ship the manual `ulog fleet run` first, validate UX, then layer daemon on top. |

---

## 8. Open questions

| ID | Question | Tentative |
|---|---|---|
| Q1 | Should probes inherit `min_retention_days` floor (v0.5) for their result records? | Yes — uniform with the rest of the archive. |
| Q2 | Tree layout: top-down (parent at top, children below) or left-right (parent left, children right)? | Top-down by default; `--orientation horizontal` for wide trees as v0.10.x option. |
| Q3 | How to render a target with 50+ children? Collapse by default? | Collapse if count > 8; "show all" link. |
| Q4 | Should the `parents` attribute support glob patterns (`parents=['*db*']`)? | No — too implicit. Explicit list only. |
| Q5 | If probe target is `https://example.com` AND the URL returns 404, is the probe failed or degraded? | Failed by default. User overrides via `@probe(success_codes=[200, 404])`. |

---

## 9. References

- [Source: docs/prds/PRD-v0.3-test-integration.md] — pytest plugin foundation
- [Source: docs/prds/PRD-v0.4-commit-author-filter.md] — sidebar panel + multi-select OR pattern reused for Targets
- [Source: docs/prds/PRD-v0.5-forensic-archive.md] — chain integrity invariant for the new `target` field
- [Source: BetterUptime / Statuscake docs] — competitive baseline for synthetic monitoring UX
- [Source: stdlib `urllib.request`, `socket`] — chosen probe-client transports
