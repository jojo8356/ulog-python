---
docType: prd
project_name: ulog-python
version: 0.6.0
date: 2026-05-05
author: jojo8356
status: draft v1
parent_prd: PRD-v0.5-forensic-archive.md
---

# ULog v0.6 — Static HTML export

> The Django viewer (`ulog web`) is great for live triage but requires
> Python + a running server. Teams that need **archival reports per
> release**, **GitHub Release attachments**, **compliance dossiers**, or
> **stakeholder-shareable post-mortems** want the same content as a
> single-folder static HTML bundle. v0.6 adds `ulog export-html` — a
> snapshot of the log archive, openable in any modern browser, no
> runtime, no network.

---

## 0. The 30-second pitch

`ulog web` is a triage tool — opens an archive, lets you slice it
interactively. That covers the engineer's workflow but not these:

1. **Compliance auditor** wants a frozen report attached to a SOC 2 /
   GDPR audit. Cannot install Python. Needs evidence as a file.
2. **Tech lead** wants to attach an incident summary to a GitHub
   Release so customers and downstream consumers can read it directly
   on the release page.
3. **DevRel / customer-success** wants to embed a per-version
   "what changed in production logs" report in marketing comms.

`ulog export-html ./logs.sqlite --output ./report-v0.5.0/` produces a
self-contained directory: `index.html` + record-detail pages + an
incidents page + the multi-track strip frozen at export time + the
integrity badge result frozen at export time. Zip it, attach it to a
release, host it on GitHub Pages, e-mail it. No `pip`, no `python`,
no Django on the consumer side.

The implementation reuses the v0.2 / v0.3 / v0.4 / v0.5 Django
templates via `render_to_string()` in standalone Django mode (no
server), so visual cohesion with the live viewer is automatic — every
template improvement to the live viewer flows to the static export
without duplication.

---

## 1. Vision

### 1.1 Why this exists

After v0.5 the archive is queryable, replayable, and verifiable, but
it remains live-server-only for human consumption. Three concrete
gaps:

1. **Distribution to non-Python audiences.** Customers, auditors, and
   exec stakeholders cannot install ulog. Today the only export paths
   are the raw `.sqlite` file (unreadable without ulog) or copy-pasted
   screenshots (not searchable). Both fail at scale.
2. **Versioned snapshots.** A release-tagged report (`bugs-v0.5.0.html`,
   `bugs-v0.5.1.html`, …) provides a chronology that the live viewer
   cannot — the live viewer always shows "now". Postmortem work
   benefits from frozen-at-the-time evidence.
3. **Long-term archival.** A 7-year compliance retention policy on
   `.sqlite` files presupposes 7-year ulog backward compatibility. A
   static HTML bundle with inlined CSS is browser-readable for as long
   as HTML4+CSS2 stays a thing — practically forever.

### 1.2 What v0.6 isn't

- **Not a replacement for the live viewer.** The viewer keeps its place
  for active triage. Export is for archival / distribution.
- **Not a SaaS dashboard.** Output is local files; the consumer opens
  them with `file://`.
- **Not a real-time export.** It's a frozen snapshot. Re-export to
  refresh.
- **Not a custom report builder.** Uses the existing viewer's templates
  and adapter contract — no new template language, no new data shape.
- **Not a PDF generator.** PDF is v0.8 (deferred). A static HTML can
  be printed-to-PDF by the user's browser if they want.

### 1.3 Target users (carried + new)

| Persona | Role | v0.6 use case |
|---|---|---|
| **Erika** (carried, v0.5) | Compliance officer | Generates `audit-2026-Q2.html` from the v0.5 archive, attaches it to a SOC 2 evidence packet. The integrity badge embedded in the export is what auditors verify. |
| **Johan** (carried, v0.4/v0.5) | Tech lead, 5-person team | Monthly postmortem distributed as `incidents-2026-04.html`. Stakeholders open it in a browser, no setup. |
| **Sara** (carried, v0.5) | Library developer | Attaches `release-v2.4.0-bugs.html` to her library's GitHub Release so consumers see what production patterns were observed. |
| **Frieda** (NEW) | DevRel / marketing lead | Embeds the static HTML in a customer-facing release-notes blog (via `iframe` or copy-paste). Static = SEO-indexable. |
| **Marco** (carried) | Solo dev | Hosts `~/incidents/` on GitHub Pages — public-facing transparency for his side projects. |

### 1.4 Success criteria

| SC | Description | Measurement |
|---|---|---|
| **SC1** | Export of a 100K-record archive completes in **≤ 30 s** | `pytest-benchmark` median 5 runs, GitHub Actions `ubuntu-latest`, CPython 3.12, NVMe SSD. Fixture in `tests/bench_export_html.py`. |
| **SC2** | Output is **self-contained** (CSS + minimal JS inlined), opens correctly with `file://` URL on Chrome, Firefox, Safari (latest stable) | Playwright check on each browser: `index.html` renders without console errors. |
| **SC3** | Output total size ≤ **10 MB** for 100K records (data NOT inlined — separate `data.json`) OR ≤ **50 MB** with data inlined | `du -sh report/` post-export, asserted in CI. |
| **SC4** | **Zero PyPI runtime dep added.** Django stays in `[web]` extra. `pyproject.toml dependencies = []` unchanged. | Same regression gate as SC4 in v0.5 (`grep '^dependencies' pyproject.toml \| grep -q '\[\]'`). |
| **SC5** | **Templates not duplicated.** The export reuses every Django template the live viewer uses. | Static analysis: `find ulog/web/templates -name '*.html' \| xargs grep -l 'ulog'` returns the same set used by both viewer and exporter. |
| **SC6** | **First adopter ships an exported report within 30 days of v0.6 tag.** | qlnes (carried from v0.5 SC6a) attaches `release-bugs.html` to its v2.x GitHub release. |

---

## 2. Scope (v0.6 — static HTML export only; other v0.6 items per PRD-v0.5 §7 covered by separate PRDs)

### 2.1 In scope

#### 2.1.1 CLI subcommand `ulog export-html`

```bash
ulog export-html <input>
    --output <dir>
    [--filter <dsl>]                    # reuse the v0.5 correlate filter DSL
    [--include level,sectors,authors,tests,incidents,multi-track,docs]
    [--theme light|dark]
    [--inline-data | --separate-data]   # default: --separate-data
    [--force]                           # overwrite non-empty output dir
    [--max-records <N>]                 # safety cap; default 1_000_000
```

Subcommand of the consolidated `ulog` binary (per PRD-v0.5 Decision C1
which lands in v0.5). For users still on v0.4 (pre-consolidation),
`ulog-export-html` is exposed as a transitional alias for one minor
version then removed in v0.7.

#### 2.1.2 Output directory layout

```
report-v0.5.0/
├── index.html                # main record list (paginated; 1000/page default)
├── page-2.html, page-3.html, …
├── r/
│   ├── 1.html                # one detail page per record (or per visible record under filter)
│   ├── 142.html
│   └── …
├── incidents.html            # ulog-incidents view, frozen at export time
├── multi-track.html          # 4-axis SVG strip, frozen at export time
├── integrity.html            # ulog-verify result frozen at export time
├── docs/                     # mirrored snapshots of /docs/<slug>/ pages
│   ├── quickstart.html
│   ├── storage.html
│   └── …
├── data/                     # only when --separate-data
│   ├── records.json          # paginated; one file per page-of-records
│   └── stats.json            # aggregate counts (level/sector/author/incident)
└── static/
    ├── ulog.css              # inlined Tailwind subset (post-D3 CLI build)
    └── ulog.js               # ~50 LOC vanilla JS for client-side filter UI
```

#### 2.1.3 Filter, scope, theme

- `--filter` accepts the same DSL parsed by `ulog correlate` (Decision
  C5). Records that don't match are excluded from the export entirely
  — the report is the snapshot of the filtered slice.
- `--include` controls which sections are emitted. Default: all.
  Excluding `multi-track` skips the SVG generation; excluding `docs`
  skips mirroring the in-app docs pages.
- `--theme` light vs dark — frozen at export time (no runtime toggle
  in the static export).

#### 2.1.4 Inlining policy

- `--inline-data` (off by default): records' JSON payload is embedded
  in `<script type="application/json">` blocks inside each HTML page.
  Trade-off: no separate `data/` directory, no `fetch()` calls, opens
  with pure `file://`. Cost: file size grows linearly.
- `--separate-data` (default): records data lives in `data/*.json`
  and is loaded via `fetch()` from the HTML pages. Smaller files but
  some browsers refuse `fetch()` on `file://` URLs (Chromium with
  `--allow-file-access-from-files` or served via a static server).
- Trade-off documented in the doc page (FR139). Default to
  `--separate-data` for any archive ≥ 10K records (heuristic: skip
  fetch issues for small reports).

#### 2.1.5 Pagination & cap

- Index pagination: 1000 records per page by default. Configurable via
  `--records-per-page`.
- `--max-records 1_000_000` is a safety cap. Refuse to export above
  the cap unless `--force` is passed (refuses with a clear message
  pointing at the live viewer for huge archives).

#### 2.1.6 Frozen integrity & multi-track

- The integrity badge state at export time is captured. If the chain is
  BROKEN at export, the badge is rendered as ✗ in EVERY page header of
  the export — auditors can't miss it.
- The multi-track SVG is generated server-side (per Decision D1 from
  v0.5) and emitted as inline `<svg>` markup. No JS dependency at
  render time.

#### 2.1.7 Reuse of viewer templates

- The exporter is a thin orchestrator that:
  1. Configures Django in standalone mode (no server, just template
     loading): `django.setup()` with minimal `settings`.
  2. For each page kind, calls `render_to_string(template_name, context)`
     and writes the output to disk.
  3. Replaces dynamic asset URLs (`/static/...`) with relative paths
     inside the output directory.
- No new templates ship. Every visual element reuses the viewer's
  existing `base.html`, `list.html`, `detail.html`, `multi_track.html`,
  `docs_page.html` from PRDs v0.2 / v0.3 / v0.4 / v0.5.

### 2.2 Explicit non-goals (deferred to v0.7+)

- **PDF export.** v0.8 — uses headless Chromium (`playwright`) to
  print HTML to PDF. v0.6 leaves PDF as a user-side concern (their
  browser's print-to-PDF works on the static HTML).
- **Streaming HTML for million-record archives.** v0.7 — needs page-
  level memory pressure analysis. v0.6 caps at 1M records.
- **Live re-export (file watch).** v0.6 is one-shot. A later version
  may add `--watch` for dev-loop iteration.
- **Custom user templates.** v0.6 emits the viewer's templates. A v0.8+
  feature could allow `--template-dir` for orgs that want branded
  reports.
- **Authentication on the static output.** Anyone with the file can
  read it. Compliance use cases requiring access control should ship
  the file via secure channels — not a v0.6 concern.
- **Search index generation** (Lunr.js, ElasticLunr). Static
  client-side search would be valuable but adds JS bundle size; v0.7
  candidate if asked.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| **Empty archive** (0 records matching filter) | Still produce a valid `index.html` with a clear "No records match" empty state. Integrity badge still shown. Tested via `tests/test_export_empty.py`. |
| **Archive with chain corruption** detected by integrity check at export | The export proceeds. Every page header carries `Integrity ✗ broken at #N` in red. The exported `integrity.html` shows the broken-at point. Auditors must see this. |
| **Output directory exists and is non-empty** | Refuse with non-zero exit unless `--force` passed. Without `--force`, a clear message: `output dir not empty; use --force to overwrite or --output <other>`. |
| **Output directory cannot be created** (permission, disk full) | Fail fast at startup with a clear `OSError`-derived message. No partial state. |
| **Filter DSL parse error** | Fail fast before any output is written. Same error format as `ulog correlate`'s DSL errors. |
| **Records contain HTML / control characters** | All log content is HTML-escaped at template render time (Django's autoescape). Tested via injection-style records (`<script>alert(1)</script>` as `msg`). |
| **Path traversal in record fields** (e.g. file=`../../etc/passwd`) | The `file` field is rendered as text only — never used as an output path. The exporter writes only to paths it constructs from sanitized record IDs. |
| **`--max-records` cap exceeded** | Refuse with non-zero exit. Message: `archive has N records (cap: M); use --max-records or --filter`. |
| **Browser doesn't support `fetch()` on `file://`** (default `--separate-data` path) | Doc page recommends `--inline-data` for small archives or `python -m http.server` for large ones. Both options documented. |
| **Multi-track strip on a 0-bucket window** | Renders `(no data)` placeholder per the live viewer's contract (PRD-v0.5 §2.1.6). |

---

## 3. Functional requirements

### 3.1 CLI surface

| FR | Description | Persona |
|---|---|---|
| **FR130** | `ulog export-html <input> --output <dir>` is the canonical entry point, exposed as a subcommand of the consolidated `ulog` binary (post-Decision C1 from v0.5). | Erika, Johan |
| **FR131** | `--filter <dsl>` accepts the v0.5 `correlate`/`bisect` filter DSL grammar (Decision C5). Records not matching the filter are excluded from the export. Parse errors fail fast before any output is written. | Johan |
| **FR132** | `--include` accepts a comma-separated list of section names (`level`, `sectors`, `authors`, `tests`, `incidents`, `multi-track`, `docs`). Default: all. Excluded sections do not appear in the export navigation. | Frieda |
| **FR133** | `--theme {light,dark}` selects a pre-built CSS bundle. Frozen at export time — no runtime toggle in the static output. | Marco, Frieda |
| **FR134** | `--inline-data` / `--separate-data` (default) toggle whether record JSON is embedded in HTML or written to `data/*.json`. Default chosen heuristically based on record count if neither flag is passed (see FR135). | Erika |
| **FR135** | `--force` is required to overwrite a non-empty output directory. Without it, refuse with a clear message and non-zero exit. | All |
| **FR136** | `--max-records N` (default 1_000_000) caps exports. Above the cap, refuse unless `--force-cap` is also passed (separate flag — `--force` alone does not bypass). | Marco (safety) |

### 3.2 Output structure

| FR | Description | Persona |
|---|---|---|
| **FR137** | Output layout is the directory tree specified in §2.1.2. Asset paths are relative; no absolute URLs. The export is portable: zipping the directory and unzipping elsewhere preserves all links. | All |
| **FR138** | Every page extends the existing `ulog/web/templates/ulog/base.html` template (post any v0.5 modifications). The integrity badge in the header shows the FROZEN-AT-EXPORT state. | Sara, Erika |
| **FR139** | A doc-style README is emitted at the output root (`README.html`) explaining: how to open the report, the `--inline-data` vs `--separate-data` trade-off, "if `fetch()` is blocked use `python -m http.server`". | All consumers |

### 3.3 Reuse of viewer machinery

| FR | Description | Persona |
|---|---|---|
| **FR140** | The exporter configures Django in standalone mode (`django.setup()` with minimal `settings`) and uses `django.template.loader.render_to_string()` to render every page. NO new Django templates ship. | Sara |
| **FR141** | The exporter reuses the v0.5 adapter contract (`Adapter.query()`, `Adapter.multi_track()`) for data fetching. Storage-agnostic by construction (SQLite + JSONL + CSV inputs all work). | Lin |
| **FR142** | When invoked on a `.jsonl` or `.csv` input, the exporter optionally builds the v0.4 `AuthorIndex` if a repo path is provided via `--repo`. Author column hidden if no repo / if `--no-author-index`. | Lin |

### 3.4 Integrity & immutability surfacing

| FR | Description | Persona |
|---|---|---|
| **FR143** | `integrity.html` is a dedicated page reproducing the `ulog verify` output at export time: chain length, span, broken-at point if any, last-check timestamp. | Erika |
| **FR144** | If chain is BROKEN at export, EVERY page in the export header carries the red `Integrity ✗ broken at #N` badge. No silent omission. | Erika, Sara |

### 3.5 Documentation

| FR | Description | Persona |
|---|---|---|
| **FR145** | New `/docs/static-export.html` page (also rendered as `ulog/web/docs/static-export.md`) covering: install (no extra needed beyond `[web]`), CLI usage, the inline-vs-separate-data trade-off, GitHub Pages hosting recipe, GitHub Release attachment recipe. | Frieda |

---

## 4. Non-functional requirements

| NFR | Budget + measurement |
|---|---|
| **NFR-PERF-60** | Export of 100K records in **≤ 30 s** on GitHub Actions `ubuntu-latest` CPython 3.12 NVMe SSD. `pytest-benchmark` median 5 runs. (= SC1.) |
| **NFR-PERF-61** | First-paint of the exported `index.html` (1000 records on the first page, default `--separate-data`) ≤ **1 s** on Chromium with simulated `Fast 3G` throttling. Playwright Lighthouse audit. |
| **NFR-SIZE-60** | Total export size ≤ **10 MB** for 100K records, `--separate-data` mode. ≤ **50 MB** for `--inline-data`. (= SC3.) |
| **NFR-DEP-60** | `pyproject.toml dependencies = []` unchanged. Django stays in `[web]` extra. (= SC4.) |
| **NFR-COMPAT-60** | Exported HTML opens correctly with `file://` URL on Chrome ≥ 100, Firefox ≥ 100, Safari ≥ 16 (latest stable each). Verified by Playwright. |
| **NFR-PORT-60** | Linux + macOS + Windows. Output paths use `pathlib.Path` and `.as_posix()` for relative URLs. |
| **NFR-SEC-60** | All log content HTML-escaped at template render (Django autoescape). Injection-style records (e.g. `msg='<script>alert(1)</script>'`) tested for non-rendering. |
| **NFR-SEC-61** | The `file` and `logger` fields of records are rendered as text only — never used to construct output paths. The only path-manipulation input is the user-supplied `--output` directory. |
| **NFR-DOC-60** | Doc page `static-export.md` shipped with: 30-second pitch, CLI reference, 4 worked examples (compliance audit attachment, GitHub Release attachment, GitHub Pages hosting, e-mail distribution). (= FR145.) |
| **NFR-REL-60** | Empty archive case (0 records) produces a valid HTML with empty-state placeholder. Tested. |
| **NFR-REL-61** | Chain-broken archive still produces a complete export, with the broken state surfaced on every page header. Tested. |

---

## 5. API surface (sketch)

### 5.1 CLI

```bash
# Basic — full archive, default theme, default sections
$ ulog export-html ./logs.sqlite --output ./report-v0.5.0/

# Filtered to last 30 days of errors, dark theme
$ ulog export-html ./logs.sqlite \
    --output ./errors-jan.html-bundle/ \
    --filter "level=ERROR AND date>-30d" \
    --theme dark

# Compliance audit packet — inline data (single-folder portable)
$ ulog export-html ./prod.sqlite \
    --output ./audit-2026Q2/ \
    --inline-data \
    --filter "immutable=1" \
    --include incidents,integrity

# GitHub Release attachment
$ ulog export-html ./logs-v0.5.0.sqlite --output ./release-v0.5.0-bugs/
$ zip -r release-v0.5.0-bugs.zip release-v0.5.0-bugs/
$ gh release upload v0.5.0 release-v0.5.0-bugs.zip
```

### 5.2 Programmatic API (Python)

For users who want to integrate export into custom tooling:

```python
from ulog.web.export import HtmlExporter, ExportOptions

exporter = HtmlExporter(
    input_path="./logs.sqlite",
    options=ExportOptions(
        output_dir="./report/",
        filter="level=ERROR",
        theme="light",
        inline_data=False,
        include={"records", "incidents", "multi-track"},
    ),
)
exporter.run()
```

The programmatic API delegates to the same machinery as the CLI. CI
pipelines that need fine-grained control (e.g. emitting on a per-test
basis) use the Python API; everyone else uses the CLI.

---

## 6. Worked examples

### 6.1 Compliance audit — attach evidence to a SOC 2 packet

```bash
$ ulog export-html ./prod-2026Q2.sqlite \
    --output ./audit-evidence/ \
    --filter "immutable=1 AND date>2026-04-01" \
    --inline-data \
    --include incidents,integrity \
    --theme light

$ zip -r audit-2026Q2-evidence.zip audit-evidence/
$ openssl dgst -sha256 audit-2026Q2-evidence.zip > audit-2026Q2-evidence.zip.sha256
```

The auditor receives:
1. The zipped HTML bundle.
2. The sha256 hash file.
3. Instructions: open `index.html`, verify the integrity badge shows ✓.

The integrity badge embedded in every page is what makes the static
export legitimate audit evidence — combined with the v0.5 hash chain,
the auditor can verify the chain offline if they have the original
SQLite (which the exporter optionally bundles via `--include source`).

### 6.2 GitHub Release attachment for transparency

```bash
$ ulog export-html ./prod.sqlite \
    --output ./release-v2.4.0-bugs/ \
    --filter "level=ERROR AND ts>=v2.3.0_release_ts AND ts<v2.4.0_release_ts" \
    --theme dark

$ zip -r release-v2.4.0-bugs.zip release-v2.4.0-bugs/
$ gh release upload v2.4.0 release-v2.4.0-bugs.zip
```

Customers reading the v2.4.0 release notes click "what bugs did we
hit?" and download the bundle. They unzip and open `index.html`. They
see the chronology, the resolved/unresolved state of each, and the
post-mortems via the incidents page.

### 6.3 GitHub Pages monthly report

```bash
$ ulog export-html ./prod.sqlite \
    --output ./docs/report-2026-04/ \
    --filter "date>=2026-04-01 AND date<2026-05-01" \
    --theme light \
    --separate-data

$ git add docs/report-2026-04/
$ git commit -m "ops: April 2026 incident report"
$ git push
```

GitHub Pages serves `docs/report-2026-04/index.html` — the report is
public, indexable, linkable. Stakeholders bookmark the URL.

### 6.4 E-mail to a non-technical stakeholder

```bash
$ ulog export-html ./prod.sqlite \
    --output ./monthly/ \
    --filter "level=ERROR AND date>-30d" \
    --inline-data \
    --include incidents,multi-track \
    --max-records 500

$ tar -czf monthly.tar.gz monthly/
$ mail -s "April incidents — see attached" exec@example.com < monthly.tar.gz
```

Stakeholder receives a small bundle (under 1 MB at this size). No
Python required, no server, no link rot in 6 months.

---

## 7. Roadmap continuation

### v0.7
- **Streaming HTML** for million-record archives (page-level chunking
  during render, not load-all-then-render).
- **Multi-DB federation** (`ulog export-html --inputs db1,db2`) for
  cross-service report aggregation.
- Removal of the `ulog-export-html` transitional alias from v0.6.

### v0.8
- **PDF export** via headless Chromium (`playwright`). Optional `[pdf]`
  extra. Same templates render to both HTML and PDF.
- **`--watch` mode** for dev-loop iteration on report styling.

### v0.9
- **Custom template overrides** (`--template-dir`) for orgs branding
  reports.
- **Static client-side search** (Lunr.js bundled, opt-in).

### v1.0
- Static export API frozen + `Stable` PyPI classifier.

---

## 8. Open questions

1. **Default `--inline-data` vs `--separate-data` heuristic.**
   Current proposal: separate by default for archives ≥ 10K records,
   inline otherwise. Alternative: always separate, force user to opt
   in to inline. **Recommend: heuristic** — it Just Works for the
   most common cases.

2. **`--include source` to bundle the original SQLite alongside HTML.**
   Useful for audit (auditor can re-verify chain) but doubles the
   bundle size and tempts users to think the SQLite is the report
   (it's not — the HTML is). **Recommend: support, but off by
   default.** Document the trade-off.

3. **Theme generation for the static export.** The live viewer uses
   Tailwind CDN today; PRD-v0.2 §3.5 plans a Tailwind standalone CLI
   build (deferred, currently v0.6 territory per Decision D3 from
   v0.5 architecture). Static export requires the standalone-built
   CSS — should we accelerate D3 to land BEFORE FR130, or ship the
   exporter with an inline Tailwind subset hand-curated?
   **Recommend: accelerate D3** — it unblocks both this PRD and the
   pre-existing v0.6 plan, and Tailwind standalone CLI is a small,
   one-time setup cost.

4. **Versioning the export format.** A future change to the template
   layout could break consumers who built tooling on top of the
   exported HTML structure. Should we emit an `export-format-version`
   field in the README and bump it on breaking changes? **Recommend:
   yes** — `<meta name="ulog-export-format" content="1.0">` in every
   page header, similar to `ulog-version` field.

5. **Search engine indexing.** Default `<meta name="robots">` should
   be `noindex,nofollow` to prevent accidental public indexing of
   internal logs. Users who WANT indexing (e.g. customer-facing
   GitHub Pages reports) opt in via `--allow-indexing`.
   **Recommend: noindex,nofollow by default**, opt-in flag for
   public reports. Safety-first.

6. **CI-friendly mode.** A `--ci` flag could disable progress
   indicators, force `--force` (overwrite is desired in CI), and emit
   a one-line summary on stderr. Useful but minor; the user can
   already pipe `2>/dev/null` and pass `--force`. **Recommend: defer
   to v0.7** unless requested.

---

## 9. Definition of Done — v0.6

- [ ] **CLI**
  - [ ] `ulog/_cli/cmd_export_html.py` registered as `ulog export-html`
        (FR130).
  - [ ] All flags from §2.1.1 parsed and validated at the argparse
        boundary (FR131-136, NFR-SEC-60 for path inputs).
  - [ ] Transitional alias `ulog-export-html` (removed in v0.7).

- [ ] **Output generation**
  - [ ] `ulog/web/export/exporter.py` — orchestrator + `HtmlExporter`
        class (FR140, FR141, §5.2 programmatic API).
  - [ ] Output layout per §2.1.2 (FR137).
  - [ ] Pagination for index pages (FR137).
  - [ ] `--inline-data` and `--separate-data` paths both implemented
        and tested (FR134).
  - [ ] `README.html` at output root (FR139).

- [ ] **Reuse of viewer machinery**
  - [ ] Standalone Django setup module (`ulog/web/export/standalone.py`)
        — no server, only template loading.
  - [ ] Zero new templates: every output renders an existing
        `ulog/web/templates/ulog/*.html` (FR140, SC5).
  - [ ] v0.4 `AuthorIndex` integration (FR142).

- [ ] **Integrity surfacing**
  - [ ] `integrity.html` page (FR143).
  - [ ] Per-page header badge respects frozen-at-export state (FR144).

- [ ] **Doc**
  - [ ] `ulog/web/docs/static-export.md` page with 4 worked examples
        (FR145, NFR-DOC-60).
  - [ ] README of repo updated to mention the export path.

- [ ] **Tests**
  - [ ] `tests/test_export_basic.py` — happy path, 100-record fixture.
  - [ ] `tests/test_export_filters.py` — DSL-filtered export.
  - [ ] `tests/test_export_empty.py` — empty archive (NFR-REL-60).
  - [ ] `tests/test_export_broken_chain.py` — corrupted chain
        (NFR-REL-61).
  - [ ] `tests/test_export_xss.py` — injection records HTML-escaped
        (NFR-SEC-60).
  - [ ] `tests/test_export_path_traversal.py` — record fields cannot
        escape output dir (NFR-SEC-61).
  - [ ] `tests/test_export_max_records.py` — cap enforcement (FR136).
  - [ ] `tests/bench_export_html.py` — SC1 perf gate.
  - [ ] Playwright `tests/e2e/test_export_browsers.py` — opens in
        Chromium / Firefox / WebKit, no console errors (SC2,
        NFR-COMPAT-60, NFR-PERF-61).

- [ ] **Type & quality**
  - [ ] `mypy --strict` green on `ulog/web/export/` (NFR-COMPAT-50
        carried).
  - [ ] `pyproject.toml dependencies = []` regression CI gate
        (carried from v0.5 SC4).

- [ ] **Cross-cutting (depends on Decision D3)**
  - [ ] D3 (Tailwind standalone CLI build) shipped — see Open
        Question 3. If D3 lands in this release, FR133 ships with
        bundled CSS; otherwise FR133 ships with an inline Tailwind
        subset and a known-to-be-imperfect visual coverage.

- [ ] **Release**
  - [ ] Tag `v0.6.0` + push.
  - [ ] First adopter ships an exported report within 30 days
        (SC6 — qlnes attaches `release-bugs.html` to its v2.x release).
  - [ ] Cross-link from v0.5's `ulog incidents --report --since`
        markdown output to "or use `ulog export-html` for a richer
        archival format".

---

## 10. Reference

- **Predecessor PRDs** : [v0.5](./PRD-v0.5-forensic-archive.md)
  (the chain integrity and incidents this exporter surfaces),
  [v0.4](./PRD-v0.4-commit-author-filter.md) (AuthorIndex reuse),
  [v0.3](./PRD-v0.3-test-integration.md) (Tests sidebar mirroring),
  [v0.2](./PRD-v0.2-storage-and-ui.md) (template foundation,
  Tailwind CDN baseline), [v0.1](./PRD-v0.1-core.md).
- **Architecture decisions reused** : Decision C1 (CLI consolidation
  — `ulog export-html` is a subcommand of the consolidated `ulog`
  binary), Decision C5 (`--filter` reuses the correlate filter DSL),
  Decision D1 (multi-track aggregation reused for the frozen SVG
  strip), Decision D2 (integrity badge sidecar JSON consumed at
  export time), Decision D3 (Tailwind standalone CLI build —
  open question 3).
- **Open architecture follow-up** : whether D3's standalone Tailwind
  build is on the v0.6 critical path or can be inlined as an interim
  workaround. To be resolved at sprint planning for v0.6.
