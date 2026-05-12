---
docType: prd
project_name: ulog-python
version: 0.6.1
date: 2026-05-12
author: jojo8356
status: draft v1
parent_prd: PRD-v0.6-static-export.md
---

# ULog v0.6.1 — Multi-format snapshot exports

> `ulog export-html` already ships (v0.6). v0.6.1 generalises it
> into `ulog snapshot --format <fmt>` and adds 4 more formats:
> `.log` (qlnes plain text), `.json` (line-delimited), `.csv`,
> and `.pdf` (rendered from the HTML via headless Chromium —
> opt-in dep). Defaults to "today's records" (`--since today`)
> so a single command produces a daily archive.

---

## 0. 30-second pitch

The HTML export is great for browser archival but useless for:

- Compliance: auditors want **PDF** (timestamped, page-numbered, signable).
- ETL pipelines: ops want **JSON Lines** to pipe into Splunk / ELK.
- Spreadsheets: managers want **CSV** to slice in Excel.
- `grep`-friendly archives: ops want **plain `.log`** (qlnes format), one record per line.

`ulog snapshot --format pdf` produces a daily compliance report;
`ulog snapshot --format json --since today` becomes a `cron` 1-liner
piped into Filebeat. Same source-of-truth (the SQL chain DB), same
filter semantics, four new output channels.

---

## 1. Vision

### 1.1 Why this exists

Three frictions surfaced post-v0.6 launch:

1. **Compliance officers won't accept HTML.** PDF is the audit format. Producing one currently requires opening the HTML in a browser and File → Print → Save as PDF (manual, lossy timestamps).
2. **CI pipelines want machine-readable.** "Attach today's logs to the build artefact" wants `.json` or `.csv`, not 12 MB of HTML.
3. **The `ulog-web` viewer is great for live triage, but you can't email a viewer link** — you email a file. Plain `.log` (qlnes-formatted, one record per line) is the universal "send this to support" format.

### 1.2 What v0.6.1 isn't

- **Not a custom report-builder.** No templated PDFs with project logo / cover page / TOC. Just: header (project, range, count) + the records table. The HTML export's layout, headless-rendered.
- **Not an incremental exporter.** Each snapshot is a fresh point-in-time dump. The verify_state.json sidecar (v0.5) annotates the snapshot's integrity status but doesn't merge across snapshots.
- **Not a streaming exporter for huge ranges.** Same 100 K-record budget as v0.6 HTML export. Beyond that, page via `--since / --until` chunks.

### 1.3 Target users

- **Erika** (carried, v0.5 compliance officer) — needs **PDF** daily. Cron job: `0 0 * * * ulog snapshot --format pdf --since yesterday --out /audit/$(date -I).pdf`.
- **Lin** (carried, pipeline integrator) — pipes **JSON** into Filebeat. `ulog snapshot --format json --since today --out /tmp/today.jsonl && filebeat -e -c .filebeat.yml`.
- **Sara** (carried) — exports **CSV** to share with a teammate auditing a regression: `ulog snapshot --format csv --filter level:ERROR --out incident.csv`.
- **Marco** (carried, solo dev) — `.log` to grep: `ulog snapshot --format log --since today | grep timeout`.

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | All 5 formats (html / log / json / csv / pdf) produce a non-empty file on a 10-record sample | yes |
| SC2 | JSON Lines output round-trips through `json.loads` line-by-line | 100% |
| SC3 | CSV output opens cleanly in LibreOffice + Excel with UTF-8 + correct column count | yes |
| SC4 | PDF output renders header + records table on a single page for ≤ 30 records, multi-page for more | yes |
| SC5 | `.log` output is `cat`-able, one record per line, qlnes format identical to runtime output | yes |
| SC6 | Wall time on 10 000 records: html ≤ 5 s, json ≤ 1 s, csv ≤ 1 s, log ≤ 1 s, pdf ≤ 10 s (Chromium spin-up) | yes |
| SC7 | PDF dep is OPTIONAL — `ulog[snapshot-pdf]` extra installs `playwright`; without it, `--format pdf` errors with a clear "install ulog[snapshot-pdf]" message | yes |

---

## 2. Scope (v0.6.1)

### 2.1 In scope (6 features, ~ 350 LOC)

1. **`ulog snapshot --format FMT [--since EXPR] [--until EXPR] [--filter K:V] [--out PATH]` CLI subcommand**. Wraps v0.6's HTML export + 4 new formats.
2. **`.log` (qlnes plain text)** — reuses `ulog/formatters/qlnes.py` to format each record; one record per line, no color codes (color stripped via `color='never'`).
3. **`.json` (JSON Lines)** — `json.dumps(record_dict, sort_keys=False, separators=(",", ":"))` per record, `\n`-terminated.
4. **`.csv`** — header row `[ts, level, logger, msg, file, line, context_json, exc_json]` then rows. UTF-8 BOM optional via `--csv-bom` for Excel friendliness.
5. **`.pdf`** — render the HTML export via Playwright headless Chromium (`page.pdf(path=...)`). Behind `[snapshot-pdf]` extra. Graceful error when extra not installed.
6. **`--since` / `--until` date expressions** — `today`, `yesterday`, `1h`, `1d`, `2026-05-12`, ISO datetime. Stdlib `datetime.date.fromisoformat` + a small regex for the relative forms.

### 2.2 Explicit non-goals (deferred to v0.6.2+)

- **PDF templating** (logo / cover / TOC) — out. v0.7+ candidate.
- **Excel `.xlsx`** native (openpyxl) — out. CSV is universal enough.
- **Streaming exports** for > 100K records — out. Same budget as v0.6.
- **Multipart archive** (`.zip` of all 5 formats) — out. The user pipes if they want it: `ulog snapshot --format json --out -` (stdout) etc.
- **Custom column projection** (`--columns ts,level,msg`) — out. Defaults are sane.
- **Pre-signed S3 upload** — out. Local-file output only.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Empty range (0 records match filters) | Produce a valid empty file with header (CSV header only / JSON empty file / PDF "no records" page / HTML empty table / .log empty file). Exit 0. |
| `--out PATH` already exists | Refuse with `Use --force to overwrite`. Exit 2. |
| `--out -` (dash) | Write to stdout (text formats only — pdf raises). |
| `--format pdf` without `[snapshot-pdf]` extra | Exit 2 with `Install ulog[snapshot-pdf] to enable PDF export (Playwright + Chromium ~ 200 MB).` |
| `--since 1h` on a DB with no recent records | Empty output. Not an error. |
| Records with non-ASCII msg (e.g. `é`, `日本語`) | UTF-8 throughout. CSV: tested with both default and `--csv-bom`. |
| Record has a 1 MB context JSON | Truncated to 1 KB in CSV (`...` suffix) for spreadsheet sanity; full in JSON / log / pdf / html. |

### 2.4 Protected invariants

- **I5 (carried):** Logging API unchanged. v0.6.1 is purely a CLI/CLI-tooling feature.
- **I10 (new):** Core formats (html / log / json / csv) have ZERO new PyPI runtime deps. PDF is opt-in.

---

## 3. Functional Requirements

- **FR141**: `ulog/_cli/cmd_snapshot.py` registered. Subcommand: `snapshot`. Required: `--format {html,log,json,csv,pdf}`. Optional: `--since`, `--until`, `--filter K=V` (repeatable), `--out PATH`, `--force`, `--csv-bom`.
- **FR142**: `--since` / `--until` parser accepts: ISO date (`2026-05-12`), ISO datetime (`2026-05-12T14:30:00`), relative `1h` / `2h` / `1d` / `7d`, keyword `today`, `yesterday`, `now`.
- **FR143**: Filters: `--filter level=ERROR`, `--filter logger=svc.payments`, `--filter msg~timeout` (substring), `--filter context.tenant_id=acme`. Same parser as the web viewer's URL filters.
- **FR144**: Default `--out` = `./ulog-snapshot-<UTC-iso-no-colons>.<ext>` (e.g. `./ulog-snapshot-2026-05-12T14-30-00Z.json`).
- **FR145**: `--format log` runs each record through the qlnes formatter with `color='never'`, separator `\n`.
- **FR146**: `--format json` outputs JSON Lines — one full record per line (`ts` as ISO, `record_hash`/`prev_hash` as hex, JSON-typed `exc`/`context`). Compatible with v0.5's chain output.
- **FR147**: `--format csv` outputs 8 columns: `ts, level, logger, msg, file, line, context_json, exc_json`. The two JSON columns are stringified JSON (re-parseable downstream).
- **FR148**: `--format pdf` renders the HTML export to PDF via Playwright. Print CSS handles page breaks every 25 records.
- **FR149**: Exit 0 on success (even on 0 records), 1 on partial failure (e.g. some records unrenderable), 2 on usage/dep errors.
- **FR150**: Doc page `/docs/snapshot/` with one example per format + cron snippet for daily PDF audit.

---

## 4. Non-Functional Requirements

- **NFR-PERF-100**: On 10 000 records: html ≤ 5 s, log/json/csv ≤ 1 s, pdf ≤ 10 s on Linux dev machine.
- **NFR-DEP-90**: html/log/json/csv use stdlib + existing ULog modules only. PDF behind `[snapshot-pdf]` extra (Playwright + Chromium downloaded via `playwright install chromium`).
- **NFR-DOC-100**: Cron example with 7-day rotation in the doc page (`find /audit -name '*.pdf' -mtime +7 -delete`).
- **NFR-SEC-90**: No shell concatenation when invoking the HTML→PDF pipeline. Playwright Python API; no `subprocess(["chromium", ...])`.

---

## 5. API surface (sketch)

```bash
# Daily compliance PDF cron
ulog snapshot --format pdf --since yesterday --out /audit/$(date -I).pdf

# Today's CSV for spreadsheet review
ulog snapshot --format csv --filter level=ERROR --out errors-today.csv

# Pipe JSON into Filebeat
ulog snapshot --format json --since 1h --out - | filebeat -e -c filebeat.yml

# Send a `.log` to support
ulog snapshot --format log --filter logger=auth --out auth-incident.log
```

---

## 6. Implementation sketch

| Story | Scope | Est. LOC |
|---|---|---|
| 6.1-1 | `cmd_snapshot.py` + `--since`/`--until` parser | 80 |
| 6.1-2 | `--filter K=V` parser (shared with web viewer's URL filters) | 40 |
| 6.1-3 | `.log` writer (qlnes formatter, color off) | 30 |
| 6.1-4 | `.json` writer (JSON Lines) | 30 |
| 6.1-5 | `.csv` writer (8 cols, optional BOM, msg truncate) | 50 |
| 6.1-6 | `.pdf` writer (Playwright + `[snapshot-pdf]` extra wiring) | 60 |
| 6.1-7 | `.html` writer (delegate to v0.6's `export-html` impl) | 20 |
| 6.1-8 | Doc page `/docs/snapshot/` | n/a |

Total ~310 LOC.

---

## 7. Decisions log

| ID | Decision | Trade-off |
|---|---|---|
| D1 | One CLI subcommand `snapshot` covering all 5 formats | Avoids `ulog export-csv` / `ulog export-pdf` proliferation. `--format` enum is discoverable. |
| D2 | PDF via Playwright headless Chromium, opt-in | Pixel-perfect fidelity to HTML export; cost is the 200 MB Chromium dep. Behind extra. |
| D3 | `.log` output uses the qlnes formatter (not a JSON-like compact form) | Goal is `grep`-friendliness, not parse-ability. JSON Lines covers parse-ability. |
| D4 | CSV truncates msg / context_json to 1 KB | Spreadsheets choke on multi-MB cells. Full data lives in `.log` / `.json` / `.pdf`. |
| D5 | `--out -` writes to stdout for text formats; PDF refuses | PDF is binary + needs a seek-able sink for Chromium's writer. |
| D6 | Default filename includes UTC timestamp no-colons (Windows-safe) | Mirrors Story 3.8's sidecar pattern. |
| D7 | No `.xlsx` native export | `openpyxl` is a heavy dep; CSV opens in Excel fine. |

---

## 8. Open questions

| ID | Question | Tentative |
|---|---|---|
| Q1 | PDF: include the chain integrity status badge from `verify_state.json`? | Yes — top-right of the cover (or first-page header). |
| Q2 | JSON Lines: include `chain_pos` / `record_hash` / `prev_hash` always, or only when chain mode is active? | Always (NULL when absent — harmless for non-chain DBs). |
| Q3 | CSV: should we sanitise newlines in `msg` to `\n` literal? Excel handles quoted multi-line cells but it's brittle. | Yes, replace `\n` → `\\n` in CSV writer (documented in doc page). |

---

## 9. References

- [Source: docs/prds/PRD-v0.6-static-export.md] — HTML export precedent + filter parser shared
- [Source: ulog/formatters/qlnes.py] — qlnes formatter for `.log` output
- [Source: ulog/_cli/cmd_verify.py] — CLI scaffolding pattern (register/run)
- [Playwright Python `page.pdf()`] — used for HTML→PDF rendering
