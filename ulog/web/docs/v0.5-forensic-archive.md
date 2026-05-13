# v0.5 — Forensic black box

Hash-chained immutable log archive, post-mortem replay/correlate,
incident lifecycle, cross-service OTel correlation, and a richer UI.
All zero-PyPI-dep at the core, opt-in storage / web extras.

## 30-second pitch

Your application's logs become a **black box** — every record links
to the previous via SHA-256, so any tampering anywhere in history
is detectable by walking the chain. Resolve / reopen incidents
in-place; the chain remembers. Replay the chain through a callback
for post-mortem; iterate filtered records through a DSL; bisect for
the first match of a regex. Cross-service correlation via the W3C
`traceparent` env var (no OpenTelemetry SDK required). All of it
queryable in the same Django UI you already have, with an
integrity badge on every page header.

## The 7 invariants (I1 → I7)

These are the contractual properties v0.5+ guarantees forever
(see `STABILITY.md` for the prose contract):

1. **I1 — Auto-class**: every record is auto-classified `level` /
   `logger` / `file` / `line` from the stdlib `LogRecord`. No
   manual tagging required.
2. **I2 — Local-first**: zero network calls; everything lives in
   one SQLite file (or JSONL / CSV).
3. **I3 — Verify-offline**: `ulog verify <db>` works fully offline,
   reads only the local DB, deterministic exit codes.
4. **I4 — Immutable-hard**: rows past `min_retention_days` cannot
   be UPDATE'd or DELETE'd via SQL — a trigger enforces it.
5. **I5 — Stdlib-compat**: `logging.getLogger(__name__).info("x")`
   continues to work byte-identical to v0.1 forever.
6. **I6 — Untagged-works**: code that has never called `ulog.setup()`
   still emits cleanly via the stdlib defaults.
7. **I7 — No-phone-home**: ulog itself never contacts the network.
   Opt-in features (v0.15 community solutions) gate every call
   behind explicit consent.

## 6 worked examples

### A) Storage / integrity — enable the chain

```python
import ulog
ulog.setup(
    integrity="hash-chain",
    handlers=["sql"],
    sql_url="sqlite:///./logs.sqlite",
    min_retention_days=30,   # rows older are immutable
)
ulog.get_logger().error("checkout failed: stripe 5xx")
```

Verify any time:

```bash
ulog verify ./logs.sqlite
# Integrity ✓ verified up to #1234 (wall: 12ms)
```

Tamper detection:

```bash
sqlite3 ./logs.sqlite "UPDATE logs SET msg='clean' WHERE chain_pos=42"
ulog verify ./logs.sqlite
# Integrity ✗ BROKEN at #42 — record_hash mismatch
```

### B) Replay — re-iterate a slice through a callback

```python
import ulog
ulog.replay(
    "./logs.sqlite",
    where_dsl="level=ERROR AND logger=globex.payments",
    on=lambda r: print(r["chain_pos"], r["msg"]),
)
# Inside the callback: ulog.is_replaying() is True.
# Records are MappingProxyType — mutation raises TypeError.
```

For tests:

```python
from ulog.testing import replay_records
RECORDS = [{"level": "ERROR", "logger": "svc", "msg": "boom"}]
with replay_records(RECORDS) as session:
    do_thing()
    assert session.matches(lambda r: "boom" in r.msg)
```

### C) Query — correlate / bisect / DSL

```bash
# Which context fields are over/under-represented under a filter?
ulog correlate "level=ERROR" --db ./logs.sqlite

# First record matching a regex (chain walk; deterministic)
ulog bisect "stripe.*5\d\d" --db ./logs.sqlite

# Iterate matching records, with optional --to-pytest to generate a
# regression test from the slice.
ulog replay "level=ERROR AND service=checkout" --db ./logs.sqlite \
  --to-pytest /tmp/test_inc.py --incident-hash 3f7c12a --topic dbtimeout
```

### D) Incidents — lifecycle in the chain

```python
import ulog
ulog.setup(integrity="hash-chain", handlers=["sql"], sql_url="...")
ulog.get_logger().error("database connection timeout")  # incident
# Later, in a fix commit:
ulog.resolve("3f7c12a", by="Johan", note="restarted db pool")
# A week later, recurrence:
ulog.reopen("3f7c12a", reason="recurrence after deploy")
```

CI gate:

```bash
ulog incidents --status open --db ./logs.sqlite ; echo "exit=$?"
# exit code = number of currently-open incidents
```

Postmortem KPIs:

```bash
ulog incidents --report --since 1m --db ./logs.sqlite > /tmp/r.md
# Markdown table with opened/closed/net-debt/MTTR/P95/reopens/top-closers
```

### E) Cross-service — OTel auto-bind

No `pip install opentelemetry-*` required. Set the W3C env or call
the contextvar setter; ulog binds `trace_id` / `span_id` to every
record emitted in that scope.

```bash
# Service A
traceparent=00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 \
  python my_app.py

# Service B (same trace propagated)
ulog trace 4bf92f3577b34da6a3ce929d0e0e4736 --db ./shared.sqlite
# 12 record(s) for trace_id 4bf92f...
#   2026-05-12T07:00:01  INFO   auth.login   user=u_042
#   ... (records from both services, time-sorted)
```

### F) UI — what changes in the viewer

- **Integrity badge** in the header on every page (gray "never
  verified" / green "✓ #N" / red "BROKEN at #N").
- **Incidents sidebar** on `/` — three radios (Open / Closed last
  7d / Reopened) with per-state counts.
- **Detail-page Incident panel** — `Resolves: #N` / `Resolved by:
  #M (Johan, ts, "note")` cross-links.
- **Multi-track view** at `/multi-track` — 4 horizontal SVG strips
  (level / service / author / file) with mute toggles.
- **"Open issue" button** on detail when `setup(issue_template_url=
  "https://linear.app/team/new?title={msg}&body={body}")` is
  configured — URL-encoded placeholders + 5-record body window.

## Troubleshooting

### `ulog verify` reports BROKEN

The chain is corrupt at the reported `chain_pos`. Two cases:

- **Accidental** (sqlite3 -batch UPDATE / external tool wrote): run
  `ulog repair --confirm` to archive the orphaned rows to a sidecar
  JSONL and truncate the chain to the last-good position. The
  archive file lets you forensically inspect what was lost.
- **Malicious** (someone tampered with audit data): the chain
  detects but cannot undo. The orphaned-rows JSONL preserves
  whatever they wrote; investigate. Re-opening the SQLHandler in
  chain mode after `verify=BROKEN` raises `SchemaError` until
  `ulog repair --confirm` clears the sidecar.

### OTel auto-bind silently does nothing

Three failure modes that look identical (no `trace_id` attached, no
warning printed):

1. `traceparent` env var absent — by design.
2. `traceparent` env var malformed (not matching the W3C regex) —
   silently ignored (Gap G4 documented).
3. The `_OTEL_TRACE_CONTEXT` contextvar was set in a different
   thread / async task — contextvars are per-context.

Check with `os.environ.get("traceparent")` + `ulog._otel.current_trace_context()`.

### `min_retention_days` mismatch on re-open

If you previously set `min_retention_days=30` and re-open with
`min_retention_days=7`, ulog warns (Story 3.6 — protect the
operator's stated retention floor). Pass the same floor or higher
on re-open.

### Where to go next

- Filter DSL grammar: `docs/api.md` (Story 4.4 section).
- Storage schema: `docs/storage.md` (v0.5 chain columns section).
- CLI ergonomics + automated QA mirror: in-app `/_qa/` checklist
  (debug-only).
