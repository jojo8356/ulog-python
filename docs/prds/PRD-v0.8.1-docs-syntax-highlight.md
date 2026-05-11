---
docType: prd
project_name: ulog-python
version: 0.8.1
date: 2026-05-11
author: jojo8356
status: draft v1
parent_prd: PRD-v0.8-modern-frontend-stack.md
depends_on: PRD-v0.4.2-docs-quality.md
benchmark: benchmarks/syntax-highlighter-2026.md
---

# ULog v0.8.1 — Docs code syntax highlighting

> Color every fenced code block in `/docs/<slug>/` (and `/diff/<sha>/`
> in a follow-up) according to its language hint. Lands as a child
> of v0.8's frontend modernization once Tailwind CLI + Alpine.js +
> HTMX are in place. Tooling selected by independent benchmark:
> **Prism.js** wins on bundle size, integration cost, and Tailwind
> dark-mode ergonomics.

## 0. Problem

Rendered doc pages currently emit `<pre><code class="lang-python">` blocks
with **zero color information**. Readers parse Python/bash/SQL/JSON by
eye on a monochrome slate background — discoverable but visually flat
compared to the rest of the ecosystem they come from (GitHub READMEs,
MDN, every modern doc site).

The `_markdown_to_html` renderer at `ulog/web/viewer/views.py:435`
intentionally avoids Pygments — that's an NFR-DEP-50 invariant
(`dependencies = []`). Architecture decision D4 doubled down on this
for the `/diff/<sha>/` view, declining syntax highlighting there for
the same reason.

The constraint forces highlighting to be client-side. That requires a
JS asset, which the current v0.5 stack (CDN-only) handles fine but
PRD-v0.8's Tailwind CLI / Alpine.js / HTMX rework is the natural
landing zone because:
- it introduces a JS bundle policy other than "no JS"
- the same CDN-vs-vendored decision (Decision D3 for Tailwind)
  applies identically to the highlighter
- a11y / dark-mode theme story is solved with Tailwind tokens already
  defined in v0.8

## 1. Vision

Plug a small client-side syntax highlighter into the existing
`/docs/<slug>/` pipeline. Recommendation backed by a written
benchmark — see [benchmarks/syntax-highlighter-2026.md](./benchmarks/syntax-highlighter-2026.md).

### 1.1 Highlighter choice — Prism.js

From the benchmark, weighted scoring across bundle / integration /
theming / quality / coverage / maintenance / WCAG:

| Tool | Score | Verdict |
|---|---:|---|
| **Prism.js** v1.30 | **4.80** | adopted |
| highlight.js v11.11 | 4.20 | viable but 5–8× heavier for our 4-language need |
| Shiki v1.x | 3.85 | disqualified (build-time only; conflicts with runtime markdown render) |
| starry-night v1.x | 2.65 | disqualified (React/Preact AST output; bundle overhead) |

See the [full comparison matrix and decision rationale](./benchmarks/syntax-highlighter-2026.md#3-decision-matrix).

### 1.2 Delivery profile

Mirrors the v0.8 stack's CDN-then-vendor approach:

| Phase | Asset delivery |
|---|---|
| v0.8.1 ship | CDN (`https://cdn.jsdelivr.net/npm/prismjs@1.30/`) — minimal integration risk, ride the CDN's edge cache. |
| v0.8.2 vendor (later) | Bundle into the Tailwind CLI build, served from `ulog/web/static/ulog/prism/`. Same trajectory as Tailwind (Decision D3 in architecture.md). |

Bundle scope at ship time:
- `prism-core.min.js` (~2 KB gz)
- 4 language components: `python`, `bash`, `sql`, `json` (~0.3-0.5 KB each)
- Theme: `prism-theme-vars` (CSS-custom-property theme) ~1 KB
- **Total: ~6–9 KB gzipped over the wire**

### 1.3 Theme — Tailwind-aware

Use `antfu/prism-theme-vars` so palette swaps happen via CSS variables.
Tokens map to existing Tailwind slate/blue/red/amber families already
used elsewhere in the UI:

```css
:root {
  --prism-foreground:      theme('colors.slate.900');
  --prism-background:      theme('colors.slate.100');
  --prism-comment:         theme('colors.slate.500');
  --prism-string:          theme('colors.emerald.700');
  --prism-keyword:         theme('colors.blue.700');
  --prism-number:          theme('colors.amber.700');
  --prism-function:        theme('colors.indigo.700');
}
:root.dark {
  --prism-foreground:      theme('colors.slate.100');
  --prism-background:      theme('colors.slate.800');
  --prism-comment:         theme('colors.slate.400');
  --prism-string:          theme('colors.emerald.300');
  --prism-keyword:         theme('colors.blue.300');
  --prism-number:          theme('colors.amber.300');
  --prism-function:        theme('colors.indigo.300');
}
```

The dark-mode swap reuses Tailwind's `darkMode: 'class'` selector — no
JS toggle code added; existing `<html class="dark">` flag drives the
whole theme.

### 1.4 Renderer change

One-line rename in `_markdown_to_html`:

```diff
- cls = f' class="lang-{code_lang}"' if code_lang else ""
+ cls = f' class="language-{code_lang}"' if code_lang else ""
```

Prism's selector convention is `.language-X` (HTML5 standard); the
current `.lang-X` prefix would silently not match. No other renderer
change needed — `<code class="language-python">…</code>` is exactly
what Prism's `Prism.highlightAll()` walks at `DOMContentLoaded`.

### 1.5 Conditional asset loading

Only inject the Prism `<script>` + `<link>` on pages that actually
contain code blocks:
- `/docs/*` (always — every page has code)
- `/diff/<sha>/` (in a v0.8.2 follow-up, gated by relaxing D4)
- **Not** on `/` records list or `/r/<id>/` detail (zero code blocks,
  zero benefit, would only cost a network request)

Implementation: template variable `{% block extra_head %}` populated
only in `docs_page.html` and `diff.html`.

## 2. Scope

### 2.1 In scope

1. **Vendor / CDN reference:** add Prism.js (`core` + 4 langs +
   `prism-theme-vars`) via `<script>` and `<link>` in
   `ulog/web/templates/ulog/docs_page.html`.
2. **Theme file:** ship `ulog/web/static/ulog/prism-tailwind.css`
   with the CSS-variable palette wired to Tailwind tokens (above).
   Verbatim if Tailwind tokens are already extracted in v0.8;
   otherwise inline hex values matching the slate/blue/emerald
   choices.
3. **Renderer rename:** `lang-X` → `language-X` in
   `ulog/web/viewer/views.py:460`.
4. **WCAG audit:** verify the chosen palette passes WCAG 2.1 AA
   contrast on both light and dark themes (Chrome a11y audit run
   on `/docs/api/` as the densest page). Adjust tokens if any
   token-on-bg pair fails.
5. **Tests** in `tests/test_web.py`:
   - `test_docs_code_block_uses_prism_class` — fetched HTML
     contains `<code class="language-python">`.
   - `test_docs_page_loads_prism_assets` — response body
     references the Prism `<script>` / `<link>`.
   - `test_records_list_does_not_load_prism` — non-docs pages
     don't pull in the Prism asset (bundle-budget regression
     guard).

### 2.2 Out of scope (deferred)

- **`/diff/<sha>/` syntax highlighting** — Decision D4 in
  architecture.md forbids it under NFR-DEP-50 today. This PRD does
  NOT relax that decision; a separate v0.8.2 PRD would have to
  revisit it once the JS-bundle policy is settled.
- **highlight.js or Shiki fallback** — single horse picked
  deliberately. If Prism stops shipping security updates, revisit
  via the trigger conditions in
  [the benchmark §5](./benchmarks/syntax-highlighter-2026.md#5-re-evaluation-trigger).
- **Server-side highlighting** — disqualified by NFR-DEP-50
  (Pygments forbidden). No stdlib alternative is ergonomic
  (would need per-language Python tokenizers + theme infra
  — see benchmark §1.1).
- **Copy-to-clipboard / line-number plugins** — Prism supports both
  via separate components. Defer to v0.8.3 doc polish; not required
  for the AA contrast / readability deliverable.
- **Markdown library swap** (`markdown-it-py` etc.) — orthogonal,
  tracked in PRD-v0.4.2 §2.2.

### 2.3 Dependency on prior PRDs

- **Hard dependency:** PRD-v0.8 must land first to provide the
  Tailwind CLI build pipeline that resolves `theme('colors....')`
  references in the CSS-variable file. Until then, this PRD stays
  in `draft v1` status.
- **Soft dependency:** PRD-v0.4.2 (docs quality) should land first
  for the TOC accordion — landing this PRD on top is cleaner if
  the doc pages already have their navigation refresh.

## 3. Acceptance

- **AC1** — Every `<code class="language-X">` block in `/docs/*`
  renders with Prism-token colors on Chromium and Firefox latest.
- **AC2** — Dark-mode toggle (`<html class="dark">`) swaps the
  palette via CSS variables only; no JavaScript re-render needed.
- **AC3** — All four target languages (`python`, `bash`, `sql`,
  `json`) render distinct color sets (keyword vs string vs comment
  vs number visually distinguishable).
- **AC4** — Records list (`/`) and detail view (`/r/<id>/`) do NOT
  fetch the Prism assets — verified via `curl /` and grep for
  `prism`.
- **AC5** — Chrome a11y audit on `/docs/api/` reports zero contrast
  failures on both light and dark themes.
- **AC6** — Total wire weight delta per `/docs/*` page is ≤ 10 KB
  gzipped (Prism core + 4 langs + theme).
- **AC7** — All 290+ existing tests stay green. Three new tests
  per §2.1.5 pass.
- **AC8** — QA reference screenshots `section-1-5` (test-integration
  doc) and `section-2-6` (author-filter doc) regenerated to show
  colored code blocks.

## 4. Non-functional

- **Bundle budget:** ≤ 10 KB gzipped client-side. Hard ceiling.
  If languages get added (e.g. `yaml`, `toml`) and the bundle creeps
  past 10 KB, revisit lazy-loading via Prism's Autoloader plugin.
- **Performance:** Prism's `highlightAll()` runs once on
  `DOMContentLoaded`. For our doc pages (typically 2-10 code blocks,
  ≤ 100 lines each), the work is sub-millisecond.
- **Zero new Python dep:** confirmed — the change is template +
  static asset + 1-line renderer rename. `pyproject.toml` untouched.
- **Backwards compat:** `lang-X` → `language-X` rename is a
  rendered-HTML change only; markdown source files are
  unaffected. Old bookmarks / browser caches refresh on next hit.
- **a11y:** WCAG 2.1 AA contrast for every token-on-bg pair
  (audit listed as AC5).

## 5. Risks / open questions

- **Prism upstream churn.** Prism's `language-bash` component has
  historically been less polished than its Python/JS counterparts
  (some heredoc edge cases). Mitigation: ship the highlighter, accept
  cosmetic glitches on bash; revisit if user feedback flags
  illegibility.
- **CDN availability dependency.** jsDelivr has 99.99% uptime in
  the last 12 months (jsdelivr.com/network), but the dev-time
  inspection UI is read-locally — a brief CDN outage degrades
  styling, not functionality (raw `<pre><code>` still renders).
  Acceptable.
- **CSS-variable theme vs Tailwind `theme()` resolution.** The
  `theme('colors.slate.900')` snippet in §1.3 only resolves under
  Tailwind CLI / PostCSS — i.e. the v0.8 pipeline. If this PRD ships
  on the v0.5 Tailwind CDN, fall back to inline hex literals.
  Both paths are documented in the implementation notes below.
- **No Pygments offline-build hack.** A tempting Plan B is to
  preprocess all `.md` files at install-time with Pygments and emit
  pre-colored HTML. Rejected: violates NFR-DEP-50 (Pygments in
  the install dep tree) and breaks the "live `.md` edit reflects in
  the UI" workflow important to doc-authoring iteration.

## 6. Implementation notes

### 6.1 Asset injection in `base.html` vs `docs_page.html`

Decision: inject via `{% block extra_head %}` defined in `base.html`
as empty, overridden in `docs_page.html` and `diff.html` (when D4
relaxes). Records / detail views don't override and pay zero cost.

### 6.2 Theme palette source (Decision G1)

- **If on v0.8 pipeline (Tailwind CLI):** use `theme('colors.slate.X')`
  references resolved at build time. Single source of truth — slate /
  blue / emerald / amber are already defined in `tailwind.config.js`.
- **If shipping before v0.8 (CDN Tailwind):** use inline hex values
  matching the slate / blue / emerald / amber Tailwind defaults
  (e.g. `slate-900 = #0f172a`, `slate-100 = #f1f5f9`, etc.) — checked
  in via the static CSS file. Migrate to `theme()` references when
  v0.8 lands.

### 6.3 Class rename — what about old bookmarks?

The class rename is purely internal — `lang-X` was never a public
contract (the renderer is in `views.py`, not a public Python API).
No deprecation period needed.

### 6.4 Why not auto-detect (highlight.js style)?

Highlight.js's auto-detection has historically misclassified short
snippets (e.g. a 3-line bash snippet detected as Perl). Our markdown
source always provides the fence language hint, so we can hard-set
the class and skip auto-detection entirely — fewer surprises, smaller
runtime cost.

### 6.5 Future Prism plugins worth considering (out of scope here)

- `line-numbers` (~1 KB) — adds gutter line numbers per `<pre>`.
- `command-line` (~1 KB) — styles shell snippets with a prompt prefix.
- `toolbar + copy-to-clipboard` (~2 KB total) — adds a "Copy" button.

Each is opt-in at template level; defer until users ask.

## 7. See also

- **Benchmark:** [benchmarks/syntax-highlighter-2026.md](./benchmarks/syntax-highlighter-2026.md) — full vendor comparison, weighted decision matrix, re-evaluation triggers.
- **Parent stack PRD:** [PRD-v0.8-modern-frontend-stack.md](./PRD-v0.8-modern-frontend-stack.md) — Tailwind CLI + Alpine.js + HTMX context.
- **Sibling docs PRD:** [PRD-v0.4.2-docs-quality.md](./PRD-v0.4.2-docs-quality.md) — TOC accordion + page refresh, soft-dependency.
- **Architecture invariants:** `_bmad-output/planning-artifacts/architecture.md` Decision D4 (no syntax highlighting on `/diff/<sha>/`) and NFR-DEP-50 (Pygments forbidden).
