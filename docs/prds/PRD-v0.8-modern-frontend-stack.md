---
docType: prd
project_name: ulog-python
version: 0.8.0
date: 2026-05-11
author: jojo8356
status: draft v1
parent_prd: PRD-v0.6-static-export.md
supersedes_story: 8-1-tailwind-standalone-cli-build-pipeline
---

# ULog v0.8 — Modern frontend stack (Tailwind CLI + Alpine.js + HTMX)

> **Pitch :** remplacer le `cdn.tailwindcss.com` runtime + les scripts
> JS inline ad-hoc par un trio production-ready : **Tailwind CLI**
> standalone (CSS optimisé < 10 KB), **Alpine.js** (réactif sans
> bundler, 15 KB) et **HTMX** (partial swaps server-driven, 14 KB).
> Total stack JS ≤ 30 KB, zéro bundler, zéro npm. Pas de framework
> SPA. Le viewer reste "HTML-first" mais devient maintenable et
> production-grade.

---

## 0. The 30-second pitch

ULog ship le viewer Django avec :
- **Tailwind via CDN** → script JS lourd qui compile le CSS dans le browser, slow first paint, pas prod-ready.
- **JS inline ad-hoc** → 4 closures IIFE séparées (lang switcher, debug bar progress, section toggles, qa checklist state) sans modèle mental commun, dur à étendre.
- **Filter UX = full page reload** → click un test name dans la sidebar = la page entière recharge, scroll position perdu, pas snappy.

Cette PRD remplace les 3 par le combo **Tailwind CLI + Alpine.js + HTMX** — le pattern "HTML-first" qui domine les boîtes Django en 2026 (cf. HackSoft, Pegasus, TestDriven). Total stack JS ≤ 30 KB, zéro bundler, zéro npm, pas de framework SPA. ROI immédiat sur la maintenabilité.

---

## 1. Vision

### 1.1 Why this exists

Le viewer ULog est passé de v0.1 (page minimal) à v0.4 (multi-features avec sidebar Tests/Authors, panneaux détail, page QA debug-only avec switcher i18n). Le JS inline a grossi en parallèle, sans pattern unifié. Trois pains pratiques :

1. **Tailwind CDN est dev-only**, son JS compile le CSS au runtime → ralentit chaque page load. La doc Tailwind elle-même recommande de migrer en production.
2. **Le JS inline est dur à étendre** — chaque nouvelle fonctionnalité UI (toggle, modal, dropdown) demande un nouveau bloc IIFE qui réinvente l'event-binding, le state, le localStorage sync.
3. **Les transitions de page sont brutales** — full reload sur chaque click filter perd le contexte visuel (scroll, sélection, zoom).

Le combo **Tailwind CLI + Alpine.js + HTMX** est devenu le stack de référence pour les apps Django modernes qui veulent éviter le piège SPA tout en gardant une UX réactive. Articles 2026 (HackSoft, Pegasus, Medium, DEV.to) montrent qu'avec ce trio :

- **CSS final** < 10 KB (Tailwind CLI scan + purge des classes utilisées)
- **JS total** ≤ 30 KB (Alpine 15 KB + HTMX 14 KB)
- **Aucun build step lourd** — Tailwind CLI binaire 32 MB standalone, Alpine + HTMX = `<script src=...>` direct
- **Aucun npm/Vite/Webpack** — pas de `node_modules` 200 MB, pas de pipeline CI à maintenir

### 1.2 What v0.8 isn't

- **PAS un framework SPA** — pas de React/Vue/Svelte. Le viewer reste server-rendered.
- **PAS un re-architecture du backend** — Django views, urls, models intacts.
- **PAS une refonte design** — visuels Tailwind identiques, juste pré-compilés.
- **PAS un ajout de bundler** — tout est `<script>` direct ou binaire standalone.
- **PAS une migration vers TypeScript** — Alpine.js + HTMX en JS standard.

### 1.3 Target users

Personae existantes (carriées) + impact :

- **Solo dev (Johan)** — bénéficie du faster page load, de la maintenabilité du JS, et du UX plus snappy en filtre.
- **CI maintainer** — bénéficie du build CSS reproductible (sortie identique en CI vs local).
- **OSS contributor potentiel** — barrière d'entrée au refactor frontend abaissée (Alpine.js a une API trivial à apprendre, pas besoin de webpack config).

### 1.4 Success criteria

| SC | Description |
|---|---|
| SC1 | Page `/` (no filter) first-paint en `< 200 ms` sur la demo DB 43 K (vs ~600 ms avec CDN). |
| SC2 | CSS shipped au browser ≤ 15 KB (vs ~3 MB du CDN script). |
| SC3 | Total JS shipped ≤ 50 KB (Alpine 15 + HTMX 14 + ulog inline ≤ 5 + django-browser-reload existant ≤ 5 KB). |
| SC4 | Click sur un test dans la sidebar → swap partiel de la records table en `< 100 ms`, scroll position préservé. |
| SC5 | Tous les inline scripts existants (lang switcher, debug bar progress, section toggles, checklist state) refactorés en patterns Alpine.js cohérents. |
| SC6 | Suite tests verte (279/279), no regression sur le rendu HTML actuel. |
| SC7 | `dependencies = []` invariant préservé. Tailwind CLI = binaire dev, Alpine + HTMX = `<script src=...>` CDN ou static asset (vendoré dans le repo). |

---

## 2. Scope

### 2.1 In scope — les 3 stacks

#### 2.1.1 Tailwind CSS standalone CLI (FR-FE-1)

Remplace le `<script src="https://cdn.tailwindcss.com">` actuel par un **build CSS pré-compilé**.

**Setup** :

```bash
# Download du binaire standalone (32 MB, zéro npm)
curl -L "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64" \
  -o vendor/tailwindcss
chmod +x vendor/tailwindcss

# Build CSS — scan tous les .html sous templates/, génère output.css
./vendor/tailwindcss -i ulog/web/static/input.css -o ulog/web/static/output.css --minify
```

`input.css` minimal :
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`tailwind.config.js` :
```js
module.exports = {
  content: ["./ulog/web/templates/**/*.html"],
  darkMode: "class",
  theme: { extend: {} },
};
```

**Intégration dev** : un Make target `make watch-css` relance Tailwind CLI en mode `--watch` quand un `.html` change.

**Intégration prod (sdist)** : commit `output.css` dans le repo (généré + commit) ; le viewer le sert via static files.

**Removal** : suppression du `<script src="cdn.tailwindcss.com">` + `tailwind.config = {...}` inline dans `base.html`.

#### 2.1.2 Alpine.js (FR-FE-2)

Remplace les 4 closures IIFE inline par des composants Alpine déclaratifs.

**Inclusion** :
```html
<script defer src="{% static 'ulog/alpine.min.js' %}"></script>
```

(Vendoré, ~15 KB minified.)

**Refactors prévus** :
- **Lang switcher EN/FR** dans `qa.html` → `x-data="{ lang: ... }"`, `@click="lang = 'en'"`.
- **Debug bar QA progress** dans `base.html` → `x-data="{ done: 0, total: 0 }"`, `x-init="loadFromStorage()"`.
- **Section toggles** dans `qa.html` → `x-data="{ allChecked: false }"`, `@change="toggleSection(...)"`.
- **Theme toggle** (dark/light) dans `base.html` → `x-data="{ dark: ... }"`, `@click="dark = !dark"`.
- **Tutorial overlay** (FR38) dans `base.html` → `x-data="{ shown: false }"`, `x-show="shown"`.

#### 2.1.3 HTMX (FR-FE-3)

Remplace les full-reloads sur filter clicks par des **partial swaps**.

**Inclusion** :
```html
<script defer src="{% static 'ulog/htmx.min.js' %}"></script>
```

(Vendoré, ~14 KB minified.)

**Patterns prévus** :
- **Click test name** (sidebar Tests) → swap uniquement la records table + l'URL devient `?test_id=...` via `hx-push-url="true"`.
- **Click record row** (table) → modal HTMX au lieu du redirect `/r/<id>/` (optionnel — le redirect actuel est déjà OK).
- **Submit form filter** (sidebar Levels/Sectors/Files multi-select) → swap records table sans recharger sidebar.
- **Pagination** (Prev/Next) → swap records table.

**Backend changes** : views.py détecte `request.headers.get("HX-Request") == "true"` et retourne soit la page complète, soit un partial template (genre `_records_table.html`).

### 2.2 Explicit non-goals

| Non-goal | Pourquoi |
|---|---|
| TypeScript | Alpine + HTMX = JS plain, simple à comprendre. TS pour 30 lignes de code = overhead. |
| Bundler (Vite, esbuild) | Le pitch HTMX-first est "no build step". Tailwind CLI suffit pour le CSS. |
| React/Vue/Svelte | Overkill pour un dev tool. SPA = perte de la simplicité Django views. |
| WebSockets | django-browser-reload utilise déjà SSE pour le dev reload. Pas de cas d'usage prod. |
| Service Worker / PWA | Pas un cas d'usage (viewer local, pas mobile). |
| Skin/theme system custom | `darkMode: "class"` Tailwind + theme toggle Alpine = enough. |

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| **Tailwind CLI binaire absent en CI** | Fallback : commit `output.css` dans le repo. CI ne rebuilds pas, sert le commit-time CSS. |
| **Alpine.js pas chargé** (network fail) | Le `<div x-data="..">` reste dans son état initial ; pas de crash, juste pas de réactivité. UX dégradée acceptable. |
| **HTMX pas chargé** (network fail) | Les `<a hx-get="...">` se comportent comme des liens normaux (HTML standard) — full reload reprend. Graceful degradation. |
| **`hx-push-url="true"` casse l'historique** | Forward/back browser navigue entre swaps. Tester explicitement. |
| **Conflict Alpine + HTMX** | Les 2 utilisent des attributes différents (`x-` vs `hx-`) et n'interfèrent pas. Pattern documenté. |
| **Tailwind CLI rebuild en watch lors d'un edit `.py`** | Pas affecté — Tailwind CLI watch les `.html`, Django autoreload watch les `.py`. Indépendants. |

---

## 3. Functional requirements

### 3.1 Tailwind CSS CLI

| FR | Description |
|---|---|
| FR200 | `vendor/tailwindcss` binaire standalone Linux/macOS/Windows checked-in (.gitattributes binary). |
| FR201 | `tailwind.config.js` à la racine, `content: ["./ulog/web/templates/**/*.html"]`. |
| FR202 | `ulog/web/static/input.css` 3-line file (`@tailwind base/components/utilities;`). |
| FR203 | `ulog/web/static/output.css` généré + committed (post-build). |
| FR204 | `Makefile` target `make watch-css` lance Tailwind CLI en `--watch`. |
| FR205 | `base.html` link `<link rel="stylesheet" href="{% static 'ulog/output.css' %}">` ; suppression du CDN script. |
| FR206 | CI step (Epic 7 release gate) regénère `output.css` et fail si diff vs commit. |

### 3.2 Alpine.js

| FR | Description |
|---|---|
| FR210 | `ulog/web/static/alpine.min.js` vendoré (v3.x stable, ≤ 15 KB minified). |
| FR211 | `base.html` `<script defer src="{% static 'ulog/alpine.min.js' %}"></script>`. |
| FR212 | Lang switcher refactoré en `x-data="{ lang: localStorage.qaLang || 'fr' }"`. |
| FR213 | Debug bar progress refactoré en `x-data="{ done: 0, total: 0 }"` qui watch localStorage. |
| FR214 | Section toggles refactorés en pattern Alpine cohérent (1 `x-data` par `<h3>`). |
| FR215 | Theme toggle refactoré en `x-data="{ dark: matchMedia(...).matches }"`. |
| FR216 | Tutorial overlay refactoré en `x-data="{ shown: !localStorage.tutorialDismissed }"`. |
| FR217 | Aucun script IIFE inline ne reste après refactor. |

### 3.3 HTMX

| FR | Description |
|---|---|
| FR220 | `ulog/web/static/htmx.min.js` vendoré (v2.x stable, ≤ 14 KB minified). |
| FR221 | `base.html` `<script defer src="{% static 'ulog/htmx.min.js' %}"></script>`. |
| FR222 | Click test name (sidebar Tests) emit `hx-get="?test_id=..."` + `hx-target="#records-table"` + `hx-push-url="true"`. |
| FR223 | `views.py::list_view` détecte `request.headers.get("HX-Request")` et retourne soit `list.html` complet, soit `_records_table.html` partial. |
| FR224 | Form sidebar (level/sector/file checkbox) submit via `hx-get` + swap records table only. |
| FR225 | Pagination prev/next via `hx-get` + swap records table only. |
| FR226 | Forward/back browser navigation (history) functional avec les partials. |

### 3.4 Migration & compat

| FR | Description |
|---|---|
| FR230 | Aucune nouvelle Python dependency. Alpine + HTMX vendorés en static. |
| FR231 | `pyproject.toml` `dependencies = []` inchangé. |
| FR232 | Tous les tests Django existants passent (279/279). |
| FR233 | Doc page `/docs/dev-frontend.md` créée — documente le build Tailwind CLI + les patterns Alpine + HTMX. |

---

## 4. Non-functional requirements

| NFR | Budget |
|---|---|
| NFR-PERF-80 | First paint `< 200 ms` sur la page `/` avec demo DB 43 K records (vs ~600 ms avec CDN). |
| NFR-PERF-81 | CSS total servi ≤ 15 KB minifié + gzipped. |
| NFR-PERF-82 | JS total servi ≤ 50 KB minifié (Alpine 15 + HTMX 14 + ulog inline 5 + django-browser-reload 5). |
| NFR-PERF-83 | Click filter (HTMX swap) `< 100 ms` sur la demo DB 43 K. |
| NFR-DEP-80 | Zéro nouvelle Python dep. Alpine + HTMX = static assets dans le repo. Tailwind CLI = binaire dev (pas dans wheel). |
| NFR-COMPAT-80 | Linux + macOS + Windows. Le Tailwind CLI binaire est download-by-platform. |
| NFR-DOC-80 | Doc `/docs/dev-frontend.md` couvre : install Tailwind CLI, watch mode, patterns Alpine, patterns HTMX, debug. |
| NFR-A11Y-80 | Aucune régression a11y (focus management, keyboard navigation) après refactor Alpine. |

---

## 5. API surface (sketch)

### 5.1 Tailwind CLI dev workflow

```bash
# Install (one-time)
make install-tailwind   # downloads vendor/tailwindcss for current OS

# Watch (during dev)
make watch-css          # ./vendor/tailwindcss -i input.css -o output.css --watch

# Build (before commit)
make build-css          # ./vendor/tailwindcss -i input.css -o output.css --minify
```

### 5.2 Alpine.js patterns

**Toggle (open/close)** :
```html
<div x-data="{ open: false }">
  <button @click="open = !open">Toggle</button>
  <div x-show="open" x-transition>Content</div>
</div>
```

**localStorage-backed state** :
```html
<div x-data="{ lang: localStorage.qaLang || 'fr' }"
     x-init="$watch('lang', v => localStorage.qaLang = v)">
  ...
</div>
```

**Form sync** :
```html
<input type="checkbox" x-model="filters.failed_only">
```

### 5.3 HTMX patterns

**Click → swap** :
```html
<a hx-get="/?test_id=tests/x.py::test_y"
   hx-target="#records-table"
   hx-swap="outerHTML"
   hx-push-url="true">test_y</a>
```

**Form submit → swap** :
```html
<form hx-get="/" hx-target="#records-table" hx-push-url="true">
  <input type="checkbox" name="level" value="ERROR">
  <button type="submit">Apply</button>
</form>
```

**View detection** :
```python
def list_view(request):
    is_htmx = request.headers.get("HX-Request") == "true"
    template = "ulog/_records_table.html" if is_htmx else "ulog/list.html"
    return render(request, template, ctx)
```

---

## 6. Worked examples

### 6.1 Lang switcher migration

**Avant** (vanilla JS inline, ~30 LOC) :
```html
<button id="qa-lang-en">EN</button>
<button id="qa-lang-fr">FR</button>
<script>
  const langButtons = document.querySelectorAll('[data-lang-switch]');
  const applyLang = (lang) => { /* ... */ };
  langButtons.forEach(b => b.addEventListener('click', () => applyLang(b.dataset.langSwitch)));
  applyLang(localStorage.getItem('ulogQA:_lang') || 'fr');
</script>
```

**Après** (Alpine, ~10 LOC) :
```html
<div x-data="{ lang: localStorage.getItem('ulogQA:_lang') || 'fr' }"
     x-init="$watch('lang', v => { localStorage.setItem('ulogQA:_lang', v); applyLang(v); })">
  <button @click="lang = 'en'" :class="lang === 'en' && 'bg-blue-600 text-white'">EN</button>
  <button @click="lang = 'fr'" :class="lang === 'fr' && 'bg-blue-600 text-white'">FR</button>
</div>
```

3× plus compact, état déclaratif, `:class` réactif sans manipuler le DOM.

### 6.2 Test name click → partial swap

**Avant** : full reload `/?test_id=tests/x.py::test_y`. Page entière re-rendue. Scroll position perdu. ~600 ms.

**Après** : HTMX swap uniquement `<table id="records-table">`. URL bar update via `hx-push-url`. Scroll position préservé. ~80 ms.

```html
<a hx-get="/?test_id={{ t.test_id|urlencode }}"
   hx-target="#records-table"
   hx-swap="outerHTML"
   hx-push-url="true"
   class="font-mono ...">
  {{ t.name }}
</a>
```

Backend (`views.py`) :
```python
def list_view(request):
    ...
    if request.headers.get("HX-Request") == "true":
        return render(request, "ulog/_records_table.html", ctx)
    return render(request, "ulog/list.html", ctx)
```

Et `_records_table.html` extracted from list.html (just the `<table id="records-table">` block).

---

## 7. Migration plan — Epic 9 (12 stories)

| # | Story | Estimate |
|---|---|---|
| 9-1 | Vendor `tailwindcss` binary + `tailwind.config.js` + `input.css` | S |
| 9-2 | First Tailwind CLI build + commit `output.css` + remove CDN script | M |
| 9-3 | `Makefile` targets (install/watch/build) + CI gate | S |
| 9-4 | Vendor `alpine.min.js` v3 + `<script defer>` in base.html | S |
| 9-5 | Refactor lang switcher to Alpine | S |
| 9-6 | Refactor debug bar progress to Alpine | S |
| 9-7 | Refactor section toggles + theme toggle + tutorial overlay to Alpine | M |
| 9-8 | Vendor `htmx.min.js` v2 + `<script defer>` in base.html | S |
| 9-9 | Extract `_records_table.html` partial + view HX-Request detection | M |
| 9-10 | HTMX-ify test name click + form filter submit + pagination | M |
| 9-11 | Doc page `/docs/dev-frontend.md` (Tailwind CLI + Alpine + HTMX patterns) | S |
| 9-12 | Perf benchmark: NFR-PERF-80/81/82/83 verification on demo DB 43 K | S |

Estimate scale : S = 30 min, M = 1-2 h.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Tailwind CLI binary 32 MB bloats the repo | Vendored under `vendor/` with `.gitattributes binary`. Not in sdist (excluded via `MANIFEST.in`). Users `make install-tailwind` to download for their OS. |
| Alpine.js + HTMX vendored = repo grows ~30 KB | Acceptable. Alternative: served via CDN with `defer` (but breaks offline dev). Vendored is the right call. |
| HTMX `hx-push-url` history conflicts with browser back | Story 9-10 includes explicit forward/back testing on the demo DB. |
| Refactor inline JS to Alpine introduces regression | Each story (9-5/6/7) has paired QA checklist items in `/_qa/` to verify behavior parity. |
| Tailwind CLI build differs across OS | `tailwind.config.js` deterministic ; CI run on Linux + macOS + Windows. |
| Users on `pip install ulog[web]` (no dev tools) can't rebuild CSS | They don't need to. `output.css` is committed and shipped in the package. |

---

## 9. Definition of Done — v0.8

✅ Tailwind CDN script removed from `base.html`
✅ `vendor/tailwindcss` binary checked in (or download script provided)
✅ `output.css` ≤ 15 KB committed and served
✅ Alpine.js vendored ; 5 inline JS blocks refactored
✅ HTMX vendored ; click test name + form submit + pagination use partial swaps
✅ Suite tests verte : 279/279 + new perf benchmarks (NFR-PERF-80/81/82/83)
✅ Doc `/docs/dev-frontend.md` published
✅ All `dependencies = []` invariants intact
✅ Manual QA checklist `/_qa/` extended with §6 (frontend stack verification)

---

## 10. Open questions

### Q1 — Vendored vs CDN for Alpine + HTMX

**Recommendation : vendored.** ULog is a local dev tool ; users may run offline. CDN dépendance = network call à chaque page. Vendored = ~30 KB de plus dans le repo, négligeable.

### Q2 — Tailwind CLI binary in repo vs download script

**Recommendation : download script.** Le binaire 32 MB par OS × 3 OS = 96 MB dans le repo. Trop. Le `make install-tailwind` script détecte l'OS et download la bonne version. CI cache le binaire.

### Q3 — HTMX views — partial template duplication

Le risque : `list.html` et `_records_table.html` peuvent diverger. Mitigation : `list.html` `{% include "ulog/_records_table.html" %}` à la place du bloc inline. Single source of truth.

### Q4 — Should we drop django-browser-reload after HTMX adoption?

**Non**. django-browser-reload reload la page entière après un .py change (autoreload Django). HTMX est pour les filter swaps utilisateur. Complémentaires, pas substituables.

### Q5 — Static files served via Whitenoise?

ULog ships avec Django default `StaticFilesHandler`. Pour prod (NFR-PERF-80), Whitenoise serait plus rapide. Mais ulog est un dev tool — `runserver` + `StaticFilesHandler` suffisent. Hors scope v0.8.

---

## 11. Roadmap continuation

- **v0.8.1** — Polish HTMX swaps (loading indicators, error toasts).
- **v0.9** — Static HTML export (Epic 8 v0.6 — bénéficie aussi du Tailwind CLI build).
- **v1.0** — Tag stable + freeze wire format.
- **v1.1** — Premier port satellite : `ulog-js`.

---

## 12. Change log

- **2026-05-11 v1.0** — Initial draft. Merge of 3 frontend tech recommendations into one PRD : Tailwind CLI standalone (Tier 1 MUST), Alpine.js (Tier 2 SHOULD), HTMX (Tier 3 MAY). Supersedes Story 8-1 of Epic 8 (tailwind-standalone-cli-build-pipeline) — that story is absorbed into Story 9-1 here.

---

## 13. Sources

- [HTMX vs Alpine.js dans Django 2026 — Yogesh Krishnan, Medium](https://medium.com/@yogeshkrishnanseeniraj/htmx-vs-alpine-js-in-django-lightweight-uis-for-2026-saas-code-demos-perf-tests-f5a87d38ca6a)
- [Hybrid HTMX + Minimal JS in Django 2026 — Yogesh Krishnan, Medium](https://medium.com/@yogeshkrishnanseeniraj/hybrid-htmx-minimal-js-in-django-2026-when-to-add-alpine-js-3b62210b5321)
- [Django + HTMX + Alpine.js — SaaS Pegasus](https://www.saaspegasus.com/guides/modern-javascript-for-django-developers/htmx-alpine/)
- [Django, HTMX and Alpine.JS — DEV Community](https://dev.to/nicholas_moen/what-i-learned-while-using-django-with-htmx-and-alpine-js-24jg)
- [Django with HTMX and Alpine.js — PySquad](https://www.pysquad.com/blogs/django-with-htmx-and-alpinejs-blazing-fast-ui-without-react)
- [Stop Using Tailwind CDN — DEV Community](https://dev.to/mr_nova/stop-using-tailwind-cdn-build-only-the-css-you-actually-use-django-php-go-1h38)
- [From Tailwind CDN to Production — Paul Conroy](https://www.conroyp.com/articles/tailwind-cdn-to-production-optimised-css-bundle)
- [Tailwind CLI installation docs](https://tailwindcss.com/docs/installation/tailwind-cli)
- [HTMX official docs](https://htmx.org/)
- [Alpine.js official docs](https://alpinejs.dev/)
- [Full-stack Django with HTMX and Tailwind — TestDriven.io](https://testdriven.io/courses/django-htmx/part-one-intro/)
