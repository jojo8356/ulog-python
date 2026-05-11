---
docType: prd
project_name: ulog-python
version: 0.4.5
date: 2026-05-11
author: jojo8356
status: draft v1
parent_prd: PRD-v0.2.1-ui-bugfixes.md
---

# ULog v0.4.5 — Theme swap: every element transitions in lockstep

> Tiny UI polish. The dark/light mode toggle currently produces a
> visible "wave" because some elements fade over 500 ms while others
> flip instantly — the per-element transition rule in `base.html`
> enumerates 15 tags by name and misses everything else. Replace it
> with a single coordinated animation (View Transitions API primary,
> universal-selector fallback) so every pixel flips together.

## 0. Problem

`base.html:28-37` declares:

```css
body, header, aside, main, table, tr, td, th, button, input,
a, span, code, pre, div {
    transition: background-color 500ms ease,
                color 500ms ease,
                border-color 500ms ease;
}
```

This rule produces visible desync in five distinct ways:

1. **Missing tags.** `label`, `input[type=checkbox]`, `details`,
   `summary`, `svg`, `nav`, `section`, `ul`, `li`, `p`, `h1-h6`,
   `form`, `time`, `dl/dt/dd`, `abbr`, `kbd`, `mark` are NOT in
   the selector list. Every such element with a `dark:bg-*` or
   `dark:text-*` Tailwind class flips **instantly** while the
   listed tags ease over 500 ms — a literal wave across the page.
   The bug is visually obvious on `/_qa/` (lots of `<label>`s) and
   on `/docs/*` (`<details>` accordion + `<h1>-<h3>` headings).

2. **Missing properties.** Only `background-color`, `color`, and
   `border-color` are transitioned. The viewer also flips
   `box-shadow` (modal/tutorial overlays), `outline-color` (focus
   rings during keyboard nav), `fill` / `stroke` (lucide SVG
   icons), and would flip `--prism-*` CSS custom properties once
   the v0.8.1 syntax-highlight PRD lands. Each of these snaps
   instantly during a theme switch.

3. **`color` cascade fights `fill: currentColor` on SVGs.**
   Lucide icons inherit color via `currentColor`. They transition
   correctly on the listed parents, but icons inside an unlisted
   `<label>` or `<p>` see their parent's `color` snap → the icon
   snaps too. Same desync, different vector.

4. **The transition rule applies to EVERY state change, not just
   theme.** Hovering during the 500 ms window animates the hover
   color over 500 ms — way too slow for a hover. The user
   perceives this as "the UI feels slow even after the theme
   settles" because the next hover after a theme swap still
   inherits the slow curve.

5. **No coordination with localStorage write.** The toggle handler
   flips `<html class="dark">` and writes `localStorage.theme` in
   the same tick. If the browser is mid-paint when the class
   flips, the paint snapshot is interrupted — a one-frame flash
   on slower devices.

## 1. Vision

A single coordinated cross-fade of the ENTIRE document, lasting one
configurable duration (default 300 ms), gated to the theme-toggle
action only. No element opts out, none opts in late, none keeps
the slow curve after the swap.

### 1.1 Primary path — View Transitions API

When `document.startViewTransition` is available (Chrome/Edge 111+,
Firefox 131+, Safari 18+ — covering ≈ 96 % of dev-time browsers in
May 2026 per caniuse.com), wrap the class flip in a
`startViewTransition` callback. The browser takes a snapshot before
the callback, runs the callback synchronously, takes a snapshot
after, and crossfades the two snapshots over 300 ms. **Every pixel
transitions in lockstep by construction** — the API was designed
for exactly this case.

```js
document.getElementById('theme-toggle').addEventListener('click', () => {
  const flip = () => {
    const html = document.documentElement;
    if (html.classList.contains('dark')) {
      html.classList.remove('dark');
      localStorage.theme = 'light';
    } else {
      html.classList.add('dark');
      localStorage.theme = 'dark';
    }
  };
  if (typeof document.startViewTransition === 'function') {
    document.startViewTransition(flip);
  } else {
    flip();  // fallback path styles handle the transition
  }
});
```

Tweak the transition duration via the canonical pseudo-elements:

```css
::view-transition-old(root),
::view-transition-new(root) {
    animation-duration: 300ms;
    animation-timing-function: ease;
}
```

### 1.2 Fallback path — `theme-transitioning` flag class

For browsers without View Transitions (~4 %: very old Chromium,
Safari < 18 without the feature flag, niche embedded browsers),
the toggle adds `theme-transitioning` to `<html>` for 320 ms,
then removes it:

```js
function flipWithFallback() {
  const root = document.documentElement;
  root.classList.add('theme-transitioning');
  flip();  // same callback as above
  setTimeout(() => root.classList.remove('theme-transitioning'), 320);
}
```

CSS:

```css
.theme-transitioning,
.theme-transitioning *,
.theme-transitioning *::before,
.theme-transitioning *::after {
    transition: background-color 300ms ease,
                color 300ms ease,
                border-color 300ms ease,
                fill 300ms ease,
                stroke 300ms ease,
                outline-color 300ms ease,
                box-shadow 300ms ease !important;
}
```

`!important` because some Tailwind utility classes already declare
their own `transition` (e.g., `transition-colors` on hover states).
The `theme-transitioning` window overrides them so the swap fades
uniformly; once the class is gone, the per-utility transitions
resume normal duty.

### 1.3 Remove the existing per-tag rule

The current rule at `base.html:32-37` is the source of the desync.
Delete it outright. The two paths above replace it without need
for any element-by-element listing.

### 1.4 First-paint flash guard

Today, `base.html:14-23` reads `localStorage.theme` and adds
`.dark` to `<html>` BEFORE the `<body>` paints — good (no FOUC).
That logic stays. The `flip()` callback inside
`startViewTransition` runs the same code on the toggle path; the
snapshot mechanism handles the cross-fade between states.

## 2. Scope

### 2.1 In scope

1. **Delete** the per-tag transition rule (`base.html:32-37`).
2. **Add** the View Transitions API primary path in the
   `#theme-toggle` click handler.
3. **Add** the `theme-transitioning` fallback class — both the
   JS that toggles it and the CSS that applies the universal
   transition during its lifetime.
4. **Add** `::view-transition-old(root)` /
   `::view-transition-new(root)` keyframe duration tuning so
   the View Transitions and fallback paths feel identical
   (300 ms ease).
5. **Keep** the icon-crossfade rule at `base.html:42-49`
   unchanged — it's a SUB-element animation (sun ↔ moon icons
   in the toggle button itself), independent of the page-wide
   swap. It still runs at 500 ms because it's a deliberate
   theatrical pause that signals the user that the toggle
   registered. Visually distinct from the page swap.
6. **Playwright e2e test** in `tests/test_theme_swap_e2e.py`:
   - `test_theme_toggle_uses_view_transition_when_available`
   - `test_theme_toggle_adds_theme_transitioning_class_temporarily`
   - `test_theme_toggle_persists_in_localStorage`
   - `test_no_per_tag_transition_rule_in_rendered_css`
     (regression guard: assert the deleted rule doesn't sneak
     back in).
   - `test_dark_class_flips_on_html_root` (sanity).

### 2.2 Out of scope (deferred)

- **Circular-reveal effect** centered on the toggle button
  (the "ripple" demoed in Chrome's docs). Cute, but adds
  CSS clip-path animation + complexity. Defer to a v0.6
  polish patch once the basic coordinated swap ships and
  feedback validates the appetite.
- **Animation tuning per-component.** If a future component
  (e.g., chain-integrity badge with traffic-light states)
  needs its OWN transition timing, it should declare a
  `:not(.theme-transitioning *) { transition: … }` scope.
  Out of scope here; revisit only when first such component
  asks.
- **`prefers-reduced-motion` handling.** Should land in this
  PRD too. Wrapped into AC8 below for explicitness.
- **Server-rendered theme detection** (Sec-CH-Prefers-Color-Scheme
  hint). The client-side localStorage approach is fine for a
  local dev tool; client hints add a Django middleware for
  no user-visible gain.

## 3. Acceptance

- **AC1** — Click the theme toggle: every element with a Tailwind
  `dark:*` class transitions to/from its dark variant in the
  same 300 ms window. No element flips instantly. No element
  arrives late.
- **AC2** — On Chrome/Edge ≥ 111, Firefox ≥ 131, Safari ≥ 18,
  the network panel shows no extra DOM mutation during the
  transition: the browser composites the snapshot crossfade
  internally.
- **AC3** — On Chrome with View Transitions disabled via
  `chrome://flags`, the fallback path runs: `theme-transitioning`
  appears on `<html>` for ≈ 320 ms, every element transitions
  via the universal CSS rule, then the class is removed.
- **AC4** — The element-by-element transition rule
  (`body, header, aside, main, table, tr, td, th, button, input,
  a, span, code, pre, div { transition: … }`) is gone from the
  rendered HTML. Regression guard test asserts this.
- **AC5** — Hovering a button DURING the theme transition does
  NOT inherit the 300 ms curve for the hover itself — the hover
  uses whatever transition the underlying Tailwind utility
  declares. Verified visually + via a brief test that doesn't
  see a `transition-duration: 300ms` on `:hover` post-swap.
- **AC6** — `localStorage.theme` is written before the toggle
  click handler returns. Reload immediately after the click
  → page comes back up in the new theme with no flash (the
  existing pre-paint `localStorage` read at `base.html:14-23`
  still works).
- **AC7** — The sun/moon icon crossfade inside the toggle button
  itself keeps its 500 ms curve (deliberate theatrical pause).
  No visual collision with the 300 ms page-wide swap.
- **AC8** — Respect `prefers-reduced-motion`. When the media
  query matches, the View Transitions duration drops to 0 ms
  (instant) AND the fallback path skips the
  `theme-transitioning` class entirely:
  ```css
  @media (prefers-reduced-motion: reduce) {
      ::view-transition-old(root), ::view-transition-new(root) {
          animation-duration: 0ms;
      }
  }
  ```
- **AC9** — All 334 existing tests stay green. 5 new
  `tests/test_theme_swap_e2e.py` tests pass.
- **AC10** — QA reference screenshots regenerated for any page
  whose visual diff exceeds noise — likely none, since the steady-
  state rendering is unchanged; only the in-flight animation
  differs.

## 4. Non-functional

- **Zero new runtime dependency.** View Transitions is a stdlib
  browser API. The fallback path is plain CSS + 5 lines of JS.
- **Bundle size impact.** 0 KB added to assets; net delta is
  slightly negative (the old per-tag rule deleted vs the new
  universal-selector rule). Both are inline `<style>` in
  `base.html`.
- **Performance.** View Transitions runs the snapshot composite
  on the browser's compositor thread — no main-thread frame
  drops even on a long page. The fallback's universal
  `transition` selector is heavier (every element has its
  transition properties reset) but only for 320 ms; outside
  that window the rule doesn't match.
- **Accessibility.** `prefers-reduced-motion` handled per AC8.
  Toggle button keyboard-accessible (already is — standard
  `<button>`). Theme persistence still survives reload.
- **Backwards compat.** Browsers without View Transitions (and
  with reduced-motion enabled) fall through to the existing
  "instant flip" UX. The bug they see today (per-tag desync)
  is replaced by the cleaner instant flip — strict improvement.

## 5. Risks / open questions

- **Long pages (e.g., `/diff/<sha>/` rendering 200K-line diffs).**
  View Transitions snapshot the rendered DOM; a 200K-line `<pre>`
  block is a large bitmap. Mitigation: View Transitions runs on
  the compositor thread and can handle large surfaces. If
  benchmarks show frame drops, scope the transition to a smaller
  container via the `view-transition-name` property — defer this
  optimization until measured.
- **Safari feature-flag gating.** Per caniuse.com, Safari ships
  the API in 18+ but some Safari versions require enabling it
  via Settings > Advanced > Feature Flags. The fallback path
  catches these users; degradation is graceful.
- **`!important` in the fallback CSS.** Necessary because some
  Tailwind utilities (`transition-colors`, `transition-all`)
  set their own `transition` shorthand that would otherwise win
  the cascade. The `!important` is scoped to the
  `.theme-transitioning` window (~320 ms), so it doesn't
  affect normal hover/focus transitions.
- **Multi-tab theme sync.** Not addressed. If user has two ULog
  tabs open and toggles in one, the other doesn't follow. Same
  behavior as today; out of scope. Could add a `storage` event
  listener in a future PRD if requested.

## 6. Implementation notes

### 6.1 Single-source-of-truth flip function (Decision I1)

The `flip()` callback is defined ONCE and called from both
the View Transitions path and the fallback path. Future-proof:
if a third path appears (e.g., the multi-tab `storage` listener
suggested in §5), it reuses the same function.

```js
function _applyTheme(targetDark) {
    const root = document.documentElement;
    if (targetDark) {
        root.classList.add('dark');
        localStorage.theme = 'dark';
    } else {
        root.classList.remove('dark');
        localStorage.theme = 'light';
    }
}
```

The click handler computes the target from the CURRENT class
(invert), and passes the boolean. Idempotent.

### 6.2 Why 300 ms (Decision I2)

Industry-standard for theme swaps:
- Tailwind's docs use 200-300 ms.
- shadcn/ui uses 300 ms.
- Vercel's "next-themes" defaults to 200 ms.
- Material Design 3 recommends 200-400 ms for "expressive"
  state changes.

We pick 300 ms — fast enough not to feel sluggish, slow enough
that the human eye registers the transition as a transition
(not a frame swap). The PRECEDING 500 ms felt sluggish during
user testing; 300 ms is the sweet spot in user feedback across
the ecosystem.

### 6.3 Test strategy (Decision I3)

The Playwright tests assert TWO observable facts:

1. **DOM-level invariants.** Toggle click → `<html>` gains/loses
   `.dark`; localStorage updates; on browsers without View
   Transitions support, `.theme-transitioning` appears
   transiently.

2. **CSS-rule invariants.** The rendered page's inline
   `<style>` block does NOT contain the old per-tag selector
   `body, header, aside, main, table, ...`. Pure regression
   guard.

We do NOT assert pixel-level animation correctness in tests —
that's a visual review job. Playwright can take screenshots
mid-transition with `page.wait_for_timeout(150)` after the
click, but that's flaky on slow CI runners and would just
re-prove what the DOM/CSS assertions already cover.

### 6.4 Reduced-motion respect (Decision I4)

The `@media (prefers-reduced-motion: reduce)` rule zeroes both
the View Transitions duration AND the fallback's transition
duration in one shot:

```css
@media (prefers-reduced-motion: reduce) {
    ::view-transition-old(root),
    ::view-transition-new(root) {
        animation-duration: 0ms;
    }
    .theme-transitioning,
    .theme-transitioning *,
    .theme-transitioning *::before,
    .theme-transitioning *::after {
        transition: none !important;
    }
}
```

Users who've opted out of motion get an instant flip on both
paths. AC8 verifies.

## 7. See also

- **Parent:** [PRD-v0.2.1-ui-bugfixes.md](./PRD-v0.2.1-ui-bugfixes.md) — defined the original theme-fade contract; this PRD tightens it.
- **Future companion:** [PRD-v0.8-modern-frontend-stack.md](./PRD-v0.8-modern-frontend-stack.md) — when Tailwind CLI replaces the CDN, the inline `<style>` block in `base.html` migrates to a real CSS file; this PRD's rules move with it.
- **External references:**
  - [MDN — View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API)
  - [caniuse.com — view-transitions](https://caniuse.com/view-transitions) (96 % global support, May 2026)
  - [Akash Hamirwasia — Full-page theme toggle animation with View Transitions API](https://akashhamirwasia.com/blog/full-page-theme-toggle-animation-with-view-transitions-api/)
  - [Ian K Duffy — Creating a theme switcher using View Transition](https://iankduffy.com/articles/creating-a-theme-switcher-using-view-transition/)
