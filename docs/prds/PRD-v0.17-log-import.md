---
docType: prd
project_name: ulog-python
version: 0.17.0
date: 2026-05-12
author: jojo8356
status: draft v1
parent_prd: PRD-v0.5-forensic-archive.md
related_prd:
  - PRD-v0.2-storage-and-ui.md
  - PRD-v0.6.1-snapshot-exports.md
---

# ULog v0.17 — Log import (`ulog import`)

> Ingest any external log file — `.log`, `.txt`, JSONL from another
> tool, syslog, journalctl JSON, nginx/Apache access logs, plain text
> with a regex — into a ulog SQLite DB so it can be browsed, filtered,
> correlated, and replayed with the full v0.5 feature set.
> **Inverse of v0.6.1 export.** One-shot ingestion, not a live tail.

---

## 0. 30-second pitch

Today ulog can only browse logs it produced itself (or files written
by code using `JSONLineHandler` / `CSVHandler`). The forensic
black box is great — but only **after** you commit to ulog as the
log writer.

v0.17 ships `ulog import <input>… --db <target.sqlite>`. Point it
at an `nginx-access.log`, a `journalctl -o json-pretty` dump, a
Splunk export, or any custom format with a regex — it parses each
line into the ulog schema and inserts into a SQLite DB you can open
with `ulog-web`. Browsable, filterable, multi-track-able like any
other ulog DB.

**Use case** : a dev inherits a 200 MB nginx log file from prod.
`ulog import access.log --db prod.sqlite --format nginx`; open
ulog-web → filter by status=5xx, sector=/api/auth, time range
last 1h, correlate on user-agent — without writing a single grep.

---

## 1. Vision

### 1.1 Why this exists

Three observations:

1. **ulog's viewer / replay / correlate are 90% useful for anyone with
   "a bunch of log files" — but they only accept ulog's own outputs.**
   Removing that constraint multiplies the addressable use cases by
   the population of devs who have legacy log archives but haven't
   adopted ulog as a writer.
2. **The schema is generic enough** : `ts / level / logger / msg /
   file / line / context (JSON)` maps cleanly onto syslog (facility →
   logger, severity → level), nginx (status → level via bucket,
   remote_addr → context.client_ip), journalctl (`_SYSTEMD_UNIT` →
   logger, `PRIORITY` → level). The chain integrity (`record_hash`,
   `prev_hash`, `chain_pos`) is left NULL — imports are NOT part of
   the trust chain.
3. **One-shot wins over live tail in scope.** Live `tail -F` is a
   different beast (file rotation, buffering, stderr handling). v0.17
   covers the bulk-ingest case; a v0.17.1 patch could later add
   `--follow`.

### 1.2 What v0.17 isn't

- **Not a live tail.** `--follow` mode is explicitly out of v0.17.
- **Not a chain extension.** Imported records get `chain_pos=0`,
  `record_hash=NULL`, `prev_hash=NULL`, `is_imported=1` (new column,
  defaults to 0). The chain integrity badge stays valid because
  imported rows are skipped by the verifier (same convention as
  `is_replay=1`).
- **Not a parser zoo.** Six built-in formats + a regex escape hatch.
  Adding the seventh built-in requires a PRD patch (`v0.17.1` style).
- **Not a transformation pipeline.** No filtering, no enrichment, no
  field renaming during import. What you ingest is what you get.
  Use SQLite SQL or `ulog replay --to-pytest` for downstream work.
- **Not bidirectional.** Round-trips (`ulog snapshot --format jsonl
  | ulog import - --format jsonl` → same DB) are best-effort and
  don't restore the chain (intentional — chain only exists for the
  writer).

### 1.3 Target users

- **Riad** (carried) — junior dev handed an nginx log to "find the
  5xx spike". Wants a UI, not 4 hours of awk.
- **NEW: Salim**, SRE — runs `journalctl -o json -u myservice > log.json`
  on a remote host nightly, scp's to laptop, wants the v0.5 multi-track
  view on weeks of journald output without instrumenting the service.
- **NEW: Camille**, security analyst — got a syslog dump from a
  compromised box. Needs to correlate by `auth.priority=ERROR` and
  search ts windows. Doesn't want to install ELK.
- **Marco** (carried) — wrote a CLI tool that emits its own JSON
  lines. Wants the ulog viewer for free.

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | `ulog import <file> --db <out>.sqlite` produces a DB openable by `ulog-web` with sidebar filters working | yes |
| SC2 | Auto-detect format from extension + content sniff on 6 built-in formats (jsonl, csv, nginx-combined, apache-combined, syslog, journald-json) | yes |
| SC3 | 100K-line nginx log imports in ≤ 30 s on a 2026-spec laptop (streaming, no full-file load) | yes |
| SC4 | Regex escape hatch: `--format 'regex:(?P<ts>\S+) (?P<level>\S+) (?P<msg>.+)'` works on arbitrary plain-text files | yes |
| SC5 | Imported records visually marked in viewer: a small `imported` chip in the record list (next to the level pill) so the user always knows what's chain-backed vs imported | yes |
| SC6 | Round-trip via `ulog snapshot --format jsonl` → `ulog import - --format jsonl` reproduces the same records (excluding chain fields) | yes |
| SC7 | Compressed files (`.gz`, `.bz2`, `.zst`) transparently decoded; opt-in for zstd via `[import-zstd]` extra | yes |
| SC8 | Malformed lines (parse failure) reported on stderr with line number; `--strict` aborts on first failure, default continues + final count | yes |
| SC9 | Zero new mandatory PyPI runtime deps (stdlib `gzip` / `bz2`; `zstandard` opt-in) | yes |

---

## 2. Scope (v0.17)

### 2.1 In scope (~ 700 LOC + tests)

1. **CLI `ulog import <input>… --db <out>.sqlite`** — accepts one
   or more input paths (glob OK), one output SQLite path. `-` for
   stdin. Creates the DB if absent (schema = current ulog v0.5
   schema + new `is_imported BOOLEAN DEFAULT 0` column).
2. **`--format <name>`** — values: `auto` (default), `jsonl`,
   `csv`, `nginx-combined`, `apache-combined`, `syslog` (RFC3164
   + RFC5424 dual), `journald-json`, `raw` (one record per line,
   level=INFO, msg=full line), `regex:<pattern>`.
3. **Auto-detect (`--format auto`)** — extension first (`.jsonl` →
   jsonl, `.csv` → csv), then content sniff on first 100 lines
   (look for nginx-combined signature, syslog RFC3164 leader,
   journald JSON keys `__REALTIME_TIMESTAMP`, etc.).
4. **6 built-in parsers** — each maps source fields to the ulog
   schema. Decision D1 codifies the mappings; mismatches stay in
   `context` JSON.
5. **Regex escape hatch (`--format regex:<pattern>`)** — Python
   `re` pattern with named groups. Recognised group names: `ts`,
   `level`, `logger`, `msg`, `file`, `line`. Unrecognised groups
   land in `context`.
6. **Streaming reader** — chunked line iteration (no full-file
   load). Compressed files (`gzip`/`bz2`) auto-decoded via stdlib;
   `.zst` via opt-in `[import-zstd]` extra (lazy `zstandard` import).
7. **Schema migration** — `is_imported BOOLEAN DEFAULT 0` column
   added by the import CLI on first write to a fresh DB; existing
   DBs get an `ALTER TABLE` on first import (Story 3.3-style
   upgrade message with copy-paste SQL when running under a
   read-only user).
8. **Imported-record chip** — viewer record-list row shows a small
   `imported` slate chip next to the level pill when
   `is_imported=1`. Hidden when no imported rows exist in the
   visible page (zero-cost when unused).
9. **Strict mode (`--strict`)** — abort on first parse failure with
   line number + raw line. Default: skip + log warning, final
   stderr summary `"N lines imported, M skipped (parse errors)."`
10. **Doc page `/docs/import/`** — covers the 6 built-in formats,
    field mappings, regex examples (apache, nginx-error, custom
    pipe-delimited), the `is_imported` chain semantics, and the
    snapshot ↔ import round-trip.

### 2.2 Explicit non-goals

- **Live tail / `--follow`** — out of v0.17; later patch.
- **Field transformation / renaming / filtering during import** —
  out. Import is "read, parse, insert verbatim". Use SQL or replay
  for downstream changes.
- **Authorship inference** (`git blame` on imported records' `file`
  field) — out. Imported records have `file`/`line` ∈ the *source
  system*, not the local repo. v0.4 author index doesn't apply
  meaningfully.
- **Reverse-chain reconstruction** — out. An imported batch
  cannot retroactively join the local chain; that would violate
  the trust model.
- **Schema customisation per-import** — out. The ulog schema is
  fixed; arbitrary user fields go in `context` JSON.
- **PII redaction during import** — out. Use the regex format with
  capture-group rewriting at the source (or pipe through `sed`)
  before `ulog import`.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Source file has no recognisable timestamp | Use the import wall-clock ts; warn once on stderr ("X lines without ts; substituted with import time"). |
| Source file is in a non-UTF-8 encoding (e.g. latin-1) | `--encoding latin-1` flag honoured; default UTF-8 with `errors=replace`. |
| Source file is a `tar.gz` of many logs | Out of v0.17. User runs `tar xzf` first. Documented. |
| `--db` points to an existing chain-integrity DB | Allowed — imports get `is_imported=1`, chain fields NULL, do NOT advance `chain_pos`. Verifier skips them (same as `is_replay=1`). |
| `--db` doesn't exist | Created with the v0.5 schema + `is_imported` column. |
| Two imports of the same file to the same DB | No dedup. Duplicates go in. (Future: `--idempotent` via hash-of-line dedup, out of v0.17.) |
| Source line > 1 MB | Allowed up to 16 MB hard cap (SQLite TEXT practical limit). Lines over 16 MB rejected with line number in stderr. |
| Regex pattern has no `(?P<msg>…)` group | Reject with `--format regex: pattern must include named group 'msg'`. |
| Custom regex captures group named `record_hash` / `chain_pos` / `is_imported` | Reserved names — error on first parse with "reserved group name X". |

---

## 3. Functional requirements

| ID | Description |
|---|---|
| FR1 | `ulog import <input>… --db <out>` is the only entry point. Multiple inputs concatenated in order. |
| FR2 | `--format` accepts: `auto`, `jsonl`, `csv`, `nginx-combined`, `apache-combined`, `syslog`, `journald-json`, `raw`, `regex:<pattern>`. |
| FR3 | `auto` detects format from extension + first 100-line sniff. Detection result printed on stderr (`detected format: nginx-combined`). |
| FR4 | All 6 built-in parsers map source fields per Decision D1. |
| FR5 | Imported rows have `is_imported=1`, `chain_pos=0`, `record_hash=NULL`, `prev_hash=NULL`. |
| FR6 | `is_imported` column added by migration; chain verifier skips imported rows (same path as `is_replay=1`). |
| FR7 | Streaming reader — RSS does not scale with input size. Hard ceiling: 200 MB RSS for any input size. |
| FR8 | `.gz` and `.bz2` decoded transparently via stdlib. `.zst` decoded when `zstandard` is installed (opt-in `[import-zstd]` extra). |
| FR9 | `--strict` aborts on first parse error; default continues + final stderr summary. |
| FR10 | Viewer record list shows `imported` slate chip on `is_imported=1` rows. |
| FR11 | `--encoding <name>` overrides default UTF-8 (default uses `errors=replace`). |
| FR12 | `--source-tag <label>` adds a constant `context.import_source=<label>` to every imported record so multi-source imports stay distinguishable. |
| FR13 | Doc page `/docs/import/` covers all 6 formats, regex examples, the `is_imported` chain semantics, and the snapshot ↔ import round-trip. |

---

## 4. Non-functional

| ID | Description |
|---|---|
| NFR-PERF-70 | 100K nginx-combined lines import in ≤ 30 s on a 2026-spec laptop (writer batch=500). |
| NFR-PERF-71 | RSS ≤ 200 MB regardless of input size (streaming guarantee). |
| NFR-DEP-70 | Zero new mandatory deps. `[import-zstd]` is the only opt-in. |
| NFR-DOC-70 | `/docs/import/` page lives; CLI `--help` references it. |
| NFR-COMPAT-70 | Importing into an existing v0.5 chain DB does not break the chain (verifier sees imported rows as out-of-chain). |

---

## 5. Decisions

### D1 — Built-in parser field mappings

| Source | → ts | → level | → logger | → msg | → context |
|---|---|---|---|---|---|
| **jsonl** | `ts` | `level` | `logger` (or `service`) | `msg` (or `message`) | all other keys |
| **csv** | `ts` column | `level` column | `logger` column | `msg` column | header columns not in the canonical set |
| **nginx-combined** | `time_local` | bucket by `status` (5xx→ERROR, 4xx→WARNING, 3xx/2xx→INFO) | `nginx.access` | `"$method $path $status"` | `client_ip`, `bytes_sent`, `referer`, `user_agent`, `request_time` |
| **apache-combined** | `time` | same status-bucket | `apache.access` | `"$method $path $status"` | same as nginx + `request_protocol` |
| **syslog (3164+5424)** | `timestamp` | parsed `severity` (debug→DEBUG, info→INFO, warning→WARNING, error/critical→ERROR/CRITICAL) | `appname` (5424) or hostname-tag combo (3164) | message body | facility, hostname, msgid, structured-data (5424) |
| **journald-json** | `__REALTIME_TIMESTAMP` (µs → ISO) | `PRIORITY` (0–7 mapped to DEBUG/INFO/WARNING/ERROR/CRITICAL per the standard) | `_SYSTEMD_UNIT` (fallback `SYSLOG_IDENTIFIER`) | `MESSAGE` | every other `__` and `_` key kept verbatim |

**Why:** every source has a canonical "what's the message + when did it
happen + how bad" trio. The rest is metadata; dropping it would defeat
the import. Keeping it all in `context` JSON costs nothing (SQLite
JSON1 column), and the viewer's bound-field filter (`?bound=client_ip=...`)
makes it queryable.

### D2 — Stream vs. batch insert

**Streaming reader + batched inserts** (default batch size 500).
Streaming so RSS stays flat; batching so SQLite write throughput hits
~50K records/s (well above NFR-PERF-70). Same batching mechanism as
the existing `SQLHandler.batch_size` — extracted into a helper so the
import path doesn't duplicate code.

### D3 — Imported rows are out-of-chain (NOT a chain extension)

Two options were considered:

1. **A** — import rows ARE part of the chain (compute hash, link to
   prev_hash). Pro: single uniform view. Con: trust model breaks —
   the import provenance is unverifiable, mixing it into the chain
   makes the chain's verifiability lie.
2. **B** — import rows are out-of-chain (`chain_pos=0`,
   `record_hash=NULL`, `is_imported=1`). Pro: trust model preserved;
   imports clearly labelled in UI. Con: needs a column add.

**Chose B.** The chain's value is its forensic guarantee. Adding
imported records into it would silently invalidate that guarantee
for downstream consumers. The `is_imported` chip in the UI makes the
distinction visually obvious.

### D4 — Regex escape hatch reuses Python `re` (not PCRE / re2)

Python's stdlib `re` is the obvious choice — zero dep, well-known
syntax, named groups work. PCRE would require a binding (`regex` PyPI
package); re2 ditto. Trade-off accepted: no recursive patterns, no
fancy lookbehinds — adequate for log parsing.

### D5 — `is_imported` chip lives in record list, not detail view

The chip is on the **list row** (next to the level pill) because
that's where the user scans dozens of rows quickly and needs to know
"is this a record I wrote or one I imported?". The detail view shows
the same record fully; adding a redundant chip there clutters without
adding info. Tooltip on the list-row chip: "Imported via `ulog import`
on YYYY-MM-DD".

---

## 6. Open questions

- **Q1** : Should `--strict` parse errors include a copy-paste-able
  regex fragment of the line that failed, to help debug a regex
  format? Lean yes for `--format regex:…`; pure built-ins less
  useful.
- **Q2** : Does the `imported` chip need a colour-coded source
  badge (nginx blue, syslog amber, journald teal) when multiple
  imports happened? Lean no for v0.17; rely on
  `context.import_source` filter instead.
- **Q3** : Should imports get a synthetic `chain_pos` so they sort
  predictably in the viewer record list? Lean no — sort by `ts` ASC
  is already deterministic; `chain_pos=0` for all imports is the
  honest signal.

---

## 7. Implementation outline (informational)

**Epic candidate** : "v0.17 Log import (`ulog import`)" — 8 stories
estimated.

| Story | Topic |
|---|---|
| 17.1 | New `is_imported` column + migration helper + verifier update |
| 17.2 | Streaming reader (lines, encoding, compression) |
| 17.3 | Parser registry + 6 built-ins (jsonl, csv, nginx, apache, syslog, journald) |
| 17.4 | Regex escape hatch (named-group binding + validation) |
| 17.5 | `ulog import` CLI subcommand (auto-detect + dispatch) |
| 17.6 | Viewer record-list `imported` chip |
| 17.7 | Doc page `/docs/import/` |
| 17.8 | Edge-case tests (large lines, bad encoding, parser miss, `--strict`, round-trip) |

Suggested ordering : 17.1 → 17.2 → 17.3 → 17.4 → 17.5 → 17.6 → 17.7 → 17.8.

---

_End of PRD-v0.17._
