---
docType: prd
project_name: ulog-python
version: 0.6.2
date: 2026-05-13
author: jojo8356
status: draft v1
parent_prd: PRD-v0.6-static-export.md
related_prd:
  - PRD-v0.8-modern-frontend-stack.md
---

# ULog v0.6.2 — Tailwind standalone CLI build pipeline (patch)

> Replaces the runtime `<script src="cdn.tailwindcss.com">` with a
> committed `tailwind.css` produced by Tailwind's standalone binary
> (no Node, no npm). Same build emits two themes (`ulog-light.css`,
> `ulog-dark.css`) consumed by the live viewer AND the static export
> (Story 8.1 of PRD-v0.6).

---

## 0. 30-second pitch

The live viewer currently loads Tailwind via the CDN `<script>` tag
in `base.html` — fine for dev, **broken offline** and **slow first
paint** in compliance/airgapped contexts. The static HTML export
(v0.6) ships a `_MINIMAL_CSS_FALLBACK` placeholder that's readable
but visually plain.

v0.6.2 ships the missing piece: a `make tailwind-build` target that:
1. Downloads Tailwind's **standalone CLI binary** (no Node, no npm,
   ~25 MB).
2. Scans `ulog/web/templates/ulog/*.html` for the classes actually used.
3. Emits `ulog/web/static/ulog/tailwind.css` purged to ~30-50 KB.
4. Emits two pre-built theme bundles (`ulog-light.css` /
   `ulog-dark.css`) consumed by the static export.

CI gate (`make tailwind-check`) fails the build if the committed CSS
is stale vs the templates.

---

## 1. Vision

### 1.1 Why this exists

Three operational pains the CDN script causes:

1. **Offline viewers don't paint.** Compliance auditors run
   `ulog web ./audit.sqlite` in an airgapped VM. The `<script>` tag
   hits the network and silently fails — every record appears as
   un-styled text. Bad first impression for a forensic tool.
2. **Static export is visually plain.** The v0.6 exporter
   currently inlines `_MINIMAL_CSS_FALLBACK` (~50 lines of plain CSS)
   because it can't rely on the CDN at recipient open-time. Theme
   toggles work but the visual identity is downgraded.
3. **Tailwind on CDN is dev-mode** — the official runtime script is
   deprecated and prints a warning. Users see "cdn.tailwindcss.com
   should not be used in production" in DevTools console.

### 1.2 What v0.6.2 isn't

- **Not a Node / npm dep.** The standalone binary is downloaded into
  `.tailwind/` (gitignored), not via `package.json`. Zero JS runtime
  in this repo.
- **Not a Tailwind config bonanza.** One `tailwind.config.js` (or
  `@theme` in CSS, depending on the v4 approach) that covers the
  classes already used in templates.
- **Not a watch-mode dev loop.** `make tailwind-build` is one-shot;
  `make tailwind-watch` (rebuild on template save) is an optional
  developer ergonomics target with no CI gate.
- **Not a v0.8 modern frontend stack** (Alpine.js / HTMX — PRD-v0.8
  ships those). v0.6.2 is purely the CSS bundle work.

### 1.3 Target users

- **Camille** (security analyst, carried) — airgapped VM analysis;
  needs the viewer to paint without network.
- **Marco** (solo dev, carried) — wants `ulog export-html` output
  to look the same as the live viewer when he ships a bundle.
- **NEW: release engineer** (you) — wants a `make` target so
  template changes don't drift from the committed CSS.

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | `make tailwind-build` produces `ulog/web/static/ulog/tailwind.css` ≤ 50 KB (gzipped < 15 KB), purged to only template-used classes | yes |
| SC2 | CDN `<script>` tag in `base.html` is removed; replaced by `<link rel="stylesheet" href="{% static 'ulog/tailwind.css' %}">` | yes |
| SC3 | Static export (`ulog export-html`) emits `static/ulog-light.css` + `static/ulog-dark.css` as files from the Tailwind build (NOT the `_MINIMAL_CSS_FALLBACK` placeholder) | yes |
| SC4 | `make tailwind-check` CI step fails if the committed CSS differs from the freshly-built one (>0 byte diff) | yes |
| SC5 | Zero new mandatory PyPI runtime deps. The binary is downloaded by the Makefile, not pulled by pip. | yes |
| SC6 | Build time on a 2026-spec laptop: ≤ 2 seconds for a clean build (Tailwind's standalone CLI is famously fast) | yes |
| SC7 | `tests/test_tailwind_freshness.py` asserts the committed CSS contains every class referenced by `{% include %}` / class= in templates (drift detector) | yes |

---

## 2. Scope (v0.6.2)

### 2.1 In scope (~ 250 LOC + Makefile + CI)

1. **Standalone binary fetch** — `make .tailwind/bin` downloads the
   Tailwind standalone CLI for the host platform from
   <https://github.com/tailwindlabs/tailwindcss/releases/latest/>.
   Platforms: `linux-x64`, `linux-arm64`, `macos-x64`, `macos-arm64`,
   `windows-x64`. Detected via `uname -sm`.
2. **Build target** — `make tailwind-build`:
   ```
   ./.tailwind/bin/tailwindcss \
       -i ulog/web/static/ulog/_tailwind-input.css \
       -o ulog/web/static/ulog/tailwind.css \
       --minify
   ```
3. **Light + dark theme bundles** — two extra builds with
   `@theme` blocks selecting the color palette per mode. Outputs:
   `ulog-light.css` (default), `ulog-dark.css` (with `:where(.dark *)`
   selectors expanded). Both consumed by the static exporter.
4. **Template scan config** — `tailwind.config.js` (or v4 CSS-first
   equivalent) with `content: ["ulog/web/templates/ulog/*.html"]` so
   the purger sees every Django class.
5. **base.html update** — remove the `<script src="cdn.tailwindcss
   .com">` block + the inline `tailwind.config = {...}` script.
   Replace by `{% static 'ulog/tailwind.css' %}` link.
6. **Static exporter integration** — `HtmlExporter._copy_static_assets`
   now copies the pre-built `ulog-{theme}.css` straight from
   `ulog/web/static/ulog/` instead of writing the fallback string.
   Fallback stays in place only as a last-resort (CSS file missing
   on disk).
7. **CI gate (`make tailwind-check`)** — re-runs the build into a
   temp file and `diff`s against the committed one. Non-zero diff =
   build fails with a clear "run `make tailwind-build` and commit"
   message.
8. **`.gitignore`** — `.tailwind/` (binary cache); keep `*.css` out
   of the ignore list so the committed bundle stays version-controlled.
9. **Doc page `/docs/contributing-build.md`** — covers
   `make tailwind-build`, `make tailwind-watch`, and how to add a
   new utility class to templates.

### 2.2 Explicit non-goals

- **Server-side rendering of multi-theme** — v0.6.2 ships exactly
  two pre-built bundles. Per-request theme selection lives in
  `base.html` via a `<html class="dark">` toggle at template-render
  time (existing behaviour). v0.8.x may revisit.
- **Custom theme support** (red / blue / corporate brand) — out of
  v0.6.2 scope. The two-theme contract is the minimum useful set.
- **Hot-reload of CSS in `ulog web --debug`** — out. The dev workflow
  is `make tailwind-watch &` in another terminal.
- **PostCSS / autoprefixer / nesting plugins** — Tailwind v4
  standalone covers what we need natively.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Host platform not in the 5 supported (e.g. FreeBSD) | Makefile errors with a clear message + link to manual download. |
| Tailwind release URL 503 / network down | `make tailwind-build` falls back to a vendored copy at `vendor/tailwindcss-bin-fallback` if present; else error + suggest `--without-tailwind` Makefile flag. |
| User runs `make tailwind-build` on a stale checkout (templates dir empty) | Tailwind emits a near-empty CSS (~1 KB). CI catches via SC1 (must contain ≥ N classes). |
| Committed CSS has trailing whitespace diff vs freshly-built | `make tailwind-check` uses `diff -q` (any byte difference). User runs `make tailwind-build` to normalise. |

---

## 3. Functional requirements

| ID | Description |
|---|---|
| FR1 | `make tailwind-build` produces `ulog/web/static/ulog/tailwind.css` from templates. |
| FR2 | Light and dark theme bundles produced as `ulog-light.css` + `ulog-dark.css`. |
| FR3 | `base.html` links the bundled CSS via `{% static %}`; CDN `<script>` removed. |
| FR4 | Static exporter consumes the bundled CSS (no longer inlines the fallback). |
| FR5 | `make tailwind-check` CI step fails on drift. |
| FR6 | Tailwind binary cached under `.tailwind/`; gitignored; auto-downloaded per platform. |
| FR7 | `tailwind.config.js` (or v4 `@theme`) lives at repo root; `content: ["ulog/web/templates/ulog/*.html"]`. |
| FR8 | Doc page `/docs/contributing-build.md` covers `tailwind-build` / `tailwind-watch`. |

---

## 4. Non-functional

| ID | Description |
|---|---|
| NFR-PERF-80 | Clean build ≤ 2 s; subsequent rebuilds (changed-template-only) ≤ 200 ms. |
| NFR-DEP-80 | Zero new mandatory PyPI deps. Binary is downloaded by `make`. |
| NFR-SIZE-80 | `tailwind.css` ≤ 50 KB; gzipped ≤ 15 KB. |
| NFR-OFFLINE-80 | Live viewer paints in an airgapped VM (no CDN reachable). |

---

## 5. Decisions

### D1 — Tailwind v4 vs v3 standalone

Choose **v4** (current stable as of 2026-05). v4's CSS-first
`@theme` system pairs naturally with our two-bundle approach (light
+ dark expressed as two `@theme` blocks). v4 also drops the
`tailwind.config.js` requirement — config can live entirely in CSS.

Source: <https://medium.com/@sir.raminyavari/theming-in-tailwind-css-v4-support-multiple-color-schemes-and-dark-mode-ba97aead5c14>

### D2 — Class strategy for dark mode

Use the **class-based strategy** (`darkMode: "class"`) — the live
viewer already toggles `<html class="dark">` via a localStorage
flag. The static export sets the class once at render time per
`--theme` flag. No JS toggle needed in the export.

Source: <https://tailwindcss.com/docs/dark-mode>

### D3 — Binary fetched per-build vs committed

**Fetched per-build (gitignored).** Committing a 25 MB binary
across 5 platforms bloats the repo. The Makefile reads `uname` and
downloads the right one. CI caches `.tailwind/` between runs.

### D4 — One config vs two for theme bundles

**One `_tailwind-input.css`** with `@theme { ... }` blocks scoped
by `:where(.dark *)`. Two separate `tailwindcss -i ... -o ...` runs
emit the two bundles (light = default, dark = with the class layer
flattened so the bundle works without the `.dark` toggle, useful
for the export where the theme is frozen at build time).

### D5 — Fallback CSS stays in `exporter.py`

The `_MINIMAL_CSS_FALLBACK` string survives v0.6.2 as a defence-in-
depth. If a user clones the repo, runs `ulog export-html` without
running `make tailwind-build` first, the export still works (just
visually plain). Future major (`v1.0`) may remove it.

---

## 6. Operating manual (for the release engineer)

Step-by-step for the first build:

```bash
# 1. One-time: pre-flight checks the host is supported.
make tailwind-doctor   # prints uname → expected binary URL

# 2. Build (downloads binary on first run, ~30 s; then ~2 s).
make tailwind-build

# 3. Verify the diff makes sense (new utility classes, etc.).
git diff ulog/web/static/ulog/

# 4. Commit the freshly-built CSS.
git add ulog/web/static/ulog/{tailwind,ulog-light,ulog-dark}.css
git commit -m "chore(css): rebuild Tailwind bundles"
```

For day-to-day dev:

```bash
# Watch mode — rebuilds on every template save in another terminal.
make tailwind-watch
```

In CI (`.github/workflows/ci.yml`), the `tailwind-check` job:

```yaml
tailwind-check:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Cache Tailwind binary
      uses: actions/cache@v4
      with:
        path: .tailwind
        key: tailwind-${{ runner.os }}-v4
    - name: Build and diff
      run: make tailwind-check
```

If the diff is non-zero, the step fails with:

```
Tailwind bundle is stale. Run `make tailwind-build` locally
and commit the result.
```

---

## 7. Open questions

- **Q1** : Should `make tailwind-build` also rebuild the static
  exporter's `_MINIMAL_CSS_FALLBACK` from the latest bundle (auto-
  embed a stripped subset)? Lean no — the fallback is intentionally
  minimal and stable.
- **Q2** : Do we need a third theme (high-contrast for accessibility)?
  Lean no for v0.6.2; revisit if user feedback asks.
- **Q3** : Should the watch-mode integrate with
  `django-browser-reload` so template + CSS edits trigger one
  unified reload? Could be a nice 30-line follow-up patch.

---

_End of PRD-v0.6.2._
