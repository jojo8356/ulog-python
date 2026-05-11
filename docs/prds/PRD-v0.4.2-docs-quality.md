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

> Post-Epic 2 documentation patch. Two goals: (a) reflect changes that
> shipped since v0.4 in the user-facing doc pages (perf cache, dev
> workflow, QA checklist pipeline, upcoming chain columns), and
> (b) make every doc page navigable via a collapsible per-chapter
> Table of Contents rendered at the top of each page.

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

## 1. Vision

Three structural improvements, scoped narrowly:

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

## 2. Scope

### 2.1 In scope

1. Markdown renderer extension in `ulog/web/viewer/views.py`'s
   `_markdown_to_html` to:
   - Emit `id="<slug>"` on every `<h2>` and `<h3>`.
   - Pre-scan the document for H2/H3, build the TOC.
   - Inject the `<details>` block immediately after the first H1.
2. Page-by-page content edits per §1.2.
3. New `ulog/web/docs/contributing.md` page + `_DOC_PAGES` entry.
4. Tests in `tests/test_web.py`:
   - `test_docs_page_has_toc_accordion`
   - `test_docs_page_h2_h3_have_anchor_ids`
   - `test_docs_contributing_page_renders`
5. Regenerate QA screenshots for `section-1-5` (test-integration doc)
   and `section-2-6` (author-filter doc) since they'll show the TOC.

### 2.2 Out of scope (deferred)

- **Full `chain-integrity.md` page** — lands with Story 3.11 once
  the chain feature is end-to-end (`ulog verify` CLI is in 3.7;
  no point documenting half a feature).
- **Anchor link icons on hover** (the GitHub-style `🔗` that appears
  next to a heading on mouseover). Nice-to-have, doesn't change the
  navigation primitive. Defer to v0.6 doc polish.
- **Cross-page deep linking** beyond the current sidebar — no
  search, no auto-glossary.
- **Markdown library swap-in** — the current minimal renderer
  is documented as v0.3-grade in `views.py:435`; v0.6 may swap to
  `markdown-it-py`. Out of scope here; the TOC injection lives in
  the renderer regardless of which one.
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
- **AC6** — All existing tests stay green. New tests for AC1–AC3
  pass.
- **AC7** — `/_qa/` reference screenshots `section-1-5` and
  `section-2-6` regenerated to show the new TOC accordion at the top
  of each doc page.

## 4. Non-functional

- **No new runtime dependency.** The accordion is HTML5 native
  (`<details>`); the renderer change is stdlib `re` + the existing
  `_html_escape` helper.
- **Bundle size.** Zero JS added. Tailwind classes for `<details>`
  styling reuse `prose` defaults plus a few utility classes.
- **Slug stability.** Anchor slugs derived from heading text via a
  fixed rule (lowercase, ASCII, non-alphanum → `-`, collapse
  consecutive `-`, strip leading/trailing `-`). Pre-existing
  links in commit messages / GitHub issues will work as long as the
  heading text doesn't change.
- **Accessibility.** `<details>` is natively keyboard-accessible
  (`Tab` to focus, `Enter` to toggle, `Space` toggles). TOC links
  are real anchors, indexed by search engines and screen readers.
- **Backwards compat.** The renderer change is purely additive on
  rendered HTML; markdown source files don't need anchor syntax.

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
