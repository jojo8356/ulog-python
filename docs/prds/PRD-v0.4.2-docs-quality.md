---
docType: prd
project_name: ulog-python
version: 0.4.2
date: 2026-05-11
author: jojo8356
status: draft v1
parent_prd: PRD-v0.4.1-viewer-perf-hotpath.md
---

# ULog v0.4.2 — Docs quality patch

> Post-Epic 2 documentation patch. Four goals: (a) reflect changes
> that shipped since v0.4 in the user-facing doc pages (perf cache,
> dev workflow, QA checklist pipeline, upcoming chain columns),
> (b) make every doc page navigable via a collapsible per-chapter
> Table of Contents rendered at the top of each page, (c) fix the
> markdown renderer so tables, ordered lists, italics and
> blockquotes stop leaking as raw text into the rendered HTML,
> and (d) add an Epic-level master checkbox to the `/_qa/` page
> so a whole epic's items toggle in one click.

## 0. Problem

The built-in `/docs/` pages were authored at v0.2 → v0.4 cadence and
fell behind the codebase. Three concrete drift points:

1. **`v0.4.1` perf cache is undocumented.** The
   `_AUTHORS_SUMMARY_CACHE` memoization + SQL `GROUP BY` aggregation
   landed in PRD-v0.4.1, but `author-filter.md` and
   `troubleshooting.md` still describe the O(N) walk path. Users
   troubleshooting cold-cache slowness have no doc pointer to "first
   request takes 600ms then subsequent <100ms".
2. **No contributor / dev-workflow page.** The `[dev]` extras
   (`ruff`, `mypy --strict`, `deptry`, `pip-audit`, `pre-commit`),
   the `Makefile` targets (`make check`), and the QA screenshot
   pipeline (`scripts/qa_screenshots.py` + `/_qa/`) all shipped
   without a doc page explaining how to run them. New contributors
   discover the toolchain by grepping `pyproject.toml`.
3. **Long doc pages have no overview.** `api.md` is 15 headings,
   `test-integration.md` 15, `author-filter.md` 15,
   `storage.md` 12. Readers landing on a deep link have no
   "what does this page cover?" affordance. The left-sidebar nav
   shows page titles but not in-page sections.

Additionally, the **`v0.5` chain-integrity** columns shipped in
Story 3.1 (this session, 2026-05-11) need a placeholder so the
`storage.md` schema section doesn't lie. Full chain integrity doc
lands later (Story 3.11), but the existing schema reference must
acknowledge the new columns now to avoid a misleading user-facing
contract.

Two QA-surface issues surfaced during the same session and ride
this PRD too:

4. **Markdown tables leak as raw text.** The minimal
   `_markdown_to_html` parser at `ulog/web/viewer/views.py:435`
   recognizes only `#`/`##`/`###`, fenced code blocks, `- ` lists,
   and `**bold** / [link](url) / inline code`. Tables (`| col |
   col |` + `|---|---|`), ordered lists (`1. foo`), `*italic*`,
   `> blockquotes`, and `---` horizontal rules pass through as
   verbatim text — visible on `/docs/test-integration/` § 3 ("CLI
   flags") where the table breaks the layout (see captured QA
   bug 2026-05-11).
5. **Per-Epic master checkbox missing on `/_qa/`.** Sections (`<h3>`)
   already have a master checkbox via
   `data-qa-section-toggle="e1-1.1-"` (cascades all items in that
   section). Epics (`<h2>`) don't — to mark an entire Epic done,
   the tester clicks every section toggle one by one. For a 50+
   item Epic this is friction the author flagged as slowing manual
   QA passes.

## 1. Vision

Five structural improvements, scoped narrowly:

### 1.1 In-page Table of Contents — `<details>` accordion

Every rendered doc page gains a collapsible "Contents" block injected
between the H1 title and the body. Built from H2 + H3 headings
present in the source markdown. Native HTML5 `<details>/<summary>` —
no JS, no third-party widget.

```html
<details class="my-3 rounded border ...">
  <summary class="cursor-pointer font-semibold">Contents</summary>
  <ul>
    <li><a href="#install">1. Install</a></li>
    <li><a href="#configure">2. Configure your application</a></li>
    <li><a href="#run">3. Run your code</a>
      <ul>
        <li><a href="#run-cli">CLI invocation</a></li>
      </ul>
    </li>
    ...
  </ul>
</details>
```

Default state: **collapsed**. Users scrolling a long page can pop the
accordion open, jump to a section via `#anchor`, and the URL hash
gets persisted so reload + back-button preserve position.

Anchors come from headings via a slug rule documented in §6.

### 1.2 Refresh existing pages for shipped behavior

Page-by-page deltas. Bounded; the goal is parity with the codebase
as of v0.4.1 plus an honest note where v0.5 work has started.

| Page | Changes |
|---|---|
| `quickstart.md` | Add a 6th step "Verify the install" pointing at `make check`. |
| `api.md` | Stub a "Performance characteristics" subsection under Storage handlers (per-request author-summary cache, invalidation rules). |
| `storage.md` | Add "v0.5 chain columns (preview)" note under Schema — lists `chain_pos`, `record_hash`, `prev_hash`, `immutable` with their NULL-when-disabled semantic. No claim of behavior yet. |
| `troubleshooting.md` | New entry: "First page load is 1-3s on a 40K-record DB". Explains the cold-cache vs warm-cache contract and points at `/_qa/` § 3 perf budgets for the test gate. |
| `author-filter.md` | Move the "Performance" section to reference v0.4.1's memoization + GROUP BY. Drop the now-stale "expect 4+s on first hit" warning. |
| `test-integration.md` | No content change — just gains the accordion. |
| `sectors-and-files.md` | No content change — just gains the accordion. |

### 1.3 New `contributing.md` doc page

Single page covering:
- Cloning + submodule init (`vendor/ucolor-python/`)
- `make install-dev` and what each `[dev]` package does
- `make check` — runs mypy + tests
- The full lint chain: `ruff check`, `ruff format`, `mypy ulog/`, `deptry .`, `pip-audit`
- `pre-commit` setup (one-time install of the hook)
- `scripts/qa_screenshots.py` + the `/_qa/` checklist workflow
- Story / sprint workflow pointer (`_bmad-output/` is internal,
  but contributors should know it exists)

Wires into the docs index registry (`_DOC_PAGES` in `views.py`) so
the left-sidebar nav surfaces it.

### 1.4 Markdown renderer extension — tables + ordered lists + italic + blockquotes + rules

The current `_markdown_to_html` (≈75 lines in `views.py:435`) handles
the v0.2 subset only. v0.4.2 grows it to cover the markdown
constructs already in use in the existing `.md` files:

| Construct | Markdown | Rendered HTML | Status today |
|---|---|---|---|
| Table | `\| a \| b \|`<br>`\|---\|---\|`<br>`\| 1 \| 2 \|` | `<table><thead>…</thead><tbody>…</tbody></table>` (Tailwind-styled) | ❌ leaks as raw text |
| Ordered list | `1. foo`<br>`2. bar` | `<ol><li>foo</li><li>bar</li></ol>` | ❌ leaks |
| Italic | `*foo*` or `_foo_` | `<em>foo</em>` | ❌ leaks |
| Blockquote | `> foo` | `<blockquote class="…">foo</blockquote>` | ❌ leaks |
| Horizontal rule | `---` on a line alone | `<hr class="…">` | ❌ leaks (parsed as nothing) |
| Nested list (1 level) | indented `- ` under another `- ` | `<ul><li>…<ul><li>…</li></ul></li></ul>` | ❌ flattened to top-level |

Implementation: extend the in-tree minimal parser. Cost is bounded —
each construct is ≤ 15 lines of Python including its state machine
hook (tables need 2-state lookahead for the separator row; lists need
a "depth" counter). Total renderer growth: ~120 → ~250 lines.

Decision **F4** (alternative considered): swap to `markdown-it-py`
(stable, well-maintained, ~150 KB on disk). Adds an optional dep
under `[web]` extras (consistent with `django-lucide`,
`django-browser-reload`). Rejected for v0.4.2 because:
- The in-tree parser is honest about its scope and proven safe
  against HTML injection (everything passes through `_html_escape`).
- A third-party markdown lib opens an auto-link surface area
  (HTML pass-through, raw HTML tags, schemes like `javascript:`)
  that needs hardening — not worth it for the 5 missing constructs.
- v0.6 may revisit if the docs gain a substantial markdown surface
  (GFM task lists, footnotes, definition lists, etc.) — opt-in via
  `[web-rich]` extra at that point.

### 1.5 Epic-level master checkbox on `/_qa/`

The QA checklist already implements per-section toggles via the
`data-qa-section-toggle="e1-1.1-"` attribute on the section `<h3>`
(see `qa.html:76+` and the JS handler at `qa.html:326+`). Same
mechanism, one level up: each Epic's `<h2>` gains
`data-qa-epic-toggle="e1-"`. Clicking it walks all checkboxes with
a `data-qa-id` starting with `e1-` and sets them to the toggle's
state (cascade) — including the per-section toggles, which get
flipped along the way.

```html
<h2 class="… flex items-center gap-2">
  <input type="checkbox"
         data-qa-epic-toggle="e1-"
         class="rounded text-emerald-600 …"
         title="Toggle every item in this Epic">
  {% lucide "flask-conical" size=18 %}
  <span data-i18n-key="section-1-title">1. Epic 1 — Test integration (v0.3)</span>
</h2>
```

JS extension: the existing `sectionToggles` block (`qa.html:326-`)
gains a sibling `epicToggles` loop. Both share a `_cascade(prefix,
state)` helper that updates all matching items + their persistence
in `localStorage`. ~25 added JS lines.

Indeterminate-state handling: when a section's items are partially
checked, the section toggle already shows `indeterminate` via the
existing `_refreshIndeterminate()` call. Same logic propagates to
the Epic toggle (`some checked && some unchecked` → indeterminate;
`all checked` → checked; `all unchecked` → unchecked). The
i18n title key `qa-epic-toggle` provides "Toggle every item in
this Epic" / "Cocher / décocher tous les items de cet Epic"
strings, added to `qa_strings.json` for both `en` and `fr`.

## 2. Scope

### 2.1 In scope

1. Markdown renderer extension in `ulog/web/viewer/views.py`'s
   `_markdown_to_html` to:
   - Emit `id="<slug>"` on every `<h2>` and `<h3>`.
   - Pre-scan the document for H2/H3, build the TOC.
   - Inject the `<details>` block immediately after the first H1.
   - Parse GFM-style tables (`| col | col |` + `|---|---|` separator).
   - Parse ordered lists (`1. foo`, multi-digit, restart from any
     number — emit `<ol start="N">` when N != 1).
   - Parse `*italic*` / `_italic_` → `<em>`.
   - Parse `> blockquote` (multi-line, indented continuations).
   - Parse `---` / `***` on a line alone → `<hr>`.
   - Parse one level of nested `- ` lists (4-space indent rule).
2. Page-by-page content edits per §1.2.
3. New `ulog/web/docs/contributing.md` page + `_DOC_PAGES` entry.
4. QA page (`ulog/web/templates/ulog/qa.html`) gains a
   `data-qa-epic-toggle="eN-"` checkbox on each Epic `<h2>`. JS
   handler in `qa.html:326+` extended with an `epicToggles` loop
   sharing the existing `_cascade` helper; same persistence in
   `localStorage`; indeterminate state mirrored from section
   toggles.
5. `qa_strings.json` (EN + FR) gains the `qa-epic-toggle`
   tooltip string.
6. Tests in `tests/test_web.py`:
   - `test_docs_page_has_toc_accordion`
   - `test_docs_page_h2_h3_have_anchor_ids`
   - `test_docs_contributing_page_renders`
   - `test_docs_renders_table_to_html_table`
   - `test_docs_renders_ordered_list`
   - `test_docs_renders_italic_blockquote_hr`
   - `test_qa_template_has_epic_toggle_per_h2` (parses
     rendered HTML for `data-qa-epic-toggle` per Epic)
7. Regenerate QA screenshots for `section-1-5` (test-integration doc)
   and `section-2-6` (author-filter doc) since they'll show the TOC
   AND the table on `/docs/test-integration/` § 3 will render
   correctly. Also regenerate `section-qa` since the QA page now
   shows Epic-level toggles.

### 2.2 Out of scope (deferred)

- **Full `chain-integrity.md` page** — lands with Story 3.11 once
  the chain feature is end-to-end (`ulog verify` CLI is in 3.7;
  no point documenting half a feature).
- **Anchor link icons on hover** (the GitHub-style `🔗` that appears
  next to a heading on mouseover). Nice-to-have, doesn't change the
  navigation primitive. Defer to v0.6 doc polish.
- **Cross-page deep linking** beyond the current sidebar — no
  search, no auto-glossary.
- **Markdown library swap-in** — the in-tree parser stays. v0.6
  may revisit `markdown-it-py` if the docs gain GFM-only constructs
  (task lists, footnotes, definition lists, strikethrough). Out of
  scope here; the renderer extensions in §1.4 cover the 6 currently
  needed constructs without a new dep — see Decision F4 for the
  cost/benefit.
- **GFM extras** — task lists (`- [ ] foo`), strikethrough
  (`~~foo~~`), autolinks, emoji shortcodes, footnotes. Not used
  in current docs; defer.
- **Multi-level nested lists** (depth > 1). Current docs nest at
  most once. Defer to a `markdown-it-py` migration if depth > 1
  is ever needed.
- **i18n of doc page contents** — the `qa_strings.json` EN/FR
  pattern is for the `/_qa/` page only. Doc pages stay EN.

## 3. Acceptance

- **AC1** — Every page at `/docs/<slug>/` shows a `<details>` block
  titled "Contents" between the H1 and the first paragraph, with
  one `<li><a href="#slug">` per H2 and nested `<ul>` for the H3s
  beneath each.
- **AC2** — Each H2 / H3 in the rendered HTML has an `id` attribute
  matching the slug used in the TOC links. Clicking a TOC link
  navigates to the target heading.
- **AC3** — `/docs/contributing/` returns 200 and renders. Sections
  present: Setup, Linters, Tests, QA pipeline, Pre-commit, Sprint workflow.
- **AC4** — `/docs/storage/` schema section mentions `chain_pos`,
  `record_hash`, `prev_hash`, `immutable` as v0.5-preview columns
  with NULL/0 defaults when chain mode is off.
- **AC5** — `/docs/author-filter/` and `/docs/troubleshooting/`
  reference the v0.4.1 perf cache; no stale "4+s first hit" warning.
- **AC6** — `/docs/test-integration/` § 3 CLI flags renders as a
  proper `<table>` with `<thead>` / `<tbody>` and Tailwind borders
  — NOT as raw `| Flag | Behavior |` text. Same on any markdown
  file with a table.
- **AC7** — `_markdown_to_html` correctly emits: `<ol>` for `1.` /
  `2.` lists with `start=` when N≠1, `<em>` for `*italic*` and
  `_italic_`, `<blockquote>` for `> foo`, `<hr>` for `---` and
  `***`, nested `<ul>` for one level of indented `- `.
- **AC8** — Each Epic `<h2>` on `/_qa/` has an
  `<input type="checkbox" data-qa-epic-toggle="eN-">` that toggles
  every checkbox in that Epic; state persists via the existing
  `localStorage` mechanism; indeterminate state shows when items
  are partially checked.
- **AC9** — All existing 290+ tests stay green. New tests for
  AC1–AC3, AC6–AC8 pass.
- **AC10** — `/_qa/` reference screenshots `section-1-5`,
  `section-2-6` (TOC accordion) and `section-qa` (Epic toggles)
  regenerated.

## 4. Non-functional

- **No new runtime dependency.** The accordion is HTML5 native
  (`<details>`); the renderer changes are stdlib `re` + the existing
  `_html_escape` helper; the QA Epic checkbox reuses the existing
  vanilla-JS handler.
- **Bundle size.** Zero JS added on the docs side. The QA Epic
  toggle adds ~25 lines of JS to the existing `<script>` already
  inline in `qa.html` (no new asset).
- **Renderer cost.** Two-pass walk over the markdown (TOC pre-scan
  + render). Largest current page is ≤ 300 lines; render time
  remains sub-millisecond.
- **Slug stability.** Anchor slugs derived from heading text via a
  fixed rule (lowercase, ASCII, non-alphanum → `-`, collapse
  consecutive `-`, strip leading/trailing `-`). Pre-existing
  links in commit messages / GitHub issues will work as long as the
  heading text doesn't change.
- **Accessibility.** `<details>` is natively keyboard-accessible
  (`Tab` to focus, `Enter` to toggle, `Space` toggles). TOC links
  are real anchors, indexed by search engines and screen readers.
  The Epic toggle is a regular `<input type="checkbox">` — same a11y
  surface as the existing section toggles.
- **Backwards compat.** Renderer changes are purely additive on
  rendered HTML; markdown source files don't need anchor syntax.
  Existing `localStorage` QA state survives — new Epic toggles
  start unchecked and don't affect previously checked items.

## 5. Risks / open questions

- **Heading slug collisions.** Two H2s with the same text → same
  slug → broken second anchor. Mitigation: append `-2`, `-3` on
  collision (same rule as GitHub markdown). Risk accepted; surveyed
  the 7 current pages, no collisions today.
- **Long pages with mostly H3s.** Some pages (e.g. `api.md`) have
  many H3 entries under one H2. The TOC could become long. Decided
  to keep nesting visual but rely on `<details>` to fold it away by
  default — readers who open it accept the length.
- **`<details>` styling on Safari.** Native rendering differs across
  browsers; pre-Mojave Safari has known quirks with `<summary>`
  text alignment. Acceptable: viewer's user base is dev-time local
  Chromium/Firefox; v0.5 doesn't ship public-facing Safari surfaces.

## 6. Implementation notes

### 6.1 Slug rule (Decision F1)

```python
def _slug(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
```

Mirrors GitHub's `<h2>` anchor rule for portability. Collisions
disambiguated via a per-document counter (`_slug_counts: dict[str, int]`
inside `_markdown_to_html`).

### 6.2 TOC injection point (Decision F2)

Injected **after** the first `<h1>` line, **before** any other
content. If a page has no H1 (anomaly — all current pages do),
inject at top of the article. Empty TOC (page has H1 only) → skip
the `<details>` block entirely.

### 6.3 Renderer change shape

The current `_markdown_to_html` walks lines once, emitting HTML.
The TOC requires two passes:
1. **Pre-scan** — collect `(level, text, slug)` for every H2/H3.
2. **Build TOC** — once, as `<details>...<ul>...</ul></details>`.
3. **Render** — walk again, emit headings with `id=` attributes,
   and inject the pre-built TOC right after the H1.

Alternative considered: single-pass with deferred TOC stitching at
end. Rejected — the markdown is small enough (largest doc < 300
lines) that the second pass is irrelevant cost; clarity wins.

### 6.4 No autolinking on headings (Decision F3)

H2/H3s get `id=` but **not** a wrapped `<a href="#...">` anchor
link (the GitHub icon-on-hover pattern). Reason: the TOC already
gives navigation; adding hover-anchors doubles the surface for
zero new affordance and requires extra CSS. Revisit at v0.6 doc
polish if user feedback asks for it.

### 6.5 Migration of existing in-page heading references

`troubleshooting.md` and `api.md` contain a few internal `[link](#anchor)`-
style references in prose. After this PRD lands, those anchors must
match the new slug rule (lowercase, hyphenated). One-shot fix
performed manually in the page-edit step §1.2.

### 6.6 Table parser shape (Decision F5)

Two-line lookahead state machine. When the current line matches
`^\|.+\|$` AND the next line matches `^\|[\s:-]+\|$` (alignment
hint), enter table mode:

```python
def _maybe_table(lines: list[str], i: int) -> tuple[str, int] | None:
    """Return (html, new_i) if lines[i:] starts a table, else None."""
    if not (lines[i].startswith("|") and lines[i].rstrip().endswith("|")):
        return None
    if i + 1 >= len(lines):
        return None
    sep = lines[i + 1].strip()
    if not re.fullmatch(r"\|[\s:|-]+\|", sep):
        return None
    headers = [c.strip() for c in lines[i].strip("|").split("|")]
    aligns = _parse_table_aligns(sep)  # left / right / center / None
    rows: list[list[str]] = []
    j = i + 2
    while j < len(lines) and lines[j].startswith("|"):
        rows.append([c.strip() for c in lines[j].strip("|").split("|")])
        j += 1
    return _render_table(headers, aligns, rows), j
```

Renders as:
```html
<table class="my-3 text-sm border-collapse">
  <thead class="bg-slate-100 dark:bg-slate-800">
    <tr><th class="px-3 py-1.5 text-left border …">Flag</th>…</tr>
  </thead>
  <tbody>
    <tr><td class="px-3 py-1.5 border …"><code>--ulog-db PATH</code></td>…</tr>
  </tbody>
</table>
```

Cells go through `_inline_md` so inline code / bold / italic / links
work inside table cells (matches GFM).

### 6.7 Italic precedence (Decision F6)

`_inline_md` already handles `**bold**`. Adding italic requires care:
`**bold**` MUST be matched BEFORE `*italic*` to avoid eating the
double-asterisk. Order in the regex chain:

1. `` `inline code` `` → `<code>` (consumes content; protects from
   further substitutions).
2. `\*\*(.+?)\*\*` → `<strong>` (greedy non-overlap).
3. `\*([^*]+)\*` → `<em>` (only matches single asterisks not
   adjacent to another).
4. `_([^_]+)_` → `<em>` (underscore variant; mid-word `_` is
   intentionally not escaped — same gotcha as CommonMark).
5. `\[link\](url)` → `<a>`.

### 6.8 Ordered list `start` attribute (Decision F7)

`1. foo / 2. bar` → `<ol><li>foo</li><li>bar</li></ol>`.
`3. foo / 4. bar` → `<ol start="3"><li>foo</li><li>bar</li></ol>`.

Rationale: authors sometimes split a procedure across non-contiguous
markdown blocks (text between steps 2 and 3). The `start=` attribute
preserves the visible numbering. Matches CommonMark behavior.

### 6.9 Epic toggle cascade — JS shape (Decision F8)

Extend the existing `_cascade(prefix, state)` helper (or extract one
if it isn't already factored). The Epic toggle handler:

```js
const epicToggles = root.querySelectorAll('[data-qa-epic-toggle]');
epicToggles.forEach(toggle => {
  toggle.addEventListener('change', () => {
    const prefix = toggle.dataset.qaEpicToggle;  // e.g. "e1-"
    _cascade(prefix, toggle.checked);
    // Also flip the section toggles in this Epic so their
    // indeterminate state lifts.
    root.querySelectorAll(`[data-qa-section-toggle^="${prefix}"]`)
        .forEach(t => { t.checked = toggle.checked; t.indeterminate = false; });
  });
});
// After any item changes, refresh both section AND epic indeterminate states.
function _refreshAllIndeterminate() {
  _refreshIndeterminate('[data-qa-section-toggle]');
  _refreshIndeterminate('[data-qa-epic-toggle]');
}
```

Wired into the existing `change` listener on `[data-qa-id]`
checkboxes so toggling an item bubbles up to refresh both section
and Epic checkboxes.
