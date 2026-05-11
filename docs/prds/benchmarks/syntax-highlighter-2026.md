---
docType: benchmark
project_name: ulog-python
date: 2026-05-11
author: jojo8356
related_prd: PRD-v0.8.1-docs-syntax-highlight.md
status: decision-ready
---

# Syntax highlighter selection — May 2026

> Comparative benchmark for picking a syntax highlighter for ULog's
> built-in `/docs/<slug>/` pages. Goal: highlight code blocks in
> the rendered markdown without breaking the project's
> **NFR-DEP-50** invariant (zero runtime Python dep beyond the
> existing `[storage]` / `[web]` extras), and stay aligned with
> the v0.8 frontend modernization stack (Tailwind CLI + Alpine.js
> + HTMX).

## 0. Constraints

| Constraint | Source | Impact |
|---|---|---|
| **No Pygments** | architecture.md / NFR-DEP-50 (Decision D4) | Disqualifies all `django-pygments*` packages and any pure-Python server-side highlighter that depends on Pygments |
| **Zero new runtime Python dep** | core PRD-v0.1 contract (`dependencies = []`) | Server-side option must be stdlib-only OR fall to client-side JS |
| **Renders at request-time** | Django view `_markdown_to_html` reads `.md` files on each `/docs/<slug>/` hit | Disqualifies build-time-only tools (Shiki SSG, starry-night for SSG pipelines) unless they expose a runtime API compatible with our model |
| **Languages used in current docs** | grep on `ulog/web/docs/*.md`: 10× bash, 9× python, 3× sql, 3× json | 4-language bundle is small for any modular highlighter |
| **Tailwind + dark mode** | architecture.md Decision D3 (Tailwind CDN through v0.5, CLI in v0.8) | Theme must support dark mode without a JS framework dep |
| **Alpine.js + HTMX coming in v0.8** | PRD-v0.8 | Highlighter must coexist with Alpine — no React/Vue lock-in |

## 1. Candidates surveyed

### 1.1 Server-side / Python

| Package | Pygments? | Maintained 2026 | Verdict |
|---|---|---|---|
| `django-pygments` | yes | abandoned (last release 2013) | ✗ disqualified (Pygments + dead) |
| `django-pygments-renderer` | yes | sporadic | ✗ disqualified (Pygments) |
| `django-extensions` `highlighting.py` | yes (Pygments) | active | ✗ disqualified (Pygments) |
| `django-highlightjs` | no — wraps highlight.js (client-side) | semi-active | ↪ delegates to client-side JS, see §1.2 |
| Custom stdlib tokenizer (`tokenize` module) | no | n/a | ✗ ergonomic dead-end: would need per-language Python tokenizers, no themes, no bash/SQL support |

**Conclusion §1.1:** No server-side option fits the constraints. All
roads lead to a **client-side JS highlighter**.

### 1.2 Client-side / JS

The four serious contenders in May 2026.

| Tool | Approach | Languages | Bundle (core+4 langs gz) | Themes | Maintained | npm weekly DL |
|---|---|---|---|---|---|---|
| **Prism.js** v1.30 | runtime tokenizer | 300+ via plugins | **~5-8 KB** | CSS theme files (~1 KB ea) + CSS-variable themes | active | ~5M |
| **highlight.js** v11.11 | runtime auto-detector | 192 | ~30-50 KB | bundled CSS themes | active | ~10M |
| **Shiki** v1.x | build-time (TextMate / WASM) | 200+ via VS Code grammars | 0 KB client (build-time) — but full bundle 1.2 MB gz at build | VS Code themes | active | ~5M |
| **starry-night** v1.x | runtime tokenizer (TextMate) | 600+ | 250 KB (common bundle) | None built-in; emits AST | active | low |

## 2. Detailed comparison

### 2.1 Bundle size (loaded at /docs/* render)

| Scenario | Prism | highlight.js | Shiki | starry-night |
|---|---|---|---|---|
| Core only | 2 KB | ~24 KB | — | — |
| + python, bash, sql, json | **~5-8 KB** | ~30-50 KB | 0 KB (pre-rendered HTML in markup) | 250 KB common, or ~12-20 KB if manually picking 4 langs |
| + theme (default dark) | +1 KB | +3-5 KB | included in inline styles | none built-in |
| **Total over the wire per page** | **~6-9 KB** | ~35-55 KB | 0 KB (but every code block is pre-styled HTML — adds ~30% to .html size) | ~13-21 KB (custom build) |

**Winner:** Prism.js (5–8× smaller than highlight.js on a like-for-like
runtime install).

### 2.2 Render speed

From cross-published benchmarks (pkgpulse 2026 / chsm.dev 2025):

| Tool | Relative speed | Notes |
|---|---|---|
| Prism.js | 1.0x (baseline, fastest) | Hand-written tokenizers per language |
| highlight.js | 0.5x | Auto-detect adds overhead |
| Shiki | 0.14x (~7× slower than Prism) | TextMate regex engines, accurate but heavy |
| starry-night | ~0.3x | Similar TextMate cost minus the WASM layer |

For our case (a few KB of code per page, highlighted once on load),
all four are imperceptible. Speed is **not** the deciding axis — bundle
size, theming, and ergonomics are.

### 2.3 Theming and dark mode

| Tool | Dark mode story | Tailwind compatibility |
|---|---|---|
| **Prism.js** | Multiple official themes (`prism-tomorrow.css`, `prism-okaidia.css`, etc.) **+** community CSS-variable theme (`antfu/prism-theme-vars`) that maps to `prefers-color-scheme` or any custom selector | ✅ Native — CSS variables drop into `:root` and `.dark` selectors used by Tailwind's `darkMode: 'class'` |
| **highlight.js** | Many bundled themes — must swap stylesheets (e.g. `github.css` ↔ `github-dark.css`) via media query or JS toggle | ✅ Works with media query; less elegant for class-based dark mode |
| **Shiki** | Built-in support for two themes side by side (`{light, dark}` in config). Pre-rendered HTML carries both as inline `<style>` data | ⚠ Requires re-rendering markdown at build time on theme swap |
| **starry-night** | No themes shipped. User maps token classes to CSS manually. | ⚠ Manual work — DIY theme |

**Winner:** Prism.js with `prism-theme-vars`. Tailwind's
`darkMode: 'class'` flips a CSS class on `<html>`; the Prism theme
variables resolve through that same class. Zero JS toggle code.

### 2.4 Class-name convention compatibility

ULog's `_markdown_to_html` currently emits:
```html
<pre class="bg-slate-100 dark:bg-slate-800 rounded p-3 overflow-x-auto text-sm">
  <code class="lang-python">...</code>
</pre>
```

| Tool | Class expected | Action needed |
|---|---|---|
| Prism.js | `class="language-python"` | Rename `lang-X` → `language-X` in the renderer (1-line change) |
| highlight.js | `class="language-python"` OR `class="python"` | Same rename, or none if we use the bare-language form |
| Shiki | n/a (build-time inlines styles) | Refactor markdown render pipeline — major change |
| starry-night | n/a (returns AST, caller maps to classes) | Bigger refactor |

**Winner:** Prism / highlight.js — tiny rename, no pipeline overhaul.

### 2.5 Integration cost

| Tool | Steps to integrate |
|---|---|
| **Prism.js** | (1) Add CDN `<script>` + `<link>` to `base.html`. (2) Rename `lang-X` → `language-X` in `_markdown_to_html`. (3) Optional: `Prism.highlightAll()` is auto-called on `DOMContentLoaded` — nothing else needed. |
| **highlight.js** | Same shape, but ship `hljs.highlightAll()` call in an `<script>`. Larger CSS asset. |
| **Shiki** | Add a Python `subprocess` call to a Node process — or ship `shiki-py` (immature bindings as of 2026-05) — **violates zero-build invariant.** Major refactor of `_markdown_to_html`. |
| **starry-night** | Same Node-side problem. Or pull in `@wooorm/starry-night` via npm + bundler in the v0.8 frontend pipeline — viable only after PRD-v0.8 lands. |

**Winner:** Prism.js — 5 lines of template + 1-line renderer rename.

### 2.6 Accessibility (WCAG)

All four can be made WCAG 2.1 AA compliant via theme choice. Prism's
default themes have **mixed** contrast (some fail AA for comment
tokens on light backgrounds). The recommendation in
`maxchadwick.xyz/blog/syntax-highlighting-and-color-contrast-accessibility`
is to start from `prism-coy` (light) and `prism-tomorrow` (dark) and
verify with the Chrome a11y audit.

No automatic disqualifier — but the theme picked needs an a11y
audit step listed as an AC of the implementing PRD.

### 2.7 License

| Tool | License | Compatible with ULog (MIT) |
|---|---|---|
| Prism.js | MIT | ✅ |
| highlight.js | BSD-3-Clause | ✅ |
| Shiki | MIT | ✅ |
| starry-night | MIT | ✅ |

No license risk on any candidate.

## 3. Decision matrix

Weighted score (1 = worst, 5 = best). Weights reflect ULog's
priorities: small bundle / minimal integration / theming for a
dev-time inspection UI.

| Criterion | Weight | Prism.js | highlight.js | Shiki | starry-night |
|---|---:|---:|---:|---:|---:|
| Bundle size | 25% | 5 | 3 | 5 (build-time, 0 client) | 3 |
| Integration cost | 25% | 5 | 5 | 1 (needs Node build step) | 1 |
| Theming / Tailwind dark mode | 15% | 5 | 4 | 4 (build-time both themes) | 1 |
| Render quality | 10% | 4 | 4 | 5 (VS Code grammars) | 5 |
| Language coverage (need: 4) | 10% | 5 | 5 | 5 | 5 |
| Maintenance / popularity | 10% | 5 | 5 | 5 | 3 |
| WCAG-ready themes | 5% | 4 | 4 | 5 | 2 |
| **Weighted total** | | **4.80** | **4.20** | **3.85** | **2.65** |

## 4. Recommendation

**Adopt Prism.js v1.30 (latest stable, May 2026).**

Concrete implementation profile:
- **Delivery:** CDN via jsDelivr (`https://cdn.jsdelivr.net/npm/prismjs@1.30/`) through v0.5; vendor into static assets when v0.8's Tailwind CLI pipeline lands — same trajectory as Tailwind (Decision D3 in architecture.md).
- **Bundle:** core + `prism-python`, `prism-bash`, `prism-sql`, `prism-json` components only. ~6-9 KB gzipped total over the wire.
- **Theme:** `prism-theme-vars` (CSS-custom-property theme), with palettes derived from Tailwind slate/blue tokens to match the rest of the viewer. `darkMode: 'class'` selector wired to the existing `<html class="dark">` swap.
- **Renderer change:** rename `class="lang-X"` to `class="language-X"` in
  `_markdown_to_html` (`ulog/web/viewer/views.py:460`). One-line diff.
- **Template change:** in `base.html`, conditional include of Prism's
  `<script>` and `<link rel="stylesheet">` — only on `/docs/*` and
  `/diff/*` pages (NOT on the records list, which has no code blocks).

Rejected alternatives:
- **highlight.js** — viable, but 5–8× larger bundle for the same 4-language need. No reason to pick the heavier option when our requirements fit Prism's sweet spot.
- **Shiki** — disqualified by the runtime-render constraint. Would require either a Node sidecar or vendoring shiki-py (immature bindings). Comes back into scope **only** if v0.7's test-execution-stack ships a Node-based build step (currently not planned).
- **starry-night** — designed for React/Preact virtual-DOM trees. Forcing it into Django HTML output is a stylistic mismatch and adds bundle weight for no quality gain over Prism at our scale.

## 5. Re-evaluation trigger

Revisit this benchmark **if** any of the following becomes true:

1. The docs gain a code-heavy section (>20 distinct languages, or
   code blocks growing past ~50 KB per page) — Shiki's render
   quality may then justify its build-time cost.
2. v0.8 ships a Node-based build pipeline anyway (currently the
   PRD-v0.8 explicit decision is no Node — Tailwind CLI standalone
   binary, Alpine.js + HTMX via CDN). If that flips, Shiki becomes
   viable.
3. Prism.js stops shipping security updates for >12 months. As of
   May 2026 Prism is actively maintained (last release < 60 days
   ago) — no concern.

## 6. References

External reading consulted:
- [Prism.js homepage + plugin catalog](https://prismjs.com/)
- [highlight.js homepage + WCAG-passing stylesheets](https://highlightjs.org/)
- [Shiki guide + bundle/theme docs](https://shiki.style/guide/)
- [starry-night repo (wooorm/starry-night)](https://github.com/wooorm/starry-night)
- [PkgPulse: Shiki vs Prism vs highlight.js 2026 comparison](https://www.pkgpulse.com/blog/shiki-vs-prismjs-vs-highlightjs-syntax-highlighting-2026)
- [chsm.dev: Comparing web code highlighters (Jan 2025)](https://chsm.dev/blog/2025/01/08/comparing-web-code-highlighters)
- [npm-compare: prismjs / highlight.js / shiki / react-syntax-highlighter](https://npm-compare.com/highlight.js,prismjs,react-syntax-highlighter,shiki)
- [antfu/prism-theme-vars (CSS variable Prism theme)](https://github.com/antfu/prism-theme-vars)
- [maxchadwick.xyz: Syntax highlighting and color contrast accessibility](https://maxchadwick.xyz/blog/syntax-highlighting-and-color-contrast-accessibility)
- [django-highlightjs (PyPI)](https://pypi.org/project/django-highlightjs/)

Internal:
- `_bmad-output/planning-artifacts/architecture.md` §Storage Architecture (Decision D4), §Pattern examples (lazy imports, `dependencies = []`)
- `docs/prds/PRD-v0.5-forensic-archive.md` (defines NFR-DEP-50)
- `docs/prds/PRD-v0.8-modern-frontend-stack.md` (defines the Tailwind CLI / Alpine.js / HTMX context for v0.8)
- `ulog/web/viewer/views.py:435-510` (current `_markdown_to_html` renderer)
- `ulog/web/docs/*.md` (4 languages used: python, bash, sql, json)
