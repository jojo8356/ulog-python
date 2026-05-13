# v0.6 — Static HTML export (`ulog export-html`)

Render a stored log file to a self-contained directory of HTML pages.
Zippable, `file://`-openable, GitHub-Pages-hostable. Zero extra
PyPI dependency beyond the `[web]` extra you already have.

## Install

```bash
pip install ulog[web]      # Django adapter is already required.
```

## CLI

```bash
ulog export-html ./logs.sqlite --output /tmp/audit-2026-05
```

Flags :

| Flag | Default | Purpose |
|---|---|---|
| `--output PATH` | required | Destination directory. Must be empty unless `--force`. |
| `--filter "DSL"` | none | Same grammar as `ulog correlate` / `ulog bisect`. |
| `--include sections` | all | Comma-list: `level,sectors,authors,tests,incidents,multi-track,docs,integrity`. |
| `--theme light\|dark` | light | Pre-built CSS bundle selection. |
| `--inline-data` | heuristic | Embed records' JSON in `<script>` blocks (single-folder portable). |
| `--separate-data` | heuristic | Records live under `data/*.json` (smaller, but `fetch()` on `file://` may fail). |
| `--force` | off | Overwrite a non-empty output dir. |
| `--force-cap` | off | Bypass the 1M-record cap. |
| `--max-records N` | 1_000_000 | Refuse if record count exceeds N. |
| `--repo PATH` | auto | Git repo for AuthorIndex. |
| `--no-author-index` | off | Skip the v0.4 author indexer. |

**Heuristic for inline-vs-separate** : archives < 10K records default
to `--inline-data` (single-folder portable). ≥ 10K → `--separate-data`
(keeps individual page weight under control).

## Output layout

```
out/
  index.html              # records, paginated 1000/page
  page-2.html             # (and so on)
  r/
    1.html                # one HTML per record (full detail)
    2.html
    …
  incidents.html
  multi-track.html
  integrity.html          # frozen verify-state, full audit detail
  docs/                   # mirror of in-app /docs/
    quickstart.html
    …
  data/                   # only in --separate-data mode
    records-page-1.json
    …
  static/
    ulog-light.css        # bundled theme
    ulog-dark.css
  README.html             # how to open, fetch() caveat, metadata
```

Every internal link is **relative** — zip the directory, ship it,
unzip elsewhere, links still resolve.

## Integrity badge — frozen at export

The header pill on EVERY page reflects the state of
`<source-db>.verify_state.json` at the moment of export. Three
possible states:

- **OK** — green `Integrity ✓ verified up to #N`. The badge tooltip
  shows the original `last_check_ts` AND the `frozen_at` timestamp
  of when the export ran.
- **BROKEN** — red `Integrity ✗ BROKEN at #N`. The dedicated
  `integrity.html` page documents the broken-at point with detail.
  Auditors cannot miss it — the badge is on every page header.
- **never verified** — gray `Integrity: never verified`. Run `ulog
  verify <db>` before exporting to surface a real status.

## 4 worked examples

### A) Compliance audit bundle

A regulator asks for "everything ERROR-or-above in March 2026" as a
read-only HTML pack:

```bash
ulog verify ./logs.sqlite
ulog export-html ./logs.sqlite --output /tmp/audit-mar26 \
  --filter "level>=ERROR AND date>=2026-03-01 AND date<2026-04-01" \
  --include "level,incidents,integrity" \
  --theme light \
  --inline-data
```

The integrity badge is on every page. Send the zip — recipient opens
`index.html`, no install required.

### B) GitHub Release attachment

Daily snapshot for a release artifact:

```bash
ulog export-html ./prod.sqlite --output /tmp/snapshot \
  --filter "date>=-24h" \
  --theme dark
zip -r snapshot-2026-05-13.zip /tmp/snapshot
gh release create v1.2.3 snapshot-2026-05-13.zip --notes-file CHANGELOG.md
```

### C) GitHub Pages hosting

Push to a `gh-pages` branch :

```bash
ulog export-html ./logs.sqlite --output ./docs/logs \
  --separate-data --theme light
git add docs/logs && git commit -m "logs snapshot $(date +%F)"
git push origin main:gh-pages
```

`--separate-data` works fine over HTTPS — `fetch()` succeeds.

### D) E-mail attachment

Single-file portable shared via e-mail:

```bash
ulog export-html ./logs.sqlite --output /tmp/share \
  --filter "level=ERROR AND date>=-7d" \
  --inline-data --theme light
zip -r weekly-errors.zip /tmp/share
```

Recipient extracts, double-clicks `index.html` — opens directly
even on `file://` (no `fetch()` round-trip required).

## `fetch()` on `file://`

Browsers block `fetch()` for `file://` URLs as a security measure.
This affects `--separate-data` exports opened by double-clicking
`index.html`. Two workarounds:

1. **Easiest** — pick `--inline-data` (default for archives <10K
   records). Every record's JSON lives in the page itself.
2. **HTTPS or local server** — for larger archives, host the bundle
   under any HTTP server. The one-liner:

   ```bash
   python3 -m http.server -d /tmp/audit-mar26 8000
   ```

   then open `http://127.0.0.1:8000/`.

`README.html` at the export root documents this in plain English
for non-technical recipients.

## XSS hardening

Record messages and `context` values are HTML-escaped before
being rendered. A record with `msg='<script>alert(1)</script>'`
appears in the export as literal text — never executed.
Verified in `tests/test_export_html.py::test_xss_msg_is_escaped`.

## Performance

- **100K records** export in ≤ 30s on GitHub Actions ubuntu-latest
  (SC1).
- **Output size** : `--separate-data` ≤ 10 MB for 100K records,
  `--inline-data` ≤ 50 MB (SC3).
- Pagination at 1000 records/page keeps any single HTML page under
  ~5 MB.

## Limitations (v0.6)

- The multi-track view is **navigationally present** but not
  interactive in the static export — it points back to the live
  viewer. v0.7 may inline a pre-rendered SVG snapshot.
- The Incidents page in the export is read-only (live viewer
  required for new resolves / reopens).
- No syntax highlighting in the doc-page mirror; markdown is shown
  in `<pre>`. v0.8.1 ships Prism.js for the live viewer; the export
  variant follows.
