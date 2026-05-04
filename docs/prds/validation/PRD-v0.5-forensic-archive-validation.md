---
validationTarget: PRD-v0.5-forensic-archive.md
validationDate: 2026-05-04
validator: bmad-validate-prd
verdict: PASS
---

# Validation report — PRD v0.5 (Forensic archive)

Target: `/home/jojokes/Documents/programmation/projets/autres/ulog-python/docs/prds/PRD-v0.5-forensic-archive.md`
Lines reviewed: 1–706 (full document).
Predecessor verdict (v0.4): `FIX_NEEDED` — see `./PRD-v0.4-commit-author-filter-validation.md`.

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
| Mesurabilité     | 9/10   | Saut majeur vs v0.4 (qui était 6/10). Tout NFR perf a budget + harness + fixture nommée. SC1-SC7 idem. Seul flou : SC6 ("≥ 100 ★ on GitHub") repose sur une recherche manuelle non-scriptée. |
| Traçabilité      | 9/10   | Persona column dans 8 tables FR. DoD §9 référence chaque FR par ID. §10 link les PRDs prédécesseurs et le brainstorming source. La matrice persona × FR est implicite mais 100 % déductible. |
| Complétude       | 9/10   | Toutes sections BMad présentes : §0 pitch, §1 vision + SC, §2 scope + non-goals + edge cases + invariants, §3 FRs SMART, §4 NFRs mesurés, §5 API sketch, §6 worked examples (6 cas, un par cluster), §7 roadmap v0.6→v1.0, §8 open questions avec recommandations, §9 DoD checklist. |
| **Moyenne**      | **9.0/10** | Premier PRD de la série qui décroche un PASS net. La leçon des validations v0.1–v0.4 a été apprise. |

---

## Findings

### BLOCKER

_None._

### MAJOR

**M1 — FR94 mentionne PostgreSQL alors que le backend PG est explicitement v0.7**
- Lignes : 276 (FR94), 625–629 (Open Q4)
- Extrait : « Per-DB write lock (`BEGIN IMMEDIATE` on SQLite, `SELECT ... FOR UPDATE` on PostgreSQL) serializes the chain. »
- Raison : §8.4 dit clairement « PG version ships in v0.7 » et recommande l'abstraction `ChainWriter`. Mais FR94 décrit déjà la stratégie PG comme livrée. Le bmad-create-epics-and-stories pourrait générer une story PG dans le sprint v0.5. Contradiction inter-sections.
- Suggestion : retirer la mention PostgreSQL de FR94 (ou la qualifier `(PG path designed, ships v0.7)`). Aligner sur §8.4.

**M2 — SC6 mesurabilité douteuse**
- Lignes : 99
- Extrait : « At least 2 reference users adopt v0.5 within 30 d of tag : qlnes + 1 new (target a public Python CLI ≥ 100 ★ on GitHub) »
- Raison : « adopt » non défini (import dans `pyproject.toml` ? un commit qui appelle `ulog.setup` ? un star sur le repo ulog-python ?). « target » est une intention, pas une mesure. Critère réellement actionnable seulement pour qlnes (Johan contrôle).
- Suggestion : reformuler en deux SCs distincts. SC6a (testable) : « qlnes lock-step migré et CI green sur ulog v0.5 dans les 30 d ». SC6b (best-effort, marqué `non-CI gate`) : « 1 PR ouverte sur un repo public listant ulog dans `pyproject.toml` ». Sépare le binaire-vrai du soft.

### MINOR

**m1 — Frontmatter manque `updated`**
- Lignes : 1–10
- Raison : `date: 2026-05-04` présent, `updated` absent. Cohérent avec v0.4 mais relevé MINOR là-bas (m6). Si `status: draft v1` évolue, on perd la trace.
- Suggestion : ajouter `updated: 2026-05-04`.

**m2 — Numérotation des sections §2.1.X vs FRs ne se croisent pas explicitement**
- Lignes : 108–213 (§2.1.1–2.1.10) et §3.1–3.8
- Raison : §2.1.4 « Query — `correlate` + `bisect` » correspond à FR101–FR104, mais ce mapping n'est pas inscrit. Pour bmad-create-epics-and-stories, c'est inférable, mais une référence explicite (`§2.1.4 → FR101–FR104`) éviterait toute ambiguïté.
- Suggestion : ajouter en fin de chaque §2.1.X une ligne `FRs: FR101–FR104`. Cosmétique.

**m3 — §2.1.10 « ~ 1 280 LOC » n'est pas justifié**
- Lignes : 106
- Raison : Le chiffrage LOC dans le titre §2.1 manque de méthode (par cluster ? par FR ?). Pour un dev solo, c'est OK. Mais c'est le seul chiffre du PRD sans méthode de mesure.
- Suggestion : soit retirer le chiffre, soit annoter `(estimate, ulog/ only — excludes web/ + tests/)`.

**m4 — §6.1 worked example avec emojis ⚡ / ▲ / ▼**
- Lignes : 451–465
- Raison : Le PRD utilise des unicode glyphs dans la sortie console attendue. Pour un test de réception du `correlate` CLI, ça force l'output exact. Sur un terminal Windows cmd.exe vintage, ces glyphs cassent.
- Suggestion : préciser dans FR101 « ASCII-safe alternate output via `--no-unicode` flag », ou annoter dans §6.1 que c'est l'apparence en TTY UTF-8.

**m5 — SC3 "≥ 30 unit tests" est un compteur, pas un critère qualité**
- Lignes : 96
- Raison : Même remarque que sur v0.4 (m4 du rapport précédent) — compter les tests n'est pas un critère de couverture. Le DoD §9 reprend le même compteur ligne 678.
- Suggestion : remplacer par « tests cover FR105–FR108 + the 8 edge cases of §2.3 ». Garder le 30 comme indicateur secondaire si on veut.

**m6 — §2.1.6 multi-track UI : 4 tracks fixes vs §7 v0.6 « configurable tracks »**
- Lignes : 175–180, 585–586
- Raison : Bon scoping (minimal v0.5, configurable v0.6). Mais FR112 dit `4 fixed tracks (level / service / author / file)` — si un user n'a pas de tag `service`, le track est vide. Comportement non spécifié.
- Suggestion : ajouter une ligne en §2.3 ou en FR112 : « tracks with zero data render as a thin grey strip with `(no data)` label ». Vraiment minor.

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

| Critère | v0.4 (FIX_NEEDED, 6.5/10) | v0.5 (PASS, 9.0/10) | Delta |
|---|---|---|---|
| Success Criteria § | Absent (BLOCKER B1) | §1.4 avec 7 SCs mesurés | **+** |
| Persona ↔ FR | Implicite | Colonne explicite dans 8 tables | **+** |
| NFR measurement | Chiffrés mais sans harness | Harness nommé partout | **+** |
| Edge cases | Zappés (BLOCKER B2 : 4 cas git) | §2.3, 8 cas avec behaviours | **+** |
| Invariants | Aucune section dédiée | §2.4, 7 invariants v1.0 freeze | **+** |
| Densité | 8/10 | 9/10 | = |
| Cohérence frontmatter | OK sauf `updated` | OK sauf `updated` (m1) | = |
| BLOCKERS | 2 | 0 | **+** |
| MAJORS | 4 | 2 | **+** |

Les 5 patterns `MAJOR` qu'on remontait depuis v0.1 sont **vraiment** corrigés — pas juste relabellisés. Le PRD assume sa filiation aux validations précédentes (§10 ligne 706) et démontre par construction qu'il a été lu.

**Régression nulle**. Aucun pattern bien traité en v0.4 n'a été dégradé en v0.5 (les non-goals restent explicites, l'API surface §5 est concrète, le DoD est trace-able).

**Reste à surveiller** : SC6 (m2) — le seul critère faible sur la mesurabilité. Et la dérive PostgreSQL FR94/§8.4 (M1) — qui pourrait piéger bmad-create-epics-and-stories en générant une story PG dans le sprint v0.5.

---

## Implementation-readiness pour `bmad-create-epics-and-stories`

**OUI, le PRD est ingestible.**

Critères vérifiés :

- 28 FRs avec IDs uniques contigus (FR90–FR117). Pas de trou.
- Chaque FR a un texte qui décrit un comportement testable (verbe + objet + condition).
- Chaque FR a ≥ 1 persona — bmad-create-epics-and-stories peut écrire des user stories `As <persona>, I want <FR>, so that <vision §1.1>`.
- §9 DoD est une checklist d'acceptance criteria mappée FR→test.
- Les NFRs sont gateables (chaque NFR a un fixture file ou un CI gate nommé).
- La seule friction est M1 (FR94 PG) — bmad-create-epics-and-stories doit lire §8.4 pour comprendre que PG est v0.7, pas v0.5. Recommandation : corriger M1 **avant** d'invoquer le break-down, sinon une story PG va apparaître par erreur.

Hors M1 : feu vert pour `bmad-create-epics-and-stories`, puis `bmad-sprint-planning`.

---

## Recommandation

**`PASS`** — le PRD passe la barre BMad. C'est le premier de la série v0.1→v0.5 à le faire.

Avant d'invoquer `bmad-create-epics-and-stories`, traiter M1 (1 minute) et idéalement M2 (5 minutes pour reformuler SC6). Les MINORS peuvent être absorbés dans le PR de tagging v0.5.0.

Pour OSS solo : ce niveau de discipline PRD est **largement** au-dessus du standard de la communauté. À ce stade, optimiser le PRD davantage relève du gold-plating — passer à l'implémentation.
