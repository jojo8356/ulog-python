---
docType: prd
project_name: ulog-python
version: 0.14.0
date: 2026-05-12
author: jojo8356
status: draft v1 (LONG-TERM)
parent_prd: PRD-v0.13-local-fix-database.md
related_prd:
  - PRD-v0.15-community-solutions-site.md
---

# ULog v0.14 — Known-bugs auto-lookup (StackOverflow / docs scraping)

> **Long-term.** When the viewer renders an error / exception, it
> auto-detects the **language** (Python, JS, Go, …) and the
> **framework / library** in the stack (Django, requests, sqlalchemy,
> aiohttp, …), then queries a **read-only cache of known bugs** from
> StackOverflow + GitHub issues + the library's own docs. The detail
> view gains a "Known matches" panel: top 3 results with title, age,
> accepted-answer indicator, deep link. Zero LLM, deterministic
> ranking.

---

## 0. 30-second pitch

When `pyodbc.Error: ('HY000', 'Connection is busy')` fires, the
debugging move is:

1. Copy the error.
2. Paste into Google.
3. Click the first StackOverflow result.

v0.14 collapses that to: **the detail view's "Known matches" panel
already shows the SO answer** (with accepted-answer green check),
plus 2 alternates, plus a link to the relevant section of pyodbc's
docs. The panel is populated at viewer-load time from a local
cache that's refreshed daily via a background scrape.

Long-term feature. The cost is the scrape infrastructure (rate
limits, ToS compliance, schema drift). The payoff is "the dev's
next 30 seconds, automated".

---

## 1. Vision

### 1.1 Why this exists

Three observations:

1. **The same error has been Googled 100 000 times.** Programmer time spent rediscovering the SO answer is enormous. If ULog already knows you're a Python+SQLAlchemy user hitting `OperationalError: database is locked`, the result is **deterministically** the top SO answer on that exact phrase.
2. **Most relevant docs links are framework-pinned.** `django.db.utils.IntegrityError` should link to Django's `IntegrityError` reference, not a generic Python doc. We know it's Django because we read the stack.
3. **Local-fix-database (v0.13) is great for PROJECT-internal knowledge. v0.14 fills the GAP**: "this isn't a bug we've seen before — but the rest of the world has".

### 1.2 What v0.14 isn't

- **NOT an LLM call.** No GPT/Claude/Llama invocation. v0.14 is pure search-and-rank on a pre-built index of public sources. Reproducible, offline-able, no hallucination risk.
- **NOT a paid SaaS bridge.** No "log in with your StackOverflow account". Read-only public-data scraping under the source's ToS (SO Data Dump, GH public issues API, official docs).
- **NOT a code-suggestion engine.** "Apply this patch?" — out. v0.14 surfaces information; the dev applies the fix.
- **NOT crowd-sourced.** That's v0.15 (community solutions site). v0.14 reads PUBLIC EXISTING content.
- **NOT real-time.** Cache refresh is daily (configurable). A bug fixed 1 hour ago on SO doesn't show up until the next scrape.

### 1.3 Target users

- **All carried personas** benefit. Specifically:
  - **Riad** (carried from v0.13, junior dev) — biggest win. Cuts onboarding-time-to-fix from hours to minutes.
  - **Marco** (solo dev) — no team to ask. v0.14 IS his team.
- **NEW: Nora**, a CTO evaluating ULog adoption — known-bugs lookup is a hire-vs-buy moment (Sentry has this; making ULog match it is competitive baseline).

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | Detect language correctly on 95% of errors in a curated 100-error corpus | yes |
| SC2 | Detect framework correctly on 80% (mostly Python/JS/Go/Rust) | yes |
| SC3 | Top-3 results contain a relevant answer for 70% of common errors (manual annotation on the same 100-error corpus) | yes |
| SC4 | Cache size on disk ≤ 500 MB after scraping top-10K bugs across the 5 most-used frameworks | yes |
| SC5 | Detail view "Known matches" panel renders in ≤ 100 ms (cache lookup) | yes |
| SC6 | Daily scrape stays within SO Data Dump's published throttle / GH public API's 5K-req/h tier | yes |
| SC7 | Operating fully offline (no network at viewer time) when cache is populated | yes |
| SC8 | Zero PyPI runtime deps for the viewer-side lookup (cache reader is stdlib SQLite). Scrape-side may need `requests` under a `[bug-cache]` extra | yes |

---

## 2. Scope (v0.14)

### 2.1 In scope (12 features, long-term — 1500+ LOC estimate)

1. **Language detector** (`ulog/_bug_lookup/language.py`) — sniffs from record's `file` extension + the stack frames. Python (`.py`), JS (`.js` / `.ts` / `.jsx` / `.tsx`), Go (`.go`), Rust (`.rs`), Java (`.java`), Ruby (`.rb`). Other → `unknown`.
2. **Framework / library detector** — heuristics on stack frames: presence of `django/`, `requests/`, `sqlalchemy/`, `flask/`, `fastapi/`, `pandas/`, `numpy/`, `aiohttp/` in any frame's file path. Multi-match allowed.
3. **Bug-cache SQLite** (`~/.cache/ulog/bug-cache.sqlite`, configurable) — schema: `(source TEXT, source_id TEXT, language TEXT, framework TEXT, title TEXT, body TEXT, accepted_answer_body TEXT, score INTEGER, url TEXT, scraped_at INTEGER, indexed_terms TEXT)`. Full-text index via SQLite FTS5.
4. **Scrape pipelines (5 of them)**:
   - **StackOverflow Data Dump pipeline** — quarterly Data Dump download, parse, extract relevant Python/JS/Go/Rust answers with score ≥ 5 + accepted answers.
   - **GitHub Issues pipeline** — daily API call per tracked repo (Django, Flask, requests, etc.) for "closed-with-fix" issues. Read-only public API.
   - **Official docs pipeline** — scrape each framework's official docs index (Django reference, requests user guide, etc.) into a "docs section → URL" map.
   - **PyPI release notes pipeline** — known-issue paragraphs from CHANGELOG.md.
   - **(Future) GitLab Issues / GitTea pipeline** — out of v0.14; v0.14.x.
5. **Search-and-rank** — given `(language, framework, error_msg)`, query FTS5 for top-10, re-rank by: signal weight (accepted > high-score > recent), framework-match boost, recency decay. Stdlib only.
6. **Detail-view "Known matches" panel** — between v0.13's "Fix" banner and the Exception block. Top 3 results. Each: source icon (SO logo / GH logo / docs-page icon), title, age, accepted-marker green check, deep link.
7. **`ulog bug-cache refresh [--source SOURCE]` CLI** — runs the scrape pipelines. Logs progress to stderr. Non-fatal on API failures (cache stays usable with stale data).
8. **`ulog bug-cache stats` CLI** — prints cache size, age, hit-rate (queries hitting → returning results).
9. **Source attribution + ToS compliance** — every panel result shows the source clearly + UTC last-scraped timestamp. SO Data Dump is CC BY-SA 4.0; attribution is mandatory.
10. **Caching disabled by default** — `setup(bug_lookup='off' | 'cache-only' | 'cache-or-fetch')`. `'off'` = no panel. `'cache-only'` = use the cache, never network. `'cache-or-fetch'` = fall back to network on miss (rate-limited).
11. **`/docs/bug-lookup/` doc page** — explains the data sources, ToS, refresh cycle, how to extend with custom sources.
12. **Custom source plugin slot** — `ulog/_bug_lookup/sources/<name>.py` interface: `scrape() -> Iterable[BugEntry]`. Users can add their own internal sources (a corporate wiki, a private GH org).

### 2.2 Explicit non-goals

- **LLM calls** — out, forever.
- **Crowd-sourced fixes** — that's v0.15.
- **Real-time scraping** — cache only. Too easy to violate ToS otherwise.
- **PII detection in scraped content** — out. SO and GH are public; users' privacy is their own concern.
- **Browser-side scraping (puppeteer / playwright spider)** — out. Use the structured APIs.
- **A "submit your own fix" button in the panel** — that's v0.15 territory.
- **i18n of scraped content** — out for v0.14. English-only. v0.14.x candidate.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Cache empty, user opens a record | "No known matches (cache empty — run `ulog bug-cache refresh`)" badge. No crash. |
| Cache stale (> 14 days) | Banner: "Cache last refreshed 18 days ago — consider refreshing." |
| Error msg has PII (e.g. `Failed to login for user 'alice@example.com'`) | Email shape redacted in the search query (so the email never goes to network in `cache-or-fetch` mode). Documented. |
| Network down + `cache-or-fetch` mode | Falls back to cache silently. |
| SO Data Dump schema changes | Scrape pipeline test_bug_lookup_so_schema.py fails fast in CI. User keeps the last-known-good cache. |
| User in a corporate environment with proxy | Standard `HTTP_PROXY` / `HTTPS_PROXY` env vars honoured. |
| User wants to share a fix back upstream | v0.14 does NOT support this. v0.15 does. |

### 2.4 Protected invariants

- **I5 (carried):** Logging API unchanged.
- **I17 (new):** Viewer NEVER calls network at page-render time. All lookups go through the cache. Network only via explicit `ulog bug-cache refresh` OR `cache-or-fetch` (documented warning).
- **I18 (new):** Cached content is ALWAYS attributed to the source + license. CC BY-SA 4.0 footer on all SO results.

---

## 3. Functional Requirements

- **FR201**: `detect_language(record) -> Language` enum (`PYTHON`, `JS`, `GO`, `RUST`, `JAVA`, `RUBY`, `UNKNOWN`).
- **FR202**: `detect_frameworks(record) -> set[str]` returns matching framework names from a built-in registry.
- **FR203**: `search_bugs(error_signature, language, frameworks, limit=3) -> list[BugMatch]` — FTS5 query + rerank.
- **FR204**: `BugMatch` dataclass: `source`, `source_id`, `title`, `excerpt`, `accepted`, `score`, `url`, `scraped_at`.
- **FR205**: `ulog bug-cache refresh [--source SO|GH|DOCS|RELEASE_NOTES|all] [--cache-path PATH]`.
- **FR206**: `ulog bug-cache stats [--format text|json]`.
- **FR207**: Detail-view "Known matches" panel — render top-3 BugMatch objects with source icon + title + age + accepted badge + URL link (external, `rel="noopener"`).
- **FR208**: `setup(bug_lookup: str = 'off')` — modes per Scope 10.
- **FR209**: PII-aware query rewriter — strips emails, IPs, UUIDs from the query before going to the cache index.
- **FR210**: Doc page `/docs/bug-lookup/` covering data sources, ToS, refresh, plugin slot.

---

## 4. Non-Functional Requirements

- **NFR-PERF-150**: Cache lookup ≤ 100 ms on a 500K-entry FTS5 cache.
- **NFR-PERF-151**: Scrape refresh (incremental) ≤ 5 min for daily GH issues + docs.
- **NFR-PERF-152**: Quarterly SO Data Dump ingest ≤ 30 min on a developer laptop.
- **NFR-DEP-140**: Viewer-side: stdlib only (sqlite3 module). Scrape-side: `requests` + `lxml` (or `selectolax`) under `[bug-cache]` extra.
- **NFR-LEGAL-10**: SO content under CC BY-SA 4.0 — attribution + link mandatory. GitHub content under each repo's license — link mandatory. Official docs — link only, never reproduce body verbatim in the cache (snippet only).
- **NFR-SEC-140**: All scraped HTML stripped to text via stdlib `html.parser` before indexing. No raw HTML stored.

---

## 5. API surface (sketch)

### 5.1 User experience (zero config)

```python
ulog.setup(integrity='hash-chain', bug_lookup='cache-only')
# That's it. Cache must be populated first via:
# $ ulog bug-cache refresh
```

### 5.2 CLI

```bash
ulog bug-cache refresh --source SO         # one source
ulog bug-cache refresh                     # all sources
ulog bug-cache stats
#  Entries: 412 870  (SO: 380K, GH: 28K, docs: 4.8K)
#  Last refresh: 2026-05-11T03:00Z (1 day ago)
#  Hit rate (last 100 lookups): 73 %
```

### 5.3 Plugin slot

```python
# ulog/_bug_lookup/sources/my_corp_wiki.py
from ulog._bug_lookup import register_source, BugEntry

@register_source('corp-wiki')
def scrape() -> Iterable[BugEntry]:
    yield BugEntry(...)
```

---

## 6. Implementation sketch (long-term — 5 distinct sub-epics)

| Sub-epic | Scope | LOC |
|---|---|---|
| 14.A | Language + framework detectors + tests on a 100-error corpus | 200 |
| 14.B | Bug-cache SQLite schema + FTS5 index + ranker | 250 |
| 14.C | SO Data Dump pipeline + tests against a frozen dump fixture | 300 |
| 14.D | GH Issues pipeline (paginated, rate-limited) | 200 |
| 14.E | Docs + release-notes pipelines + Viewer panel + CLI + doc page | 400 |

Total ~ 1350 LOC. Multi-month effort, likely shipped as v0.14.0 → v0.14.5 incrementally.

---

## 7. Decisions log

| ID | Decision | Trade-off |
|---|---|---|
| D1 | NO LLM | Reproducibility + offline-ability + zero hallucination + free. Loses fuzzy-match magic. |
| D2 | Cache-first; network is opt-in per query | Predictable perf + offline OK + ToS-friendly. Stale by ≤ cache age. |
| D3 | SO Data Dump as primary source | Bulk-licensed, doesn't hit live API. Attribution mandatory. |
| D4 | English-only for v0.14.0 | Reduces scope. v0.14.x candidate for FR/ES/DE. |
| D5 | Framework detection by stack-frame path | Lightweight, deterministic. Misses dynamic-import cases (documented). |
| D6 | PII redaction at query-rewrite time | Defence in depth — emails / UUIDs / IPs stripped before reaching cache OR network. |
| D7 | Plugin slot for custom sources | Big-org users (corp wiki, internal jira) can wire their own. |
| D8 | Daily refresh as default | Sweet spot between cost and freshness. Configurable per source. |
| D9 | NO write-back path | v0.14 is read-only. v0.15 is the write-back layer. |

---

## 8. Open questions

| ID | Question | Tentative |
|---|---|---|
| Q1 | SO Data Dump full ingest is ~30 min — is there a "fast subset" pipeline? | Yes — v0.14.0 ships "top-100K-Python-questions" subset (~5 min). Full dump is v0.14.1. |
| Q2 | What about Discourse forums (Django, Rust)? | Out of v0.14.0. v0.14.x candidate. |
| Q3 | Cache invalidation on language detection improvement (re-run search on cached errors)? | No — invalidation is by `scraped_at`. Language detection is consumer-side. |
| Q4 | Should the panel show a confidence score? | No — flat top-3 list. Confidence is noise. |
| Q5 | Privacy: can a competitor figure out our codebase by watching network for `cache-or-fetch` mode? | Cache-or-fetch sends sanitised queries only. Document the threat model. |
| Q6 | Distribution of the cache: ship a "starter cache" with ULog (e.g. 50 MB pre-built for the top 100 errors)? | Yes — v0.14.1 candidate. Speeds up onboarding. |

---

## 9. References

- [Source: docs/prds/PRD-v0.13-local-fix-database.md] — local PROJECT-INTERNAL fixes; v0.14 covers the WORLD-EXTERNAL counterpart
- [Source: docs/prds/PRD-v0.15-community-solutions-site.md] — write-back layer; v0.14 is the READ side
- [StackOverflow Data Dump policy] — bulk-licensed, CC BY-SA 4.0
- [GitHub REST API rate-limits] — 5K req/hour authenticated
- [Sentry's "Resolved with" UX] — competitive baseline
