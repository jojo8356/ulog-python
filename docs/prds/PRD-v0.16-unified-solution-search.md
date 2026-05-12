---
docType: prd
project_name: ulog-python
version: 0.16.0
date: 2026-05-12
author: jojo8356
status: draft v1
parent_prd: PRD-v0.13-local-fix-database.md
related_prd:
  - PRD-v0.14-known-bugs-auto-lookup.md
  - PRD-v0.15-community-solutions-site.md
---

# ULog v0.16 — Unified solution search (community + local, consent-first)

> Merges v0.13's **local fix DB** and v0.15's **`ulog.solutions`
> community site** into a single search UX on the detail view.
> Flow: dev clicks "Search solutions" → consent dialog (first-use
> only) → **community site queried first** (the bigger pool) →
> local DB queried second → results merged + deduped + ranked.
> No network call ever happens without explicit user consent for
> that record. v0.14 (known-bugs lookup) plugs in as a third source
> when it ships.

---

## 0. 30-second pitch

v0.13 + v0.14 + v0.15 each ship their own panel on the detail view.
Three panels = three places to look = cognitive load when the
question is just "has anyone fixed this?".

v0.16 unifies the search experience: **one button "Search solutions"
on every record with a signature**. Click → consent dialog ("send
your error signature to `ulog.solutions`? It's a SHA-256 hash, no
code, no PII") → **two queries fire in parallel** (community site +
local DB) → results merge into one ranked list with provenance
badges (`community / local / known-bug`). Local results always
show; remote ones only on consent.

The consent is **per-record** (not global): the dev decides each
time. A "remember consent for this session" checkbox makes the
common case painless.

---

## 1. Vision

### 1.1 Why this exists

Three observations from prototyping the v0.13 + v0.14 + v0.15
panel stack:

1. **Three side-by-side panels is bad UX.** The dev clicks the
   record, sees "Local fixes" + "Known matches" + "Community
   solutions" — each potentially empty, each potentially with
   one true relevant answer buried below uncertain ones. Merged
   ranking is what they actually want.
2. **The consent dance must be EXPLICIT and per-record.** Sending
   the error signature to `ulog.solutions` is a network call out
   of the local process. Even though the payload is just a hash,
   privacy-conscious users want a click. The pattern of "global
   opt-in via `setup(community_solutions=True)`" assumes a homogeneous
   trust posture; real teams have records they'd happily share and
   records they'd never want to.
3. **Local-first cost is zero; community costs a roundtrip.** A
   sensible default is: **show local results immediately, gate
   the community fetch behind consent**. Even when consent is given,
   results stream in as they arrive — local appears within 5 ms,
   community within 200 ms.

### 1.2 What v0.16 isn't

- **Not a new data layer.** Re-uses v0.13's local sidecar, v0.15's
  hosted endpoint, v0.14's bug cache (when v0.14 ships). v0.16 is
  pure orchestration + UX.
- **Not a search engine in itself.** Backends do the searching;
  v0.16 fans out and merges.
- **Not opt-in globally.** Each query is per-user-per-record. A
  `setup()` flag can DEFAULT the consent state but not bypass the
  per-record button.
- **Not a session that learns** ("user always consents → stop
  asking"). The "remember for session" checkbox is **scoped to the
  current viewer process** and resets on restart. Persistent consent
  remains explicit each viewer launch.

### 1.3 Target users

- **Riad** (carried, junior dev) — biggest win. One button, three
  sources, ranked list. Stops being "do I need to check three
  places?".
- **Lin** (carried) — runs in a corporate environment where
  egress traffic is audited. Per-record consent is exactly the
  control her security team wants documented.
- **Marco** (carried, solo dev) — clicks consent once per session,
  done.
- **NEW: Aïcha**, a privacy-conscious dev — wants ULog to never
  contact `ulog.solutions` for sensitive error signatures (e.g.
  internal endpoints). Per-record consent lets her allow on
  "InvalidEmailError" and deny on "InternalTokenLeakError".

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | One "Search solutions" button on every detail view; result panel renders ≤ 5 ms for local + ≤ 300 ms for community after consent | yes |
| SC2 | Consent dialog is shown EVERY first-record-per-session unless `setup(community_solutions='auto-consent')` (highly discouraged, banner-warned) | yes |
| SC3 | Result merge order: relevance-rerank weighted (community accepted+helpful = highest, local-by-trusted-author = second, known-bug-accepted = third, community-others, local-others) | yes |
| SC4 | Provenance badge on EVERY result item: `community` / `local` / `known-bug` (when v0.14 ships) | yes |
| SC5 | "Search solutions" works fully offline when consent denied (local-only) | yes |
| SC6 | Zero new PyPI runtime deps for the merge logic; community fetch uses stdlib `urllib` (already used elsewhere) | yes |
| SC7 | `tests/test_unified_search_e2e.py` covers: consent-given path, consent-denied path, network-down path, dedup of community-and-local entries by same author, ranking determinism | yes |

---

## 2. Scope (v0.16)

### 2.1 In scope (10 features, ~ 500 LOC)

1. **Unified "Search solutions" button** on `/r/<id>/` — visible whenever the record has a `signature` (v0.13). Hidden when no signature exists (i.e. record predates v0.13 or `capture_stack=False` was passed AND msg-only signature also unavailable).
2. **Consent dialog** — modal that shows on first click per viewer session per record. Body: "Send the error signature `a3f7c12…` (a SHA-256 hash; no code, no PII, no logs) to `ulog.solutions` to look for community fixes?". Three buttons: `[Yes, this record]`, `[Yes, this session]`, `[No, local-only]`.
3. **Per-session consent state** — kept in `localStorage` under `ulog:consent_session_id`. Survives reloads within the SAME viewer process; cleared on viewer restart (the session id is generated server-side on viewer startup and surfaces via a `<meta name="ulog-session-id" ...>` tag).
4. **Parallel fan-out** — `Promise.all([fetchLocal(sig), fetchCommunity(sig)])`. Local is always queried; community gated by consent.
5. **Merge + rerank** — see Decision D3 below for the ranking formula.
6. **Provenance badge** — every result item carries a colored chip: `community` (purple), `local` (emerald), `known-bug` (slate).
7. **Dedup heuristic** — if the same author has BOTH a local entry AND a community entry for the same signature, collapse into one item showing both provenances (`local + community`). Prevents "this dev appears twice".
8. **Network failure UX** — when consent given but community endpoint unreachable: a small amber strip "Community search failed (offline?). Showing local results only." Local results still render.
9. **Settings: `setup(community_solutions='off' | 'opt-in' | 'auto-consent')`** — `opt-in` (default) is the per-record-dialog flow. `off` hides the button entirely. `auto-consent` skips the dialog AND shows a permanent amber banner ("auto-consent mode active — all signature lookups go to ulog.solutions automatically"). Users who pick `auto-consent` accept the trade-off explicitly.
10. **Doc page `/docs/unified-search/`** — covers the consent model, the 3 sources, the ranking formula, network-failure behaviour, the `auto-consent` warning.

### 2.2 Explicit non-goals

- **Persistent consent across viewer restarts** — out. Each viewer launch starts at "no consent yet". Privacy default = re-ask.
- **A "consent allowlist" of signatures the user pre-approved** — out. Trust me: it sounds nice, fast becomes confusing.
- **Sending more than the signature** (msg, stack, frameworks) — out. Server-side ranking uses only the signature. Adding more context = more privacy exposure for marginal ranking gain.
- **Background pre-fetch on viewer load** ("warm the cache for top-10 unresolved errors") — out. Every query is consent-gated; pre-fetch would violate that.
- **Inline editing of community results** — out (read-only on remote results). Local results link to v0.13's edit form.
- **AI summarisation of merged results** — out forever.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Consent denied → user later clicks again on the same record | Re-shows the dialog (consent state is per-click, not sticky-denied). |
| Consent given for "session" → user reloads the viewer | Session-id regenerates; consent re-prompts on next click. Documented. |
| Community endpoint returns 500 | Amber strip + local results render. Logged in viewer stderr. |
| Community endpoint returns 1000 results | Truncate to 20 server-side; "view all on ulog.solutions" link. |
| User in `auto-consent` mode opens 100 records back-to-back | 100 background fetches. Documented as the trade-off. Banner remains visible. |
| Signature has 0 community results AND 0 local results AND 0 known-bug results | Single message: "No solutions yet — be the first to share one." with a link to v0.13's resolve form. |
| Same author has 1 local + 1 community fix for the same sig | Collapsed into one row, badge `local + community`, fix text from whichever is newer. |
| v0.14 (known-bugs) not yet implemented | Source skipped silently. v0.16 ships before v0.14; works with 2-source merge until v0.14 lands. |
| `community_solutions='off'` set in setup | Button hidden entirely. v0.13 panel still renders. Documented as "explicitly community-disabled". |
| `auto-consent` AND `community_solutions='off'` simultaneously | `off` wins. Documented in the `setup()` docstring. |

### 2.4 Protected invariants

- **I5 (carried):** Logging API unchanged.
- **I22 (new):** A network call to `ulog.solutions` NEVER happens without an explicit user action (click on the button + consent on the dialog). The dialog cannot be auto-dismissed; the user must pick an option.
- **I23 (new):** The payload to `ulog.solutions` for search is the signature hex string. Nothing else. (Audit-checked in the test suite — `test_unified_search_e2e.py::test_only_signature_in_search_payload`.)

---

## 3. Functional Requirements

- **FR241**: `/r/<id>/` renders a "Search solutions" button whenever `record.signature` is non-NULL.
- **FR242**: Click on the button shows the consent modal IF (consent state for this session/record) ∉ `{accepted_session, accepted_record_<id>}`.
- **FR243**: Consent modal renders the signature hex (truncated to 8 + `…`) and the dialog body verbatim per Scope 2 above.
- **FR244**: Three options: `[Yes, this record]`, `[Yes, this session]`, `[No, local-only]`. Each writes to `localStorage`.
- **FR245**: On `Yes, this record` — fan out: local query + `GET https://ulog.solutions/api/fix/<signature>` (or `community_solutions_endpoint` per v0.15's `setup` arg).
- **FR246**: Merged result list — `<ol>` of result items, each with: provenance badge + author + relative date + fix excerpt + "view full" link.
- **FR247**: Ranking formula (Decision D3 below) — DETERMINISTIC, tested by `test_unified_search_ranking.py`.
- **FR248**: Network error UX: amber strip below the button, local results still listed.
- **FR249**: `setup(community_solutions: str = 'opt-in')` accepts `'off' | 'opt-in' | 'auto-consent'`. `auto-consent` triggers a permanent amber banner in the viewer chrome.
- **FR250**: Doc page `/docs/unified-search/` covering the model + the 3 sources + the ranking + the consent model.

---

## 4. Non-Functional Requirements

- **NFR-PERF-170**: Local query ≤ 5 ms p99 on a 1000-fix sidecar DB.
- **NFR-PERF-171**: Community query ≤ 300 ms p95 over a typical internet link to `ulog.solutions`.
- **NFR-PERF-172**: Merge + render ≤ 50 ms for ≤ 20 results.
- **NFR-DEP-160**: Stdlib only on the viewer side (`urllib.request` for community fetch). Reuses v0.13 + v0.15 modules.
- **NFR-SEC-160**: Network payload audited: signature ONLY. Test gate exists.
- **NFR-PRIV-10**: Consent is opt-in per record per session by default. `auto-consent` is a documented trade-off behind an obvious banner.
- **NFR-DOC-160**: Doc page covers the consent model with a clear "what is sent, what is not".

---

## 5. API surface (sketch)

### 5.1 User-facing (viewer)

```
1. Open /r/142071/.
2. See record + Authored by + Call stack + "Search solutions" button.
3. Click "Search solutions".
4. Modal: "Send signature `a3f7c12...` to ulog.solutions?"
5. Click "Yes, this session".
6. Panel renders below the button with 3 results, merged + ranked.
```

### 5.2 Setup

```python
ulog.setup(
    integrity='hash-chain',
    capture_stack=True,
    community_solutions='opt-in',  # default; per-record consent dialog
    # community_solutions='off',         # no button shown
    # community_solutions='auto-consent', # no dialog; amber banner forever
)
```

---

## 6. Implementation sketch

| Story | Scope | LOC |
|---|---|---|
| 16.1 | "Search solutions" button + signature visibility logic | 50 |
| 16.2 | Consent modal + localStorage session state | 80 |
| 16.3 | Fan-out (local + community in parallel) | 60 |
| 16.4 | Merge + rerank (Decision D3) + dedup heuristic | 90 |
| 16.5 | Provenance badges + result item template | 70 |
| 16.6 | Network-error UX (amber strip) | 30 |
| 16.7 | `setup(community_solutions=...)` 3-mode handling + auto-consent banner | 50 |
| 16.8 | `test_unified_search_e2e.py` (consent given/denied/offline + ranking + payload audit) | ~ 200 tests |
| 16.9 | Doc page `/docs/unified-search/` | n/a |

Total ~ 430 LOC core + ~200 LOC tests.

---

## 7. Decisions log

| ID | Decision | Trade-off |
|---|---|---|
| D1 | Single button + merged panel replaces 3 side-by-side panels | Less cognitive load. Loses per-source visibility — replaced by provenance badges on each item. |
| D2 | Consent per-record-per-session, NOT global | Privacy-by-default. Adds clicks for power users — mitigated by "Yes, this session" option. |
| D3 | Ranking formula (deterministic): community-accepted×3 + local-author-trusted×2 + known-bug-accepted×2.5 + recency-decay-factor (30 days half-life) + helpful-vote-count×0.1. Score normalised 0-100. | Documented + tested. Future-tunable as a single function. |
| D4 | Network payload = signature only | Defence in depth. Server can't infer code from a hash. |
| D5 | Consent state in `localStorage` per session | Survives reload, not viewer restart. Privacy default = re-ask each viewer launch. |
| D6 | `auto-consent` mode exists but banner-warned | Some teams (CI-only ULog deployments) want zero clicks. Trade-off explicit. |
| D7 | No persistent consent across restarts | "Don't ask me again ever" is exactly the misuse-pattern that erodes consent UX over time. Opt out via `auto-consent` instead. |
| D8 | Dedup by `(author_email, signature)` collapse | Same author shouldn't appear twice in a 5-item list. Provenance becomes a comma-list (`local + community`). |
| D9 | v0.14 plug-in slot reserved | When v0.14 ships, becomes the third fan-out target. Until then, 2-source merge works. |
| D10 | Re-uses v0.13's signature column | No new column, no new schema migration. v0.13 is a hard dep. |

---

## 8. Open questions

| ID | Question | Tentative |
|---|---|---|
| Q1 | Should the consent dialog include a "Why?" disclosure link? | Yes — one-line "Read more: /docs/unified-search/#consent" inline. |
| Q2 | What about a "delete this consent" affordance in settings? | Yes — settings page with "Clear all session consents" button. v0.16.1 candidate. |
| Q3 | Should the panel collapse to empty state once results render (vs persist below the button)? | Persist — re-collapsing is friction. |
| Q4 | If a user has `community_solutions='off'` AND clicks the button anyway (browser cache / stale page), what happens? | Server-side defence: button is hidden. Backend route also gates on the `community_solutions` setting; returns 403. |
| Q5 | Rate limiting on `ulog.solutions` API for an `auto-consent` user with 1000 records? | Yes — 60 req/min per IP. Documented. |

---

## 9. References

- [Source: docs/prds/PRD-v0.13-local-fix-database.md] — local layer + signature
- [Source: docs/prds/PRD-v0.14-known-bugs-auto-lookup.md] — future third source
- [Source: docs/prds/PRD-v0.15-community-solutions-site.md] — community endpoint + ed25519 identity
- [GDPR Article 6(1)(a)] — explicit consent as legal basis
- [Mozilla Consent UX Guidelines] — per-action, never coerced
