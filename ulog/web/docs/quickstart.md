# Quickstart

Five steps from "I'd like persistent logs" to "I'm debugging a user report in
the browser."

## 1. Install

```bash
pip install ulog[storage,web]
```

## 2. Configure your application

```python
import ulog
ulog.setup(
    handlers=['stream', 'sql'],
    sql_url='sqlite:///./logs.sqlite',
)
log = ulog.get_logger(__name__)
log.info("hello")
```

## 3. Run your code

Logs accumulate in `./logs.sqlite` (and on stderr, since we kept `stream`
in the handler list).

## 4. Open the inspection UI

```bash
ulog web ./logs.sqlite          # v0.5+
# (previously: `ulog-web ./logs.sqlite` — removed in v0.5; see RELEASE_NOTES.md)
```

A browser tab opens on `http://127.0.0.1:<random-port>` with the filter
sidebar already populated.

## 5. Filter

- Tick **ERROR** in the **Level** sidebar to focus on what failed.
- Click a **Sector** to drill into one part of the codebase
  (e.g. `qlnes.audio.renderer`).
- Click a row to open the full detail view (JSON pretty-print + traceback).

That's it. No daemon to keep running, no auth wall to set up, no infra cost.

## v0.5 quick tour

If you're on **v0.5+**, three knobs add forensic-grade features
without touching your call sites:

```python
ulog.setup(
    integrity="hash-chain",       # SHA-256 chain in SQLite (Epic 3)
    min_retention_days=30,        # rows past this date are immutable
    handlers=["sql"],
    sql_url="sqlite:///./logs.sqlite",
    issue_template_url="https://linear.app/team/new?title={msg}&description={body}",
)
```

Now :

- **Verify** the chain anytime: `ulog verify ./logs.sqlite` — green if
  intact, red `BROKEN at #N` if tampered. See [v0.5 doc](v0.5-forensic-archive).
- **Resolve incidents**: `ulog.resolve(hash, by="Johan", note="...")`
  emits a `RESOLVED` record that links to the original.
- **Cross-service trace**: set `traceparent` env (W3C); ulog
  auto-binds `trace_id` to every record. Query across services with
  `ulog trace <id>`.
- **Multi-track view**: navigate to `/multi-track` for 4 SVG strips
  (level / service / author / file) over the shared time axis.
- **Integrity badge** on every page header turns green after `ulog
  verify`, red if the chain breaks.

Full feature tour: [v0.5 — Forensic black box](v0.5-forensic-archive).
