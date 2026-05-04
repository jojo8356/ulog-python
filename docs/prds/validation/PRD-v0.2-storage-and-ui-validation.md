---
docType: prd-validation
validationTarget: PRD-v0.2-storage-and-ui.md
validationDate: 2026-05-04
validator: bmad-validate-prd
verdict: FIX_NEEDED
---

# Validation report — PRD v0.2 (Storage + Django UI)

PRD validé contre les standards BMad (`prd-purpose.md`). Verdict global :
**FIX_NEEDED** — le PRD est riche, lisible, et techniquement solide, mais
souffre d'une absence de **Success Criteria mesurables** explicites et de
plusieurs FR/NFR où les seuils manquent ou sont subjectifs. Aucun BLOCKER
empêchant le démarrage du build, mais corrections recommandées avant le
sprint planning.

---

## Score global

| Critère          | Note  | Commentaire                                                   |
|------------------|-------|---------------------------------------------------------------|
| Densité          | 8/10  | Prose serrée. Quelques formulations conversationnelles dans le pitch (acceptable pour un §0). |
| Mesurabilité     | 6/10  | NFR-PERF chiffrés, mais FR23/FR36/NFR-REL-10/NFR-DOC-10 manquent de seuils. Pas de Success Criteria globaux. |
| Traçabilité      | 6/10  | Personas (Marco/Lin/Sara/Erwan) listés, mais aucune carte FR↔persona explicite. Le scope §2.1 ↔ FRs §3 est implicite. |
| Complétude       | 7/10  | Toutes les sections principales présentes sauf Executive Summary / Success Criteria formels. User Journey en personas-prose, pas en flows numérotés. |
| **Global**       | **6.75/10** | PRD viable, action items ciblés ci-dessous. |

---

## Findings

### BLOCKER

Aucun. Le PRD est implémentable en l'état pour un projet OSS solo.

### MAJOR

**M1. Absence d'une section "Success Criteria" mesurables**
- **Lieu** : entre §1 (Vision) et §2 (Scope) — section manquante.
- **Raison** : BMad requiert des critères de succès globaux distincts des FRs (ex. "v0.2 atteint son but si X% des testeurs trouvent leur bug en moins de Y minutes via l'UI"). Le §10 "Definition of Done" est un checklist d'artefacts, pas un critère produit.
- **Suggestion** : ajouter §1.4 "Success Criteria" avec 3–5 métriques :
  - "Un utilisateur naïf trouve une ERROR dans une DB de 10K records en ≤ 60 sec sans lire la doc (mesuré sur 3 testeurs Marco-likes)."
  - "Le pipeline `setup → run → ulog-web` fonctionne sans intervention sur les 3 OS cibles."
  - "≥ 90% des records SQLite restent inspectables après crash du host process (test fault injection)."

**M2. FR23 — seuil "sweet spot" subjectif**
- **Lieu** : ligne 191. Extrait : *"Default `batch_size=100` is the sweet spot between latency and throughput on local SQLite."*
- **Raison** : "sweet spot" n'est pas mesurable. Anti-pattern BMad (adjectif subjectif sans condition de test).
- **Suggestion** : reformuler en "`batch_size=100` ciblé pour atteindre NFR-PERF-10 (≥ 5K rec/sec) avec une perte max de 100 records en cas de crash brutal." Lier explicitement au NFR.

**M3. NFR-REL-10 — "best-effort" non testable**
- **Lieu** : ligne 280. Extrait : *"Any storage handler must survive disk-full / file-locked errors without crashing the host process — best-effort, log to stderr fallback."*
- **Raison** : "best-effort" est un échappatoire. Pas de critère d'acceptation : on teste comment ?
- **Suggestion** : "Sur injection d'erreur (`disk full`, `file locked`, `permission denied`), le handler logue 1 ligne stderr formatée `ULOG-HANDLER-ERROR: <code> <path>` et `emit()` retourne sans propager d'exception. Couverture par 3 tests `pytest` dédiés."

**M4. Traçabilité FR ↔ persona absente**
- **Lieu** : §3 entier. Personas définis §1.3, FRs définies §3, pas de pont.
- **Raison** : BMad demande que chaque FR soit reliée à un besoin user explicite (champ "user value" ou tag persona).
- **Suggestion** : ajouter une 3e colonne aux tables FR `| Persona |` (ex. FR21 → Lin/Marco, FR38 tutorial → Erwan, FR44 sectors → Marco/Lin). Ou un mini-paragraphe en tête de chaque sous-section §3.x : "Ces FRs servent <persona> qui veut <besoin>."

**M5. NFR-DOC-10 — critère d'acceptation flou**
- **Lieu** : ligne 276. Extrait : *"The `/docs` content is also published as markdown in `docs/` for offline reading; the Django app is just a renderer."*
- **Raison** : énoncé descriptif, pas une exigence mesurable. Comment valide-t-on que c'est respecté ?
- **Suggestion** : reformuler en "100% des fichiers `ulog/web/docs/*.md` sont identiques (diff vide) à ceux exposés sous `/docs/<page>` à l'exécution. Vérification via test d'intégration."

### MINOR

**m1. Manque d'Executive Summary formel**
- **Lieu** : début du document.
- **Raison** : §0 "30-second pitch" en tient lieu mais BMad nomme la section "Executive Summary".
- **Suggestion** : renommer §0 ou ajouter un H2 "Executive Summary" avant le pitch. Léger.

**m2. User Journeys en prose, pas en flows numérotés**
- **Lieu** : §1.3 (lignes 79–96).
- **Raison** : pour la partie web, BMad recommande des flows pas-à-pas (Erwan : `1. installe via pipx → 2. lance → 3. crash → 4. ouvre ulog-web → 5. ...`).
- **Suggestion** : ajouter §1.3.bis "User Flows" avec 2–3 séquences numérotées pour Marco et Erwan (les utilisateurs UI). Lin/Sara restent en prose (pas d'UI usage).

**m3. FR40 — page "sectors-and-files-explained" listée mais §7 enumère "sectors-and-files" (sans "explained")**
- **Lieu** : ligne 223 vs ligne 419.
- **Raison** : incohérence mineure de naming.
- **Suggestion** : aligner sur un seul nom (suggestion : `sectors-and-files`).

**m4. NFR-A11Y-10 — manque le scope de test**
- **Lieu** : ligne 277. Extrait : *"UI passes WCAG 2.1 AA"*.
- **Raison** : OK mais on ne dit pas avec quel outil (axe-core ? Lighthouse ? manuel ?).
- **Suggestion** : ajouter "validé par `axe-core` CI run, 0 violation critical/serious sur les 4 routes principales (`/`, `/r/<id>`, `/docs`, `/docs/quickstart`)."

**m5. §10 DoD — "≥ 60 unit tests" est un proxy de couverture, pas un critère qualité**
- **Lieu** : ligne 467.
- **Raison** : compter les tests ≠ tester intelligemment.
- **Suggestion** : remplacer par "Couverture de ligne ≥ 80% sur `ulog/handlers/*` et `ulog/web/viewer/*` (mesure `coverage.py`)." Garder le `mypy --strict` qui lui est binaire et bon.

**m6. §9.4 — "session-per-thread" formulé en open question, mais c'est un blocker thread-safety qui mérite décision avant FR23**
- **Lieu** : ligne 448.
- **Raison** : décision technique encore ouverte alors que FR23 prescrit `batch_size=100` + `atexit` flush. Si la queue+writer-thread est retenue, la sémantique d'`atexit` change.
- **Suggestion** : trancher avant d'entrer en sprint, documenter dans une mini-ADR liée au PRD.

---

## Points forts

- **Anti-goals très clairs (§1.2 + §2.2)**. Liste explicite de ce que v0.2 n'est PAS, avec roadmap des reports en v0.3+. C'est exactement ce que BMad attend pour cadrer le scope.
- **Personas concrets et nommés** (Marco/Lin/Sara/Erwan) avec scénarios d'usage réels, pas des archétypes vagues.
- **NFR-PERF chiffrés** (5K rec/sec, 500 ms, 200 ms) — directement testables.
- **Mockup textuel §6** précieux : enlève l'ambiguïté de la disposition UI sans nécessiter de Figma.
- **Cohérence frontmatter** : `parent_prd: PRD-v0.1-core.md` correctement liée, version SemVer, date à jour.
- **Pas de fuite d'implémentation problématique** : "SQLAlchemy", "Tailwind", "Django" sont OK car explicitement scoppés produit. Aucun "QuerySet.values()" ou équivalent au niveau FR.
- **Densité de prose** globalement excellente — pas de "in order to", "it is important to note", filler corporate.
- **Open Questions §9** existent et sont honnêtes, pas planquées.

---

## Action items prioritaires (ordre suggéré)

1. **M1** : ajouter §1.4 "Success Criteria" (30 min de rédaction).
2. **M4** : tagger persona dans les tables FR (1h, mécanique).
3. **M3 + M2** : reformuler les 2 NFR/FR subjectifs (15 min).
4. **m6** : trancher la question thread-safety SQL avant sprint (décision produit).
5. Reste (m1–m5) : pass éditorial groupé, 30 min.

Coût total estimé pour passer en **PASS** : ~3h de travail PRD.
