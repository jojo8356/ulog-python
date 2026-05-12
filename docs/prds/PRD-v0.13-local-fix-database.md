---
docType: prd
project_name: ulog-python
version: 0.13.0
date: 2026-05-12
author: jojo8356
status: draft v1
parent_prd: PRD-v0.5-forensic-archive.md
related_prd:
  - PRD-v0.12-call-stack-tracing.md
---

# ULog v0.13 — Local fix database (per-error solutions ledger)

> When a dev resolves an error / warning, they tag the record with
> a **"Fix" entry** describing what they did. The fix is stored
> with a content-addressable hash of the original error signature
> (msg + stack hash). Next time the **same** error fires (same
> signature), the viewer auto-links to the prior fix: "✓ Resolved
> 12 days ago by Lin: increased pool size to 25 (see commit
> a3f7c12)". Project-local memory, no network.

---

## 0. 30-second pitch

You debug an error today. You fix it. 6 weeks later, the same error
fires again — different deployment, different user, same root cause.
You spend 40 minutes rediscovering the fix because nobody on the team
remembers and the commit message says "fix bug".

v0.13 collapses this to: **the record shows "✓ Resolved 6 weeks ago
by you: tuned the cache TTL"** at the top of its detail view, with
a link to the original record, your write-up, and (optional) the
commit sha. The dev who fixed it is found by `git blame` (v0.4
machinery). The repeat detection is content-addressable: same
canonical msg + same stack hash (v0.12) → same fix link.

No external service. SQLite sidecar `<db>.fixes.sqlite` (mirrors
v0.4's authors-sidecar pattern). 100% local. v0.15 layers a
community site on top.

---

## 1. Vision

### 1.1 Why this exists

Three observations from "we hit this same bug a year ago":

1. **Tribal knowledge evaporates.** Even on a team of 3, "Lin fixed this last quarter" is a fragile cache. Slack messages get archived; commit messages stay terse. The error-to-fix link should live next to the error.
2. **Repeated errors are signal, not noise.** Currently the viewer treats two emits of `log.error("connection pool exhausted")` as two unrelated rows. With a fix-link annotation, the second one is "known incident, here's the fix" — triage time drops to 0.
3. **The chain (v0.5) + stack (v0.12) already produce a stable error signature.** `sha256(canonical(msg) + stack_hash)` is the natural primary key. We just need a small ledger table and a write-side UX.

### 1.2 What v0.13 isn't

- **Not a ticket tracker.** No assignees, no status workflow, no comments thread. Single field: "what did you do to fix it?".
- **Not a community site.** Local to the project. v0.15 ships the online layer.
- **Not auto-resolved.** Fixes are explicit user input. v0.13 doesn't pattern-match "this looks like the timeout bug, here's the fix from v0.7".
- **Not a code-change tracker.** Linking to a commit sha is optional. The fix WRITE-UP is the load-bearing artefact.
- **Not anonymous.** Author = git author email (v0.4 indexer). No opt-out (locally — your DB stays on disk).

### 1.3 Target users

- **Lin** (carried, pipeline integrator) — has fixed the "S3 connection pool exhausted" bug 4 times in 2 years. With v0.13: writes the fix ONCE, future hits auto-link.
- **Marco** (carried, solo dev) — his future self will thank him. Fix-link survives across machine moves.
- **NEW: Riad**, junior dev onboarded into the team — opens the viewer, sees `✓ Resolved 3 months ago by Lin: ...` on every error. The repository of past fixes IS his onboarding material.

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | Resolving a record takes 3 actions: click the record → click "Resolve" → write 1+ sentences → submit | yes |
| SC2 | Repeat detection: a NEW record with the same error signature auto-shows the prior fix banner | yes |
| SC3 | Fix author resolved via v0.4's git-blame email (no manual entry) | yes |
| SC4 | Sidecar SQLite `<db>.fixes.sqlite` works on JSONL/CSV sources too (mirrors A3) | yes |
| SC5 | CLI `ulog fix list / show / unresolve` for shell-side triage | yes |
| SC6 | Fix records survive v0.5's chain mode (they're in a SIDECAR, untouched by `verify`) | yes |
| SC7 | A "view-only" viewer mode where Resolve buttons are hidden (compliance read-mode) | yes |

---

## 2. Scope (v0.13)

### 2.1 In scope (10 features, ~ 600 LOC)

1. **Error signature**: `sha256(canonical_msg + stack_hash)`. Canonical msg = the msg with numeric runs replaced by `<N>` and quoted strings replaced by `<S>` (e.g. `"connection failed after 5 retries to host 'db1'"` → `"connection failed after <N> retries to host <S>"`).
2. **`fixes` table** in sidecar `<db>.fixes.sqlite`: `(signature TEXT PK, fix_text TEXT, author_email TEXT, author_name TEXT, commit_sha TEXT NULL, original_record_id INTEGER, resolved_at TEXT)`.
3. **`/fix/<signature>/` resolve form** — 1 textarea ("What did you do?"), optional commit sha, optional pre-filled author (from git blame).
4. **Detail-view "Fix" banner** — when the current record's signature is in the fixes table, render an emerald banner at the top: `✓ Resolved <relative-date> by <author>: <fix excerpt>` + "view full fix" link.
5. **Records-list inline marker** — small `🩹` icon (lucide `bandage`) on records that have a known fix. Filter axis "show only resolved" / "show only unresolved errors+warnings".
6. **CLI subcommands**: `ulog fix resolve <record_id>` (interactive prompt), `ulog fix list`, `ulog fix show <signature>`, `ulog fix unresolve <signature>`.
7. **Signature collision warning** — if a user resolves a signature already resolved (by them or someone else), warn + offer to APPEND or REPLACE. Default APPEND (history preserved).
8. **Fix history** — `fixes` table has `version INTEGER` so multiple writes accumulate. Detail view shows the LATEST by default, "view history (N)" toggles older entries.
9. **Read-only viewer mode** — `--read-only` flag hides Resolve buttons. For compliance shipped DBs.
10. **Doc page `/docs/fix-database/`** + an example walkthrough.

### 2.2 Explicit non-goals (deferred to v0.13.x+ or never)

- **Network sync** — out. Local-only. v0.15 ships the online layer.
- **Pattern-based suggestion** ("this looks like that other bug") — out. v0.14 candidate.
- **Workflow state** (open / triaging / resolved) — out forever. ULog is not Jira.
- **Comments thread** — out. The textarea IS the thread; if you need more, link to a ticket.
- **Cross-project fix import** — out. v0.13 is per-project. v0.15 handles cross-project via the community site.
- **AI-generated fix suggestions** — out forever.

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Resolve a record with no stack (v0.12 disabled or pre-v0.12 record) | Signature falls back to `sha256(canonical_msg)` only. Less precise, still works. |
| Two records with the same signature emitted 5 ms apart | One Fix entry, applies to both. The banner shows on both. |
| Records-list filter "unresolved errors+warnings" finds 10K records | Paginates as normal; sidebar count is computed via LEFT JOIN. |
| Git blame unavailable (no `--repo`) | Author defaults to `"local-user"` (from `os.getlogin()`). Manual override field in the form. |
| The DB chain (v0.5) is corrupted | Fixes survive: they're in the SIDECAR. `ulog repair` doesn't touch `.fixes.sqlite`. |
| The user types a 500-page write-up | Textarea cap at 64 KB (v0.13.1 may relax — likely never needed). |
| Two devs resolve the same signature in parallel (race) | Optimistic concurrency: both writes land as separate `version` rows. UI shows newest first, both accessible via history. |
| Resolve a record THEN the original record gets purged via `ulog purge` | Fix entry orphan: `original_record_id` becomes a dangling FK. Banner still works (signature is the load-bearing key). |
| Read-only mode + user clicks "Resolve" via URL trick | Backend re-checks `read_only`; returns 403. Defence in depth. |

### 2.4 Protected invariants

- **I5 (carried):** Logging API unchanged.
- **I15 (new):** The fix database is ALWAYS a sidecar SQLite. Never bolted onto the main `logs` table. Preserves chain integrity.
- **I16 (new):** Fix entries are append-only (no DELETE). `unresolve` flips a `void` flag — original text preserved for audit.

---

## 3. Functional Requirements

- **FR191**: `error_signature(canonical_msg, stack_hash) -> str` (64-char hex sha256). Stored in `logs.signature` (NEW column, populated at emit time).
- **FR192**: `canonical_msg(msg) -> str` normaliser: numeric runs → `<N>`, quoted strings (`"…"` / `'…'`) → `<S>`, GUIDs/UUIDs → `<UUID>`.
- **FR193**: `<db>.fixes.sqlite` schema: `fixes(signature, version, fix_text, author_email, author_name, commit_sha, original_record_id, resolved_at, void INTEGER DEFAULT 0)`. PK: `(signature, version)`.
- **FR194**: `/fix/<signature>/` form — POST writes a new `version` row. GET shows the latest non-void + history toggle.
- **FR195**: Detail view: if a NON-VOID fix exists for the record's signature, render emerald banner at the top with the fix excerpt + "view full fix" + "view history (N)".
- **FR196**: Records-list filter axis `?resolved=yes|no|any`. Default `any`. Sidebar count via LEFT JOIN on signature.
- **FR197**: CLI: `ulog fix resolve <record_id> [--text "..."] [--commit-sha SHA]`; opens `$EDITOR` if `--text` omitted. `ulog fix list [--format text|json]`. `ulog fix show <signature> [--all]`. `ulog fix unresolve <signature> [--why "..."]`.
- **FR198**: `--read-only` flag on `ulog web ./logs.sqlite --read-only`: hides Resolve buttons + 403s POST to `/fix/<signature>/`.
- **FR199**: Doc page `/docs/fix-database/` covering: signature mechanics, normaliser examples, sidecar vs main DB, read-only mode, CLI cheatsheet.

---

## 4. Non-Functional Requirements

- **NFR-PERF-140**: Signature computation ≤ 50 µs per emit (stdlib hashlib + regex).
- **NFR-PERF-141**: Banner lookup on detail view ≤ 5 ms (single-row PK lookup in sidecar).
- **NFR-DEP-130**: SQLAlchemy already pinned via `[storage]`. Zero new deps.
- **NFR-SEC-130**: Fix text is rendered with full HTML escape. `<script>` / `<img onerror>` neutralised. Markdown? Out of v0.13 — plain text only.
- **NFR-DOC-130**: Doc page with canonical-msg examples + a "how the signature collides on parametrised errors" worked example.

---

## 5. API surface (sketch)

### 5.1 Resolve via CLI

```bash
ulog fix resolve 142071
# Opens $EDITOR; first line = "What did you do?"
# Saves to <db>.fixes.sqlite with signature derived from record 142071.

ulog fix list
#  SIG (8)   RESOLVED_AT          AUTHOR             EXCERPT
#  a3f7c12…  2026-04-01T12:00Z   lin@team.io        "Increased pool size to 25"
#  b9e2d44…  2026-03-12T09:30Z   marco@team.io      "Added retry-on-503"
```

### 5.2 Web UI

```
GET /r/142071/   → "✓ Resolved 2 months ago by Lin: 'Increased pool size to 25' [view full]"
GET /fix/a3f7c12.../   → fix detail + history toggle + (when not read-only) "Edit / Append"
GET /?resolved=no&level=ERROR   → unresolved errors only (Riad's onboarding view)
```

### 5.3 No `setup()` change

```python
ulog.setup(integrity='hash-chain', capture_stack=True, ...)
# Fix DB sidecar is created lazily on first resolve. No new kwargs.
```

---

## 6. Implementation sketch

| Story | Scope | LOC |
|---|---|---|
| 13.1 | `error_signature` + `canonical_msg` normaliser + tests | 80 |
| 13.2 | `logs.signature` column + emit-time population | 60 |
| 13.3 | `<db>.fixes.sqlite` schema + CRUD repo | 100 |
| 13.4 | `/fix/<signature>/` form + POST handler | 80 |
| 13.5 | Detail-view banner partial | 50 |
| 13.6 | Records-list `?resolved=` filter + sidebar count | 70 |
| 13.7 | `ulog fix {resolve,list,show,unresolve}` CLI | 120 |
| 13.8 | `--read-only` flag + 403 enforcement | 40 |
| 13.9 | Doc page `/docs/fix-database/` | n/a |

Total ~ 600 LOC.

---

## 7. Decisions log

| ID | Decision | Trade-off |
|---|---|---|
| D1 | Sidecar SQLite for fixes, NOT a column on `logs` | Preserves chain integrity (v0.5). Mirrors A3 (authors sidecar). |
| D2 | Signature = `sha256(canonical_msg + stack_hash)` | Collisions are intentional (same code path + same msg shape = same fix). Trade-off: parametrised errors with different shapes get separate signatures. |
| D3 | Canonical msg normaliser strips numbers/strings/UUIDs | "Failed after 5 retries" + "Failed after 12 retries" share a signature. Documented. |
| D4 | Append-only `fixes` (versioned rows) | Audit trail preserved. `unresolve` flips `void`, doesn't delete. |
| D5 | Author resolved via v0.4 git-blame email | Zero manual entry. Falls back to `os.getlogin()` when no repo. |
| D6 | Plain text fix write-ups (no markdown) | Avoid XSS surface + render complexity. v0.13.x may add markdown. |
| D7 | NO ticket workflow | Not Jira. Single textarea is the contract. |
| D8 | NO cross-project import | v0.15 community site is the right scope for that. |
| D9 | `--read-only` for compliance-shipped DBs | Same audit DB can be shared without write-side UX. |

---

## 8. Open questions

| ID | Question | Tentative |
|---|---|---|
| Q1 | Should fix entries optionally reference a v0.5 incident (when incidents ledger exists)? | Yes — `incident_id` optional FK, when v0.5 incidents land. |
| Q2 | UI for "find similar unresolved errors" (cluster by signature)? | Yes — a `/fixes/clusters/` page sorting signatures by record count, v0.13.1 candidate. |
| Q3 | Should the canonical-msg normaliser be tunable per-logger? | No — too much config surface. Project-wide constants. |
| Q4 | Records emitted before v0.13 (no `signature` column) — back-compute on viewer load? | No. Pre-v0.13 records show "no fix tracked" badge. Migration would be too expensive. |

---

## 9. References

- [Source: docs/prds/PRD-v0.5-forensic-archive.md] — incidents ledger may dovetail
- [Source: docs/prds/PRD-v0.4-commit-author-filter.md] — sidecar pattern (A3) + author resolution
- [Source: docs/prds/PRD-v0.12-call-stack-tracing.md] — stack_hash is the second half of the signature
- [stdlib `hashlib`, `re`] — chosen primitives
