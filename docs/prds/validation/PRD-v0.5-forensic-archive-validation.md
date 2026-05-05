---
validationTarget: PRD-v0.5-forensic-archive.md
validationDate: 2026-05-04
lastVerified: 2026-05-05
validator: bmad-validate-prd
verdict: PASS
---

# Validation report — PRD v0.5 (Forensic archive)

Target: `/home/jojokes/Documents/programmation/projets/autres/ulog-python/docs/prds/PRD-v0.5-forensic-archive.md`
Lines reviewed: 1–706 (full document).
Predecessor verdict (v0.4): `FIX_NEEDED` — see `./PRD-v0.4-commit-author-filter-validation.md`.

> **Correction 2026-05-05** : revérification du rapport contre le PRD source. Trois findings retirés ou corrigés (M1, M2, m3) — voir `## Corrections` en fin de rapport. Score recalculé en conséquence.

---

## Critical context — the 5 patterns flagged on v0.1–v0.4

These were the recurring `MAJOR` patterns this PRD was explicitly written to fix. Each is rated PASS / FIX_NEEDED on its own.

| # | Pattern | Status | Evidence |
|---|---|---|---|
| **P1** | Missing Success Criteria | **PASS** | §1.4 (lines 90–100) defines SC1–SC7. Each is measurable: numeric budget + harness (`pytest-benchmark`, GitHub Actions, Playwright TTI, regex CI gate). SC4 even ships its own grep-based regression gate. SC6 is the weakest (manual GitHub check) but acknowledged as such. |
| **P2** | Persona ↔ FR traceability | **PASS** | Every FR table in §3.1–3.8 carries a `Persona` column. 28 FRs (FR90–FR117), each mapped to ≥ 1 of the 6 personas. Diego (NEW) appears on FR109/FR110, Erika (NEW) on FR92/FR93/FR95/FR97/FR107, etc. — the new personas don't sit unused. |
| **P3** | NFRs without measurement methods | **PASS** | §4 (lines 333–351). Every NFR carries an explicit harness (`pytest-benchmark median 5 runs, CPython 3.12, GitHub Actions ubuntu-latest`, `tests/bench_log.py`, Playwright TTI). NFR-SEC-50 specifies the regex `[0-9a-f]{4,64}`. NFR-DEP-50 references SC4's CI grep gate. Six PERF NFRs all have numeric ceilings and named fixture files. |
| **P4** | Edge cases (esp. git) zapped | **PASS** | §2.3 (lines 227–238) lists 8 edge cases with explicit behaviours: concurrent multiprocess writers, chain corruption, predicate raising, OTel SDK absent, resolve-on-missing-hash, double-resolve, retention-violating purge, sha256 collision. Each has a behaviour, not just a flag. |
| **P5** | Protected invariants | **PASS** | §2.4 (lines 240–257). 7 invariants I1–I7 stated as v1.0-freeze contract. Each is one-sentence enforceable (no narrative filler). I5 has a CI gate (SC5 / `test_qlnes_compat.py`). I7 (no telemetry) is the kind of invariant that's easy to lose track of — explicit here. |

**5/5 PASS.** Not just retitled sections — measurable, traceable, enforced via CI.

---

## Score global

| Axe              | Note   | Commentaire |
|------------------|--------|-------------|
| Densité          | 9/10   | 706 lignes, ~zero filler. §0 pitch dense, §1.1 cite 3 pain points concrets avec chiffrage. Quelques redondances bénignes (SC1=NFR-PERF-52, SC4=NFR-DEP-50, SC7=NFR-PERF-55) — mais le PRD le note explicitement (`(= SC1.)`), donc redondance assumée pour navigation. |
| Mesurabilité     | 9.5/10 | Saut majeur vs v0.4 (qui était 6/10). Tout NFR perf a budget + harness + fixture nommée. SC1-SC7 idem. SC6 est splitté SC6a (mécanique : tag qlnes pinné ≥ 0.5.0) / SC6b (best-effort, explicitement *non* release-blocking) — la séparation testable/soft est nette. |
| Traçabilité      | 9/10   | Persona column dans 8 tables FR. DoD §9 référence chaque FR par ID. §10 link les PRDs prédécesseurs et le brainstorming source. La matrice persona × FR est implicite mais 100 % déductible. |
| Complétude       | 9/10   | Toutes sections BMad présentes : §0 pitch, §1 vision + SC, §2 scope + non-goals + edge cases + invariants, §3 FRs SMART, §4 NFRs mesurés, §5 API sketch, §6 worked examples (6 cas, un par cluster), §7 roadmap v0.6→v1.0, §8 open questions avec recommandations, §9 DoD checklist. |
| **Moyenne**      | **9.1/10** | Premier PRD de la série qui décroche un PASS net. La leçon des validations v0.1–v0.4 a été apprise. |

---

## Findings

### BLOCKER

_None._

### MAJOR

_None._ (M1 et M2 retirés — voir `## Corrections` en fin de rapport.)

### MINOR

> **Statut 2026-05-05** : tous les MINORS m1–m6 ont été appliqués dans le PRD. Détails ci-dessous.

**m1 — Frontmatter manque `updated`** — ✅ **résolu**
- Ligne ajoutée : `updated: 2026-05-05` dans le frontmatter (ligne 6).

**m2 — Numérotation des sections §2.1.X vs FRs ne se croisent pas explicitement** — ✅ **résolu**
- Ligne italique `_FRs: FR…_` ajoutée en fin de chaque §2.1.1 → §2.1.10. Le mapping §scope ↔ §FR est désormais explicite pour `bmad-create-epics-and-stories`.

**m3 — §2.1 « ~ 1 280 LOC » n'est pas justifié** — ✅ **résolu**
- Titre §2.1 annoté : `~ 1 280 LOC of ulog implementation — estimate, ulog/ package only, excludes ulog/web/ + tests/`.

**m4 — §6.1 worked example avec emojis ⚡ / ▲ / ▼** — ✅ **résolu**
- Note ajoutée avant le bloc d'exemple : la CLI détecte `locale.getpreferredencoding()` et fait le fallback ASCII (`>>` / `<<` / `!` / `+` / `WARN`) — pas de flag nécessaire.

**m5 — SC3 "≥ 30 unit tests" est un compteur** — ✅ **résolu**
- SC3 reformulé : « every FR105–FR108 capability + the 8 edge cases of §2.3 are covered by at least one passing pytest test (≥ 30 tests as a secondary indicator) ». Mesure : `tests/coverage_matrix.md` qui liste FR/edge case → test name. DoD §9 mis à jour en miroir.

**m6 — §2.1.6 multi-track UI : tracks vides** — ✅ **résolu**
- Ligne ajoutée en §2.1.6 : « A track with zero records over the visible window renders as a thin grey strip with `(no data)` label — never a hard error or empty SVG. »

---

## Points forts

- **Frontmatter strictement conforme BMad** : `docType`, `version`, `status`, `parent_prd`, `input_session`, `author`, `date` — tous présents et corrects.
- **§0 pitch en 30 s** dense et liant directement la motivation Johan (« comprendre les erreurs de mon histoire ») aux 4 capabilities ship.
- **§1.2 "What v0.5 isn't"** : 5 négations explicites avec rationale. Discipline anti-feature-creep exemplaire pour un PRD draft v1.
- **§2.4 Protected invariants** : ce n'est pas juste une liste, c'est un **contrat de freeze v1.0**. Le « Meta-principle » (ligne 256) est l'archétype d'un design principle BMad-grade.
- **§2.3 Edge cases avec comportements explicites** — chaque edge case a une réponse, pas un « TBD ». Le cas sha256-collision (ligne 238) est traité (« theoretical, treat chain as broken at collision point ») là où la plupart des PRDs auraient zappé.
- **NFRs §4 avec harness nommé** : on ne lit pas « must be fast » nulle part. Toujours « ≤ X ms median 5 runs CPython 3.12 GitHub Actions ubuntu-latest ». C'est implementation-ready.
- **§6 Worked examples** : 6 cas, un par cluster FR. §6.5 (replay → pytest fixture) est particulièrement fort — il décrit non seulement l'usage mais le **fichier généré** (lignes 535–555). Un dev peut implémenter à partir de ça.
- **§9 DoD reference les FRs par ID** dans chaque case à cocher — le pont DoD↔FR est mécanique, pas devinatoire.
- **§10 référence explicite aux validations précédentes** (lignes 706) : le PRD assume qu'il a été écrit pour adresser des findings, et le déclare. Honnêteté méthodologique.
- **Cohérence narrative** : §0 → §1 → §2.4 → §3 → §6 → §9 racontent la même histoire de bout en bout (immutable + replay + correlate + incidents). Aucun FR orphelin.

---

## Comparaison vs v0.4 — est-ce que v0.5 progresse vraiment ?

**Oui, et c'est un saut net, pas incrémental.**

| Critère | v0.4 (FIX_NEEDED, 6.5/10) | v0.5 (PASS, 9.1/10) | Delta |
|---|---|---|---|
| Success Criteria § | Absent (BLOCKER B1) | §1.4 avec 7 SCs mesurés (SC6 splitté SC6a/SC6b) | **+** |
| Persona ↔ FR | Implicite | Colonne explicite dans 8 tables | **+** |
| NFR measurement | Chiffrés mais sans harness | Harness nommé partout | **+** |
| Edge cases | Zappés (BLOCKER B2 : 4 cas git) | §2.3, 8 cas avec behaviours | **+** |
| Invariants | Aucune section dédiée | §2.4, 7 invariants v1.0 freeze | **+** |
| Densité | 8/10 | 9/10 | = |
| Cohérence frontmatter | OK sauf `updated` | OK sauf `updated` (m1) | = |
| BLOCKERS | 2 | 0 | **+** |
| MAJORS | 4 | 0 | **++** |

Les 5 patterns `MAJOR` qu'on remontait depuis v0.1 sont **vraiment** corrigés — pas juste relabellisés. Le PRD assume sa filiation aux validations précédentes (§10 ligne 706) et démontre par construction qu'il a été lu.

**Régression nulle**. Aucun pattern bien traité en v0.4 n'a été dégradé en v0.5 (les non-goals restent explicites, l'API surface §5 est concrète, le DoD est trace-able).

**Reste à surveiller** : uniquement les MINORS (m1–m6) — cosmétiques, pas bloquants pour `bmad-create-epics-and-stories`.

---

## Implementation-readiness pour `bmad-create-epics-and-stories`

**OUI, le PRD est ingestible.**

Critères vérifiés :

- 28 FRs avec IDs uniques contigus (FR90–FR117). Pas de trou.
- Chaque FR a un texte qui décrit un comportement testable (verbe + objet + condition).
- Chaque FR a ≥ 1 persona — bmad-create-epics-and-stories peut écrire des user stories `As <persona>, I want <FR>, so that <vision §1.1>`.
- §9 DoD est une checklist d'acceptance criteria mappée FR→test.
- Les NFRs sont gateables (chaque NFR a un fixture file ou un CI gate nommé).
- FR94 défère explicitement le backend PostgreSQL à v0.7 dans son texte (« PostgreSQL backend is deferred to v0.7 (see §7 + §8.4) »), donc `bmad-create-epics-and-stories` n'a aucun signal pour générer une story PG dans le sprint v0.5.

Feu vert pour `bmad-create-epics-and-stories`, puis `bmad-sprint-planning`.

---

## Recommandation

**`PASS`** — le PRD passe la barre BMad. C'est le premier de la série v0.1→v0.5 à le faire.

Aucun blocker, aucun major. Les MINORS peuvent être absorbés dans le PR de tagging v0.5.0 ou laissés tels quels. `bmad-create-epics-and-stories` peut être invoqué directement.

Pour OSS solo : ce niveau de discipline PRD est **largement** au-dessus du standard de la communauté. À ce stade, optimiser le PRD davantage relève du gold-plating — passer à l'implémentation.

---

## Corrections (revérification 2026-05-05)

Trois findings du rapport initial du 2026-05-04 ne reflétaient pas le contenu réel du PRD. Retirés ou corrigés ci-dessous, avec preuve de l'erreur dans le rapport initial :

### M1 — supprimé (claim faux)

Le rapport initial citait FR94 comme contenant : « Per-DB write lock (`BEGIN IMMEDIATE` on SQLite, `SELECT ... FOR UPDATE` on PostgreSQL) serializes the chain. »

**Le texte réel de FR94 (ligne 277 du PRD)** est : « Per-DB write lock (`BEGIN IMMEDIATE` on SQLite) serializes the chain. **PostgreSQL backend is deferred to v0.7 (see §7 + §8.4).** »

FR94 défère déjà PG à v0.7 dans son propre texte. Aucune contradiction inter-sections. M1 fabriquait un problème inexistant.

### M2 — supprimé (claim faux)

Le rapport initial citait SC6 comme : « At least 2 reference users adopt v0.5 within 30 d of tag : qlnes + 1 new (target a public Python CLI ≥ 100 ★ on GitHub) » et recommandait de splitter en SC6a/SC6b.

**Le PRD (lignes 99–100) contient déjà SC6a et SC6b distincts** :
- SC6a : « qlnes is migrated to ulog v0.5 within 30 days of tag... Mechanically checkable. »
- SC6b : « (best-effort) At least 1 additional public adopter... Best-effort — not a release-blocking gate. »

La séparation testable / best-effort que M2 demandait est déjà implémentée. Le « ≥ 100 ★ on GitHub » que M2 cite n'apparaît pas dans le PRD.

Le commentaire « Mesurabilité » du tableau Score global a été corrigé en conséquence (note 9 → 9.5).

### m3 — référence corrigée

Le rapport initial localisait « ~ 1 280 LOC » à `§2.1.10 lignes 106`. Localisation réelle : titre de **§2.1** ligne **107** (`### 2.1 In scope (12 features, ~ 1 280 LOC of ulog implementation)`). Le finding lui-même reste valide.

### Impact sur le score

| Champ | Avant | Après |
|---|---|---|
| MAJORS count | 2 | 0 |
| Mesurabilité | 9/10 | 9.5/10 |
| Moyenne | 9.0/10 | 9.1/10 |
| Verdict | PASS | PASS (inchangé) |
| Implementation-readiness | « bloqué par M1 » | aucun blocage |
