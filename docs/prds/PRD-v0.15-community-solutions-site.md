---
docType: prd
project_name: ulog-python
version: 0.15.0
date: 2026-05-12
author: jojo8356
status: draft v1 (LONG-TERM)
parent_prd: PRD-v0.13-local-fix-database.md
related_prd:
  - PRD-v0.14-known-bugs-auto-lookup.md
---

# ULog v0.15 — `ulog.solutions` community site

> **Very long-term.** A hosted site (`ulog.solutions`) where devs
> push their FIX entries (from v0.13's local fix database) into a
> public, signature-keyed, crowd-curated repository. From the
> viewer, when an error fires and v0.13 has no local fix AND v0.14
> has no SO match, a panel offers: "View 8 community solutions on
> ulog.solutions for this error". The viewer can also push the
> local fix back — opt-in, signed, attributed.

---

## 0. 30-second pitch

v0.13 stores fixes per-project. v0.14 reads existing public bugs.
v0.15 closes the loop: **devs upload their fixes** to a public
crowd-sourced database keyed by ULog's error signature.

Why ULog's signature is the magic: `sha256(canonical_msg + stack_hash)`
**is content-addressable** — two devs in two organisations hitting
the same Django race condition produce the same signature. They've
been searching SO with different keywords; ULog matches them
deterministically.

Mechanics:

1. Dev resolves an error locally (v0.13).
2. "Share with community" button → signs the fix with the dev's
   GitHub identity (OAuth) → POSTs to `https://ulog.solutions/api/fix`.
3. Other devs hitting the SAME signature see the panel auto-load
   from the same endpoint (cached locally for 24h).
4. Upvote / mark-helpful aggregate signal; abuse flagging by
   moderators.

This is a 12-month build minimum and only makes sense once ULog
has a user base. Slotted as v0.15 to acknowledge the dependency
order: v0.13 (local) → v0.14 (read public) → v0.15 (write public).

---

## 1. Vision

### 1.1 Why this exists

Three observations:

1. **Public crowd-sourcing IS the right shape for cross-organisation knowledge.** SO works because every dev contributes. Sentry's "discovered solutions" works at the org level; v0.15 generalises to anyone running ULog.
2. **Signature-keyed database avoids the "what error are we talking about" ambiguity** that plagues SO question-quality. Two devs hitting `sqlalchemy.exc.OperationalError: database is locked` from a multi-threaded SQLite app produce identical signatures, instantly.
3. **The viewer is the right surface for crowd-knowledge discovery.** No tab-switch, no Googling, no "is this the same bug?" anxiety. The fix appears in-context, with attribution.

### 1.2 What v0.15 isn't

- **NOT a replacement for SO.** v0.14 reads SO; v0.15 is a NEW DB scoped to "fixes keyed by ULog signatures". Adjacent + complementary.
- **NOT a forum / discussion site.** Solutions are atomic posts. Comments are flat 1-deep. No threading.
- **NOT user-generated docs.** No long-form articles. The unit is "I hit this error and did THIS to fix it".
- **NOT a product**. The hosted side is run by Johan as a free service. No paid tier, no SaaS lock-in. Trade-off: scaling is a problem if it takes off.
- **NOT a CDN for the v0.14 cache.** Separate database, separate ingest. v0.14 is "public bug knowledge from existing sources"; v0.15 is "ULog-native fix submissions".
- **NOT mandatory.** Users who don't want a community presence ignore the "Share" button forever.

### 1.3 Target users

- **Marco** (carried) — submits fixes from his own project; gets back fixes from others. Network effect.
- **Lin** (carried) — has 30 services; submitting fixes is a side-effect of resolving errors. Compounding internal knowledge → external.
- **NEW: Yael**, who maintains an open-source library — sees community fixes for HER library's errors land on `ulog.solutions/<signature>`. Free user-research surface.
- **NEW: Pierre**, a moderator (Johan to start; volunteers later) — flags spam, merges duplicates.

### 1.4 Success criteria

| ID | Metric | Target (v1 launch) |
|---|---|---|
| SC1 | 1000 devs registered via GitHub OAuth | yes |
| SC2 | 5000 fix submissions across 1000 unique signatures | yes |
| SC3 | Hit rate (signatures with ≥ 1 solution) for top-100 Python error signatures ≥ 50 % | yes |
| SC4 | Hosted infra ≤ 30 €/month at launch (single VPS + free CDN tier) | yes |
| SC5 | Submission flow (resolve locally → click "Share" → choose visibility → done) ≤ 30 seconds | yes |
| SC6 | Spam / abuse moderation queue ≤ 24h response time | yes |
| SC7 | Local viewer can operate fully offline (community fixes cached for 24h) | yes |

---

## 2. Scope (v0.15)

### 2.1 In scope (15 features — multi-quarter effort)

#### Server-side (`ulog.solutions`)

1. **Hosted site `https://ulog.solutions/`** — Django (mirrors the local viewer stack). Tailwind UI matching the local viewer's design.
2. **GitHub OAuth** — sign in to submit. Read access stays public.
3. **`/api/fix` POST endpoint** — accepts `{signature, fix_text, commit_sha?, language?, frameworks?, author_github_id, signed_at_iso, ed25519_signature}`. Validates signature, dedupes (same author + same signature within 1 hour = update). Returns the canonical URL.
4. **`/api/fix/<signature>` GET endpoint** — paginated list of fixes for a signature. Order: helpful-votes DESC, recency DESC. Returns JSON.
5. **Public pages `/<signature>`** — human-readable page: signature hex (truncated), language + framework chips, top-3 fixes inline + "view all (N)" expand, "submit your own" CTA.
6. **Search**: `/?q=...` full-text search across fix titles + signatures (FTS5 server-side).
7. **Upvote / mark-helpful** — 1 click per logged-in user per fix; aggregate count visible.
8. **Spam moderation queue** — flagged-by-3 fix enters moderation; moderator reviews & hides.

#### Client-side (ULog viewer)

9. **"Community solutions" panel** in detail view — between v0.14's "Known matches" and v0.13's "Fix" banner. Hidden when `setup(community_solutions=False)`. Lazy-fetches from `ulog.solutions/api/fix/<signature>` (24h cache).
10. **"Share with community" button** on the local fix form — opt-in, OAuth-flow on first use. Subsequent shares 1-click.
11. **Local fix signed before send** — ed25519 keypair generated on first share, stored under `~/.config/ulog/identity.pem`. Public key uploaded to the server bound to the GitHub identity.
12. **Privacy filters** — same PII-redaction as v0.14 applied at submission: emails / UUIDs / IPs stripped from `fix_text` (preview shown before submit).

#### Doc + ops

13. **`/docs/community/` doc page** — covers privacy model, signature mechanics, OAuth flow, deletion procedure.
14. **GDPR + content-takedown procedure** — `/legal/takedown` form, email contact, response SLA documented.
15. **`/api` documented OpenAPI 3 schema** — third parties (IDE extensions, etc.) can read the data programmatically. CC BY-SA 4.0 on submitted content.

### 2.2 Explicit non-goals

- **Paid features / SaaS tier** — never. Donations welcome.
- **Federation (multiple ulog.solutions instances)** — out of v0.15.0. Long-term candidate.
- **AI-summarized fixes / "best answer" auto-pick** — out forever.
- **User profiles / karma scoreboard** — out. Solutions matter, not reputation rankings.
- **Mobile app** — out. The viewer is the only client.
- **Comment thread** — out. Flat 1-comment-per-user reply (`/api/fix/<signature>/<fix_id>/comment`) is v0.15.1 candidate.
- **Soft-fork / private instance** — explicitly supported via self-host (Docker Compose recipe shipped with the codebase).

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| User submits a fix with PII | PII-redaction preview shown; user must confirm. If they bypass via API, content moderation handles. |
| User's GitHub account is deleted | Their submissions stay (CC BY-SA 4.0); attribution becomes `<former contributor>`. |
| Same signature submitted by 100 devs in 1 hour | Server rate-limits to N per signature per IP. Subsequent submits 429. |
| Server is down (hosted site outage) | Viewer falls back to cache; if cache miss → "Community solutions unavailable (try again later)" badge. No crash. |
| Hosted site is shut down (Johan moves on) | Codebase is open-source (Docker Compose ships). Community can fork-host. |
| User wants to delete their own fix | Soft-delete (hidden, original text preserved in audit log per CC BY-SA's "removal request" handling). Hard-delete via GDPR procedure. |
| A flagged fix is actually correct | Moderator unhides; reviewer flag reasoning logged. |
| Self-signed local certs in corporate proxies | OAuth uses HTTPS to GitHub; standard `REQUESTS_CA_BUNDLE` honoured. |

### 2.4 Protected invariants

- **I5 (carried):** Logging API unchanged.
- **I19 (new):** No client telemetry. The viewer fetches fixes; the server logs the request (standard nginx logs). No "ULog phones home with your error msgs without you clicking Share".
- **I20 (new):** All submissions are CC BY-SA 4.0 (mirrors SO). Users acknowledge at submit time.
- **I21 (new):** Public keys are bound to GitHub identities, NEVER to email or other PII.

---

## 3. Functional Requirements

### Server-side
- **FR221**: Django + PostgreSQL + GH OAuth + Tailwind CDN initially.
- **FR222**: `/api/fix` POST: ed25519-signed submission, dedup, returns canonical URL.
- **FR223**: `/api/fix/<signature>` GET: paginated solutions, JSON output.
- **FR224**: `/<signature>` HTML page: human-readable, indexable by search engines.
- **FR225**: Search FTS5 over fix titles + signatures.
- **FR226**: Upvote endpoint `/api/fix/<id>/helpful` (POST), 1-per-user-per-fix, idempotent.
- **FR227**: Moderation queue: 3-flag threshold → hidden + reviewer notification.
- **FR228**: Audit log: every soft-delete / unhide / moderator action.

### Client-side
- **FR229**: "Community solutions" panel in detail view, lazy-fetched, 24h local cache.
- **FR230**: "Share with community" button: OAuth on first use, ed25519 sign + POST, PII-redaction preview.
- **FR231**: `~/.config/ulog/identity.pem` ed25519 keypair generation on first share.
- **FR232**: `setup(community_solutions: bool = False, community_solutions_endpoint: str = "https://ulog.solutions/api")`.

### Privacy + ops
- **FR233**: `/legal/takedown` form with structured fields; email backend with 72h SLA.
- **FR234**: GDPR data-export endpoint `/api/user/me/export` for logged-in users.
- **FR235**: Self-host Docker Compose recipe in `ops/ulog-solutions/` under MIT.

---

## 4. Non-Functional Requirements

- **NFR-PERF-160**: Public page render ≤ 200 ms on a 100K-fix DB (CDN-cached static rendering).
- **NFR-PERF-161**: Submission flow (POST + index update) ≤ 500 ms p95.
- **NFR-SEC-150**: All POSTs require ed25519 signature verifying against the GitHub-identity-bound pubkey.
- **NFR-SEC-151**: All client→server traffic HTTPS only. HSTS + secure cookies.
- **NFR-DEP-150**: Client-side: stdlib + `cryptography` under `[community-solutions]` extra (for ed25519). Viewer fetch uses stdlib `urllib`.
- **NFR-DEP-151**: Server-side: Django + django-allauth + cryptography + PostgreSQL. Free tier on a single VPS until scale forces otherwise.
- **NFR-LEGAL-20**: CC BY-SA 4.0 on submitted content (mirrors SO). Acknowledgement at submit time.
- **NFR-LEGAL-21**: GDPR Article 17 (right to erasure) supported via takedown form.
- **NFR-DOC-150**: 4 doc pages: `/docs/community/`, `/legal/privacy`, `/legal/terms`, `/legal/takedown`.

---

## 5. API surface (sketch)

### 5.1 Client (viewer)

```python
ulog.setup(
    integrity='hash-chain',
    capture_stack=True,
    bug_lookup='cache-only',
    community_solutions=True,  # opt-in
)
```

### 5.2 REST (server)

```http
POST /api/fix
Content-Type: application/json

{
  "signature": "a3f7c12...",
  "fix_text": "Increased pool_size to 25",
  "commit_sha": "abc1234",
  "language": "python",
  "frameworks": ["sqlalchemy"],
  "author_github_id": "jojo8356",
  "signed_at_iso": "2026-05-12T12:34:56Z",
  "ed25519_signature": "..."
}

GET /api/fix/a3f7c12abc...
→ { "fixes": [ {...}, {...} ], "next_cursor": null }
```

---

## 6. Implementation sketch — staged

| Stage | Scope | Months (rough) |
|---|---|---|
| 15.A | Server skeleton: Django + GH OAuth + DB schema + `/api/fix` POST/GET | 2 |
| 15.B | Client: panel + share button + ed25519 keygen + OAuth flow | 1 |
| 15.C | Public pages + search + upvotes + moderation queue | 2 |
| 15.D | Docs + privacy + GDPR + takedown procedure | 1 |
| 15.E | Self-host Docker Compose recipe + ops docs | 1 |
| 15.F | Beta with 100 users + iterate | 2 |
| 15.G | v1 public launch | 1 |

Total ~10 months calendar, single-developer. Highly contingent on ULog adoption (no point shipping without users).

---

## 7. Decisions log

| ID | Decision | Trade-off |
|---|---|---|
| D1 | Centralised hosted site, NOT federated | Simpler v1. Federation = v0.15.x candidate IF adoption justifies. |
| D2 | GitHub OAuth only (no email/password) | Cheap identity, abuse-resistant (GH bans propagate). Excludes non-GH users. |
| D3 | ed25519 signing on submissions | Tamper-evidence. Public-key-bound identity. |
| D4 | CC BY-SA 4.0 on submissions | Mirrors SO. Compatible with reuse / forks. |
| D5 | Flat reply (no comment threading) | Solutions, not discussions. Avoids forum-quality decay. |
| D6 | NO karma / reputation system | Solutions matter, not ranks. Less abuse incentive. |
| D7 | NO paid tier | Avoids product-management distraction. Donations OK. |
| D8 | Self-host Docker Compose ships from day 1 | Survives Johan moving on. Long-term insurance for users. |
| D9 | NO client telemetry | Trust foundation. Only deliberate Share-button POSTs go to server. |
| D10 | PII redaction preview before submit | Defence in depth. User stays in control. |
| D11 | Submissions are append-only + soft-delete | Audit log preserved. GDPR via takedown procedure (hard delete on request). |

---

## 8. Open questions

| ID | Question | Tentative |
|---|---|---|
| Q1 | Single VPS or managed Postgres + Cloudflare? | Single VPS for v1 (Hetzner CX21, ~6€/mo). Migrate when traffic warrants. |
| Q2 | Should the server-side embed a v0.14-style cache (auto-pull SO matches into the same DB)? | No — keep concerns separate. v0.14 is the public-source layer; v0.15 is the user-contribution layer. |
| Q3 | Multi-language UI on the public site? | English-only v1. Translation contributions accepted under CC BY-SA 4.0. |
| Q4 | RSS / Atom feed of new fixes for a signature? | Yes — `/atom/<signature>` for "watch this error". Cheap. |
| Q5 | Sentry / Datadog / Honeycomb integration to import their groups → ULog signatures? | Out of v0.15.0. Plugin-slot candidate via the `BugEntry` interface from v0.14. |
| Q6 | If a fix references a commit_sha in a private repo, what's shown? | The sha hex only; no link auto-generated. Public-repo shas get GitHub links. |

---

## 9. References

- [Source: docs/prds/PRD-v0.13-local-fix-database.md] — local layer this depends on
- [Source: docs/prds/PRD-v0.14-known-bugs-auto-lookup.md] — adjacent read-side; v0.15 is the write-side
- [SO Data Dump CC BY-SA 4.0] — the licensing precedent
- [Django + django-allauth + cryptography] — server stack baseline
- [Hetzner CX21 pricing] — infrastructure cost reality check
