---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - docs/prds/PRD-v0.1-core.md
  - docs/prds/PRD-v0.2-storage-and-ui.md
  - docs/prds/PRD-v0.2.1-ui-bugfixes.md
  - docs/prds/PRD-v0.3-test-integration.md
  - docs/prds/PRD-v0.4-commit-author-filter.md
session_topic: 'ulog v0.5+ roadmap features — what pushes the lib toward v1.0 freeze post-v0.4 commit-author filter'
session_goals: '30+ divergent feature candidates, clustered into must / could / wild — material for a PRD-v0.5 candidate or a re-scope of roadmap §7'
selected_approach: 'ai-recommended'
techniques_used:
  - First Principles Thinking
  - Cross-Pollination
  - Reverse Brainstorming
ideas_generated: 22
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Johan
**Date:** 2026-05-04

## Session Overview

**Topic:** ulog v0.5+ roadmap features — what pushes the lib toward v1.0 freeze post-v0.4 commit-author filter.

**Goals:** 30+ divergent feature candidates, clustered into must / could / wild — material for a PRD-v0.5 candidate or a re-scope of the existing roadmap §7.

**Tone:** technical, pragmatic, no corporate filler.

## Technique Selection

**Approach:** AI-Recommended Techniques (mode 2).

**Recommended sequence:**

- **Phase 1 — First Principles Thinking** (deep, ~10 min) — strip ulog to its foundational truth to break the implicit "ulog = stdlib + batteries" axiom. Surface the axes that are invisible because they're assumed (immutability ? temporality ? consumability ?).
- **Phase 2 — Cross-Pollination** (creative, ~15 min) — steal from adjacent tools (Sentry, Datadog, Honeycomb, Grafana, Linear, Prometheus, OTel) AND non-observability domains (git, Jupyter, Kafka, IDE debuggers, music DAWs). Target: 30–50 wild ideas, 5–10 unexpected.
- **Phase 3 — Reverse Brainstorming** (creative, ~10 min) — flip the question: "how would we make ulog WORSE ?" / "what feature would kill adoption ?" / "what would cause a fork ?" — to expose the protected invariants (what ulog must NEVER lose).

**AI Rationale:** Topic is *innovation on familiar tech* (familiar, concrete) needing strong divergence to escape the trap "v0.5 = same as v0.4 plus a bit". Combo: foundation-setting + wild divergence + stress-test.

## Phase 1 results — First Principles Thinking

5 foundational decisions captured. Each subsequent decision tightens the design space.

### [Storage / Immutability — Idea #1] : "Black Box Recorder"

*Concept* : Errors + security events are **immutable** in the ulog DB. No DELETE possible (via API, SDK, ideally enforced at SQL engine level via trigger / CHECK). Constitutes a permanent forensic history — incident registry in the "aircraft black box" sense, not rotable logs.
*Novelty* : Most logging libs treat logs as ephemeral (rotation, TTL, purge). Ulog treats them as an **append-only audit ledger** for the errors category. Two storage regimes coexist in one DB : errors + security = forever, info + debug = rotable.

### [Architecture / Scope Boundary — Idea #2] : "Scribe, not analyst"

*Concept* : Ulog provides the mechanism (immutable storage + tag schema + query) but never classifies. The app tags explicitly (`log.error("login failed", security=True, attack="brute_force")`). Ulog stays a logging lib — refuses to become a SecOps / pattern-matching / heuristic tool.
*Novelty* : Most "observability" libs grab more turf via implicit tagging (Sentry catches every exc, Datadog auto-instruments). Ulog assumes the **scribe role, not analyst role** — predictable, light, scope that never drifts.

### [Architecture / API — Idea #3] : "Immutability as policy, not as default"

*Concept* : `ulog.setup(immutable_when=callable)` — the app passes a predicate `(record) -> bool`. True → immutable store, DELETE refused. False → rotable store, purgeable. Default : `lambda r: r.levelno >= ERROR`. The `security=True` tag can be folded into the predicate by the user if they want.
*Novelty* : Most libs have a single retention policy (rotation by size/time). Ulog separates **storage class** (immutable vs rotable) as a per-record decision delegated to the app. The lib stays neutral on what "important" means.

### [Architecture / Integrity — Idea #4] : "Verifiable Black Box"

*Concept* : Hash chain at write (`record_hash = sha256(canonical_json + prev_hash)`), exposed via a `ulog verify` CLI and an integrity badge in the UI. T1 (DB-trigger only) remains as a light-mode option for apps allergic to overhead. T3 (TSA / RFC 3161) rejected — violates zero-PyPI-dep + scope creep.
*Novelty* : No mainstream logging lib (loguru, structlog, stdlib, Sentry SDK) exposes a user-side integrity verification. Ulog caps that gap for ~300 LOC while staying inside its scope. Differentiator vs Sentry/Datadog whose DBs are opaque "trust us" black boxes.

### [Consumption / Replay — Idea #5] : "Time Machine Replay"

*Concept* : `ulog.replay(filter=..., on=callback)` re-injects records back into an app pipeline (active replay), not just displays them. **Primary use case for v0.5 : regression test from a real incident** — given an error chain X that fired in prod, generate a pytest fixture that replays the records and asserts the new code-path resolves the bug. Auxiliary use cases (informational scrub UI, fuzz-replay) postponed to v0.6+.
*Novelty* : No logging lib does this. Sentry replay captures frontend DOM, not backend events. Ulog inverts : the log DB becomes a **re-executable source of truth**. Coherent extension of "aircraft black box that can replay the crash for the investigators".

---

## Phase 2 results — Cross-Pollination

10 cross-domain seeds adopted, 2 deferred to v0.6+. Each idea respects Phase 1 doctrine (scribe pas analyste, zero-dep, hash chain immutability).

### [Cross-Pollination / Investigation — Idea #6] : "Honeycomb-style Correlate"

*Concept* : Bouton UI + CLI `ulog correlate <filter>` qui calcule le **lift** (odds-ratio) de chaque tag/dimension dans le filtre vs baseline (rest of DB). Sort top 10 over et bottom 5 under-correlate. Single SQL query, ~30 LOC Python wrapper. **Self-amplifying** : valeur grandit avec la taille de l'archive, ce qui converge avec la doctrine "errors forever".
*Novelty* : Aucune lib de logging Python (loguru, structlog) ne le fait. Domaine premium-only (Honeycomb $$, Datadog $$$). ulog l'apporte gratuit, stdlib + DB locale + zero coût. Time-to-insight passe de minutes à secondes.

### [Cross-Pollination / VCS — Idea #7] : "Chain bisect"

*Concept* : `ulog bisect <pattern>` — binary search sur le chain immutable, retrouve le PREMIER record matching un pattern. La chain donne l'ordre total → bissection saine. Ressort le record + contexte commit (v0.4 author + sha + diff link). ~50 LOC.
*Novelty* : Transféré direct de `git bisect`. Mental model maîtrisé par tous les devs. Aucune lib de logging ne le fait — toutes assument scan linéaire.

### [Cross-Pollination / Finance — Idea #8] : "Incident ledger (open/closed)"

*Concept* : Errors first-class avec état. `ulog.resolve(incident_hash, by, note)` émet un record de résolution qui référence l'original par hash (chain-safe, immutability préservée). UI sépare open vs closed. CLI `ulog incidents --status open` pour ce qui saigne encore. Reopen = autre record append. Postmortem auto-généré (`ulog incidents --report --since 1m`). ~150 LOC + nouvelle table `resolutions`.
*Novelty* : Inspiré double-entry accounting. Transforme l'archive du "graveyard" en "registre apprenant". Aucun équivalent dans les libs Python.

### [Cross-Pollination / Scientific Computing — Idea #9 — DEFERRED v0.6] : "Records as Jupyter cells"

*Concept* : `ulog notebook <filter>` exporte les records matchés en `.ipynb`, chaque record = une cell `ulog.replay_record(hash="...")` modifiable. Pairs avec replay (Phase 1 #5).
*Verdict* : 🟡 defer to v0.6 — wrapper élégant SUR replay, mais bundler avec v0.5 dilue le scope. Replay doit ship d'abord, notebook s'ajoute clean en v0.6.

### [Cross-Pollination / Music DAW — Idea #10] : "Multi-track timeline"

*Concept* : UI multi-track inspirée Ableton/Reaper. Records empilés par axe de tag (service / level / author / file). Mute/solo per track. Solo = isolate, mute = exclude.
- **v0.5 minimal** (~150 LOC) : 4 tracks fixes (level / service / author / file), SVG simple, mute only.
- **v0.6 full** (+ ~450 LOC) : tracks configurables, solo, scrubber overlay (absorbe Idea #14), canvas pour scale 1M+ records.

*Novelty* : UX universellement nouvelle dans les log viewers. Sentry/Datadog/Honeycomb tous tabulaires. Multi-track est orthogonal — temporal density per dimension visible at a glance. Borrows decades of refinement from audio production.

### [Cross-Pollination / Aviation — Idea #11] : "Mandatory retention floor"

*Concept* : `ulog.setup(min_retention_days=730)` force rétention minimum sur les records rotables aussi. Refuse les purges qui violent le floor. Default = 0 (off, opt-in). ~20 LOC.
*Novelty* : Inverse le pattern habituel (libs default keep little). Hook compliance SOC 2 / GDPR Art. 30 / HIPAA en une ligne. Cheap, doctrine-aligned, ouvre l'adoption enterprise sans bloat.

### [Cross-Pollination / OpenTelemetry — Idea #12] : "trace_id auto-bind"

*Concept* : ulog auto-attache le `trace_id` OTel courant (lecture stdlib contextvars `OTEL_TRACE_CONTEXT`) sur chaque record. `ulog trace <id>` replays cross-service. Zero new dep — juste lecture contextvars. ~50 LOC.
*Novelty* : Cross-service replay = missing link en debugging micro-services. structlog le fait via processor chains manuels. ulog l'offre gratis. Killer growth feature pour adoption au-delà du solo dev.

### [Cross-Pollination / Project Mgmt — Idea #13] : "One-click issue from record"

*Concept* : Bouton UI "Open issue" sur le detail panel. Génère URL via template configurable (`ulog.setup(issue_template_url=...)`) prefilling title (record msg), body (record JSON + N records de contexte + author + commit hash), tags (level, service), assignee. Marche pour Linear / GitHub / GitLab / Jira. ~30 LOC.
*Novelty* : Sentry l'a (payant), ulog l'apporte gratis + tracker-agnostic. Combo killer avec #8 (ledger) : issue closed → webhook → `ulog.resolve()` auto. Boucle fermée prod → tracking → résolution.

### [Cross-Pollination / Bret Victor — Idea #14 — ABSORBED in #10 v0.6] : "Scrubbable timeline"

*Verdict* : 🟡 absorbé dans #10 (DAW full v0.6). Le track-mute v0.5 capture 80 % de la valeur UX à un coût d'implem 5× moindre.

### [Cross-Pollination / Postal Tracking — Idea #15 — DEFERRED v0.6+] : "Record lineage chain-of-custody"

*Concept* : Métadata sur le journey de chaque record (`emitted_at`, `verified_at[]`, `replayed_at[]`, `exported_at[]`). Audit-of-the-audit. ~80 LOC + table `record_lifecycle`.
*Verdict* : 🟡 defer to v0.6+. Doctrine borderline (analyst-y), valeur surtout compliance/forensics niche. v0.5 reste focused.

---

## Phase 3 results — Reverse Brainstorming

7 anti-features fired. Chacun expose un **invariant protégé** que ulog tiendra même au v1.0 freeze.

| # | Anti-feature (qui tankerait ulog) | Invariant exposé |
|---|---|---|
| AF1 | "ulog détecte les attaques automatiquement et tag les records" | **I1. Scribe pas analyste** — aucune classification automatique. Tagging est un acte explicite de l'app uniquement. |
| AF2 | "ulog auto-upload les records vers un cloud dashboard pour verification" | **I2. Local-first / zero-network par défaut** — ulog n'ouvre jamais de socket sans opt-in explicite. |
| AF3 | "hash chain verification requires a paid SaaS verifier" | **I3. Verification 100 % offline et gratuite** — `ulog verify` lit la DB locale, zero auth, zero account, zero payment. |
| AF4 | "ulog purge les records après 30 jours peu importe le flag immutable" | **I4. Immutabilité = contrat dur** — aucun cleanup silencieux. Le predicate `immutable_when` est respecté à 100 %, jamais contourné. |
| AF5 | "ulog ships un package `ulog2` qui breaks la stdlib `logging.getLogger()` compat" | **I5. Stdlib compat forever** — `logging.getLogger(__name__).info(...)` continue de marcher dans toutes les versions ulog, pour toujours. |
| AF6 | "chaque log call doit être taggé (no plain `log.error('oops')` allowed)" | **I6. Ergonomics-first** — les calls untaggés marchent. Tagging est opt-in pur. La barrière à l'entrée reste = stdlib. |
| AF7 | "ulog.setup() phones home pour telemetry de l'usage" | **I7. Zero phone-home** — ulog observe l'app du user, jamais le user. Aucune télémétrie collectée par la lib. |

**Pattern émergent — meta-principe v1.0 freeze contract :**

> **ulog est un outil que l'utilisateur contrôle entièrement. Il ne dépasse jamais la limite "scribe local-first ergonomique stdlib-compatible".**

Toute future feature qui viole un de ces 7 invariants est rejetée d'office. Cette phrase devient la **boussole v1.0**.

---

## Phase 4 — Final clustering & v0.5 scope crystallized

### MUST — ship en v0.5 (12 features, ~1280 LOC d'implem ulog)

| Feature | Origin | LOC est. |
|---|---|---|
| Black Box immutable storage (per-record `immutable_when` predicate) | P1 #1 + P1 #3 | 150 |
| Scribe philosophy enforced (no auto-classify ever) | P1 #2 + P3 I1 | doctrine |
| Hash chain + `ulog verify` CLI + UI integrity badge | P1 #4 | 300 |
| Replay → primary use case = regression test | P1 #5 | 200 |
| `ulog correlate <filter>` (lift sur tags) | P2 #6 | 150 |
| `ulog bisect <pattern>` (binary search chain) | P2 #7 | 50 |
| Incidents ledger (`ulog.resolve()`, `ulog incidents --status open`) | P2 #8 | 150 |
| Multi-track UI minimal (4 fixed tracks, mute) | P2 #10 | 150 |
| `min_retention_days` floor | P2 #11 | 20 |
| OTel `trace_id` auto-bind + `ulog trace <id>` | P2 #12 | 50 |
| Issue button (URL template) | P2 #13 | 30 |

### COULD — defer to v0.6+

- Jupyter notebook export (P2 #9)
- Multi-track UI full + scrubber (P2 #10 v0.6 + P2 #14 absorbed)
- Lineage chain-of-custody (P2 #15)

### WILD — explicitly out of scope

- TSA / RFC 3161 signing (T3 from Phase 1 drill — viole zero-dep + scope creep)
- ML-based anomaly detection (viole I1)
- Cloud upload / SaaS verifier (viole I2/I3)
- Auto-tagging heuristics (viole I1)

### REJECTED — 7 protected invariants from Phase 3

I1 Scribe pas analyste · I2 Local-first / zero-network · I3 Verification offline · I4 Immutability hard contract · I5 Stdlib compat forever · I6 Ergonomics-first / untagged works · I7 Zero phone-home

---

## Session conclusion

**Total ideas captured** : 5 (Phase 1) + 10 (Phase 2) + 7 invariants (Phase 3) = **22 captured directives**. 2 ideas deferred (P2 #9, #15), 1 absorbed (P2 #14).

**Output artifact** : `docs/prds/PRD-v0.5-draft-scope.md` — pre-PRD scope ready for ingestion by `/bmad-create-prd`.

**Next step recommended** : `/bmad-create-prd` invocation in a fresh context, pointing at the draft scope. The draft scope already satisfies the BMad PRD validation requirements that were missing in v0.1–v0.4 (Success Criteria section, persona traceability, NFR measurement methods).


