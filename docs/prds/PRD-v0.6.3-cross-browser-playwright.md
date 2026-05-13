---
docType: prd
project_name: ulog-python
version: 0.6.3
date: 2026-05-13
author: jojo8356
status: draft v1
parent_prd: PRD-v0.6-static-export.md
related_prd:
  - PRD-v0.6.2-tailwind-build-pipeline.md
---

# ULog v0.6.3 — Cross-browser Playwright matrix (patch)

> Adds a Playwright e2e suite that opens `ulog export-html` output
> in Chromium / Firefox / WebKit and asserts the integrity badge +
> record list paint correctly. Closes NFR-COMPAT-60 (Story 8.13 of
> PRD-v0.6). Also bundles Story 8.13's Lighthouse first-paint check.

---

## 0. 30-second pitch

The v0.6 static export was written with `tests/test_export_html.py`
covering 26 invariants — but every one of them is **server-side**
(HTML byte content, file paths, JSON shapes). None of them open
the export in an actual browser.

v0.6.3 ships the missing browser-side gate: a Playwright pytest
suite that:

1. Generates a fresh export into a tmp dir.
2. Serves it via `python -m http.server` for `--separate-data` mode.
3. Opens `index.html` in **headless Chromium, Firefox, AND WebKit**
   in sequence (one `pytest` parametrize run per browser).
4. Asserts: no console errors, integrity badge visible, paginated
   record list paints, click navigation works.
5. Runs a Lighthouse audit on Chromium with `Fast 3G` throttling →
   first-paint of `index.html` (1000 records) ≤ 1 s (NFR-PERF-61).

CI matrix runs the 3 browsers across Linux only (NFR-COMPAT-60
spec) on every PR touching `ulog/web/export/` or templates.

---

## 1. Vision

### 1.1 Why this exists

Three risks the Python-only test suite misses:

1. **CSS regressions across engines.** Tailwind output relies on
   modern selectors (`:has`, `:where`, container queries in v4).
   WebKit's history of dragging behind Chromium on these features
   means a working Chrome export can ship broken WebKit visuals.
2. **JS feature drift.** The `--inline-data` mode embeds JSON in
   `<script type="application/json">`. Parsing that on every
   browser is trivially well-supported, but the multi-track strip's
   vanilla JS (<50 LOC, Story 6.5) uses `Promise.all`,
   `matchMedia('(prefers-color-scheme: dark)')`, and
   `IntersectionObserver`. WebKit's `prefers-color-scheme` for
   `file://` URLs is famously inconsistent.
3. **Compliance auditors run weird browsers.** Some use
   Brave (Chromium-clone, OK), some use Safari (WebKit, our
   weakest tested surface), some run Firefox-ESR with old
   defaults. v0.6.3 makes the 3-engine support explicit.

### 1.2 What v0.6.3 isn't

- **Not a mobile-browser matrix.** iOS Safari / Chrome Android are
  out of scope. Playwright supports device emulation, but real
  device labs need vendor SaaS (BrowserStack) — out of scope.
- **Not a percy.io visual-diff gate.** Pixel-perfect rendering
  comparison is a future PRD (v0.6.5?). v0.6.3 asserts only that
  required content is *visible* via DOM checks.
- **Not a flaky-test-quarantine system.** If a browser is broken
  for legitimate reasons (e.g. WebKit 18.5 has a CSS bug), the test
  fails. We file an issue; we don't quarantine.

### 1.3 Target users

- **Release manager** (you) — needs a green CI badge before
  publishing GitHub Releases.
- **Camille** (carried, security analyst) — runs Safari at work.
  Wants confidence the bundle she opens renders.
- **Lin** (carried, regulated env) — corporate browser is locked
  to Firefox ESR. Same concern.

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | `tests/test_export_html_e2e.py` parametrizes over `["chromium", "firefox", "webkit"]` × `["--inline-data", "--separate-data"]` → 6 test variants per assertion | yes |
| SC2 | All variants pass in CI on every PR touching `ulog/web/export/` | yes |
| SC3 | First-paint of `index.html` (1000 records, `--separate-data` mode, `Fast 3G` throttling) ≤ 1 s on Chromium (NFR-PERF-61) | yes |
| SC4 | Zero JS console errors on page load across all 3 browsers | yes |
| SC5 | Integrity badge visible (`page.locator(".integrity-OK, .integrity-BROKEN, .integrity-missing").is_visible()`) on every page | yes |
| SC6 | Test wall time ≤ 5 min on GitHub Actions (3 browsers × 2 modes × ~3 assertions per test = manageable) | yes |
| SC7 | Browser cache shared between CI runs (saves 90 s of install per run) | yes |

---

## 2. Scope (v0.6.3)

### 2.1 In scope (~ 200 LOC test + CI matrix)

1. **`tests/test_export_html_e2e.py`** — new pytest file using the
   `pytest-playwright` plugin (already in `[dev]` via Story 1.1).
   Parametrizes `browser_name` over chromium / firefox / webkit.
   ~10 tests per browser, ~30 total.
2. **Fixture: served export** — `@pytest.fixture` that builds a
   sample export in a tmp dir and launches
   `python -m http.server -d <tmp> 0` (port 0 = random free).
3. **Fixture: file:// mode** — separate fixture that yields the
   tmp dir's `index.html` path (for `--inline-data` testing the
   double-click-open path).
4. **Assertions** per browser:
   - `page.goto(url)` succeeds.
   - `page.locator('h1').text_content()` contains the record count.
   - No console errors (`page.on('console', collect_errors)`).
   - Integrity badge visible.
   - Click a record row → detail page loads.
   - `page.on('dialog', ...)` to confirm XSS escape (Story 8.12
     re-asserted via real browser).
5. **Lighthouse audit** — `tests/test_export_html_lighthouse.py`
   using the `playwright-lighthouse` package (single browser:
   chromium). Throttling: `slow4g`. Asserts FCP ≤ 1 s.
6. **CI matrix** — `.github/workflows/ci.yml` adds a
   `playwright-cross-browser` job that runs on ubuntu-latest with:
   ```yaml
   - run: python -m playwright install --with-deps chromium firefox webkit
   - run: pytest tests/test_export_html_e2e.py \
            --browser chromium --browser firefox --browser webkit
   ```
7. **Browser cache** — `actions/cache@v4` keyed by `playwright`
   version + OS to skip the 90 s install when unchanged.
8. **Skip markers** — `@pytest.mark.skip_browser("webkit")`
   available for documented WebKit-specific issues if any
   surface.

### 2.2 Explicit non-goals

- **Mobile devices / iOS / Android** — out.
- **Visual diff regression (Percy / playwright-visual-regression)**
  — out. v0.6.5 PRD candidate.
- **Cross-OS browser matrix (Windows / macOS runners)** — out.
  GitHub Actions Linux runner with the 3 engines covers
  NFR-COMPAT-60 as written. Cross-OS adds runner cost without
  proportional reward.
- **CDN-loaded asset tests** — by v0.6.2 the CDN is gone; the
  export is fully self-contained.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| `pip install playwright` succeeds but `playwright install` 503s | Job fails with clear "browser binary download failed" message; retry-on-failure flag set. |
| WebKit fails on `:has()` CSS but Chrome passes | Test fails with browser name in the error; we file an issue. Story 8.13 doesn't auto-quarantine. |
| Lighthouse audit times out (Slow 3G + 1000 records is borderline) | Doubled timeout; first-2-runs advisory like Story 7.10's benchmark gate. |
| `file://` URL with `--separate-data` fails fetch() (expected) | Test asserts the failure mode is graceful (error message in page, not silent break). |
| Browser binary cache stale / corrupt | `--with-deps` re-installs idempotently; CI step `playwright install --force` available. |

---

## 3. Functional requirements

| ID | Description |
|---|---|
| FR1 | Playwright pytest plugin installed via `[dev]` extras (already there). |
| FR2 | Cross-browser parametrize covers chromium + firefox + webkit. |
| FR3 | Two-mode coverage: `--inline-data` (file://) AND `--separate-data` (http.server). |
| FR4 | Integrity badge visibility checked on every test variant. |
| FR5 | Console-error count asserted to be 0. |
| FR6 | Lighthouse audit asserts FCP ≤ 1 s for the 1000-record default scenario. |
| FR7 | CI matrix runs on every PR touching `ulog/web/export/` or `ulog/web/templates/`. |
| FR8 | Browser cache shared between CI runs via `actions/cache@v4`. |

---

## 4. Non-functional

| ID | Description |
|---|---|
| NFR-COMPAT-60 | All 3 browsers green on Linux for every release tag. |
| NFR-PERF-61 | First-paint ≤ 1 s @ Slow 3G, Chromium, 1000 records, `--separate-data`. |
| NFR-CI-60 | E2E job ≤ 5 min wall time. |

---

## 5. Decisions

### D1 — `pytest-playwright` (Microsoft) vs `mxschmitt/pytest-playwright`

Choose **`microsoft/playwright-pytest`** (the official Microsoft
plugin). Better long-term maintenance signal; `mxschmitt`'s plugin
is the original but Microsoft adopted it.

Source: <https://github.com/microsoft/playwright-pytest>

### D2 — `--browser` CLI flag vs `parametrize`

Choose **`--browser`** (the plugin's CLI flag, repeatable). One
test function runs across all 3 browsers without per-test
`@pytest.mark.parametrize`. Cleaner reports.

Reference: `pytest --browser chromium --browser firefox --browser
webkit` produces 3 results per test.

Source: <https://playwright.dev/python/docs/test-runners>

### D3 — Headless by default

Headless on. Headed mode (`--headed`) is opt-in via the same
plugin flag for local debugging. CI is always headless.

### D4 — Browser binary install — `--with-deps` flag

Use `python -m playwright install --with-deps` so the system
libraries Chromium/Firefox/WebKit need on Ubuntu are auto-installed
(otherwise WebKit silently fails to launch on minimal runners).

Source: <https://playwright.dev/python/docs/ci-intro>

### D5 — Lighthouse via `playwright-lighthouse` not raw `lighthouse-ci`

`playwright-lighthouse` runs inside the same browser session so we
don't double-launch Chromium. Single test process; bounded cost.

---

## 6. Operating manual

### Local dev

```bash
# One-time: install Playwright + the 3 browsers + system deps.
pip install ulog[dev]
python -m playwright install --with-deps chromium firefox webkit

# Run the suite locally.
pytest tests/test_export_html_e2e.py -v \
    --browser chromium --browser firefox --browser webkit

# Headed mode for debugging.
pytest tests/test_export_html_e2e.py --headed --slowmo 500 \
    --browser webkit -k "test_index_loads"

# Single test on a single browser (fastest dev loop).
pytest tests/test_export_html_e2e.py::test_index_loads \
    --browser chromium -v
```

### CI

Adding to `.github/workflows/ci.yml`:

```yaml
playwright-cross-browser:
  runs-on: ubuntu-latest
  needs: test
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - name: Cache Playwright browsers
      uses: actions/cache@v4
      id: playwright-cache
      with:
        path: ~/.cache/ms-playwright
        key: playwright-1.55-${{ runner.os }}
    - run: pip install -e ".[dev,storage,web,web-dev]"
    - run: python -m playwright install --with-deps chromium firefox webkit
      if: steps.playwright-cache.outputs.cache-hit != 'true'
    - run: python -m playwright install-deps
      if: steps.playwright-cache.outputs.cache-hit == 'true'
    - name: Run e2e
      run: |
        pytest tests/test_export_html_e2e.py -v \
            --browser chromium --browser firefox --browser webkit \
            --tracing=retain-on-failure
    - uses: actions/upload-artifact@v4
      if: failure()
      with:
        name: playwright-traces
        path: test-results/
```

Tracing on failure means every failed run uploads a Playwright
`.zip` trace you can replay in `playwright show-trace trace.zip`.

### Adding a new test

Pattern:

```python
def test_records_list_renders(page, served_export_url):
    """Runs across all 3 browsers via the plugin's parametrize."""
    page.goto(f"{served_export_url}/index.html")
    page.wait_for_selector("h1")
    assert "records" in page.text_content("h1").lower()
    assert page.locator(".integrity-missing, .integrity-OK, .integrity-BROKEN").is_visible()
```

Browser-specific skips:

```python
@pytest.mark.skip_browser("webkit")  # known WebKit bug X
def test_some_chromium_only_thing(page):
    ...
```

---

## 7. Open questions

- **Q1** : Should we add a smoke test for the **live viewer**
  (`ulog web --debug`) instead of just the static export? Lean yes
  (re-uses the same browsers) — could ship as a separate
  `test_live_viewer_e2e.py` file in v0.6.4.
- **Q2** : Visual-regression diffs (pixel-by-pixel screenshots vs
  a baseline) — useful for catching theme regressions but
  notoriously flaky. Defer to a v0.6.5 PRD if user asks.
- **Q3** : Should `playwright-lighthouse` results post a PR comment
  with the trend? Could be a `actions/github-script` follow-up.

---

_End of PRD-v0.6.3._
