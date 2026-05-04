---
validationTarget: docs/prds/PRD-v0.3-test-integration.md
validationDate: 2026-05-04
verdict: FIX_NEEDED
---

# Validation report — PRD v0.3 (Test integration)

## Score global

| Axe | Note /10 | Commentaire |
|---|---|---|
| Densité | 8 | Pas de filler corporate. Quelques redites entre §0, §1.1, §2.1.1 (le pitch et le scope racontent deux fois la même chose). |
| Mesurabilité | 5 | NFRs ont des budgets clairs (`< 5 ms`, pytest 7.0+) mais aucune méthode de mesure spécifiée. Aucun "Success Criteria" mesurable au niveau produit (réduction du temps de triage, taux d'adoption, etc.). |
| Traçabilité | 6 | Personas Marco/Lin/Iza présentes mais aucun FR ne référence explicitement le besoin user qu'il résout. Pas de matrice persona → FR. |
| Complétude | 6 | Sections requises majoritairement présentes (Vision, Scope, FRs, NFRs, DoD, Open Questions). MANQUANT : Executive Summary explicite, Success Criteria distinct du DoD, User Journeys formalisés (CI workflow), section Risques. |

**Verdict : FIX_NEEDED** — le PRD est solide pour un draft v1 et déjà très implementation-oriented (FRs concrètes, schéma JSON, hooks pytest nommés), mais il rate des standards BMad mesurables (Success Criteria, méthode de mesure NFR) et 4 anti-patterns rédactionnels.

---

## Findings

### BLOCKER

Aucun. Le PRD a assez de substance pour ne pas bloquer une implémentation, et un solo OSS peut tolérer l'absence de Success Criteria formels — mais il faut au moins le signaler.

### MAJOR

| # | Ligne | Extrait | Raison | Suggestion |
|---|---|---|---|---|
| M1 | — (manquant après §1) | — | **Pas de section "Success Criteria" mesurable au niveau produit.** Standard BMad : un PRD doit pouvoir répondre à "comment on saura que v0.3 a réussi ?" indépendamment du DoD. Le DoD §9 est une checklist d'implémentation, pas un critère produit. | Ajouter §1.4 "Success Criteria" : ex. "un dev avec un test failing trouve le record incriminé en ≤ 2 clics", "≥ 1 utilisateur externe ouvre une issue/PR sur la feature dans les 60j post-release", "overhead pytest ≤ 5ms mesuré sur la suite ulog elle-même". |
| M2 | 257 | `NFR-PERF-20 : Plugin overhead < 5 ms per test` | **Métrique sans méthode de mesure.** Comment on mesure 5ms ? Quel hardware ? Quelle taille de test ? Anti-pattern BMad : NFR non vérifiable. | Reformuler "métrique + condition + mesure" : ex. "p95 overhead < 5 ms par test, mesuré sur un test no-op (`def test_noop(): pass`) avec le SQL handler en mode batch, sur la CI GitHub Actions ubuntu-latest". |
| M3 | 261 | `xdist on Windows is the trickiest case... fall back to JSONL if xdist + sqlite combination is detected` | **Décision de design enfouie dans un NFR.** Le fallback JSONL automatique change le contrat du plugin et n'apparaît dans AUCUN FR. Risque de fuite implémentation + non-traçabilité. | Soit promouvoir en FR (ex. FR70 : "Si xdist détecté + sql handler → log warning + auto-switch vers jsonl handler"), soit déplacer en Open Question (§8) et trancher avant implémentation. |
| M4 | 70-83 | Personas Marco / Lin / Iza | **Aucune traçabilité persona → FR.** BMad demande que chaque exigence pointe sur un besoin user. Là, on a 3 personas et 19 FRs sans lien explicite. | Ajouter colonne "Persona" dans les tables FR, ou matrice de traçabilité §3.6. Iza (flake / `--count=10`) n'est servie par AUCUN FR explicite — soit ajouter un FR pour la distinction `iteration`, soit la sortir du scope. |
| M5 | 105-108 | `--ulog-db PATH` ... `--ulog-disable` | Mentionnés en §2.1.1 ET formalisés en FR67/FR68 ; mais §2.1.6 introduit `--ulog-summary` (FR69) avec un comportement par défaut qui contredit FR52. **FR52 dit "OFF par défaut sauf setup OU --ulog-db"** → si plugin OFF, comment `--ulog-summary` peut-il être "default ON" (ligne 249) ? | Clarifier : `--ulog-summary` est ON par défaut **uniquement quand le plugin est actif**. Reformuler FR69 explicitement. |
| M6 | 220 | FR55 : `test_id ... + parametrize_id` | **Décision en conflit avec Open Question 2** (ligne 371-375). FR55 affirme un format, OQ2 dit "v0.3 keeps the conservative nodeid-only form" — c'est cohérent, mais "nodeid-only" inclut-il le `[True-1]` ou pas ? Ambiguïté résiduelle. | Trancher : "test_id = nodeid complet pytest, incluant suffixe parametrize, traité comme chaîne opaque en v0.3. Un champ `params` structuré arrive en v0.4." |

### MINOR

| # | Ligne | Extrait | Raison | Suggestion |
|---|---|---|---|---|
| m1 | 7 | `status: draft v1` | Format frontmatter cohérent avec consigne, mais `version: 0.3.0` dans la même frontmatter pour un draft est trompeur (suggère release-ready). | Utiliser `version: 0.3.0-draft.1` ou ajouter `release_status: pre-release`. |
| m2 | 117 | `"level":"INFO\|ERROR"` | Notation pipe ambiguë dans un schéma JSON (pas de syntaxe legit). | Reformuler en prose : "level vaut INFO si outcome ∈ {passed, skipped}, ERROR si outcome ∈ {failed, errored}". |
| m3 | 184 | `412 tests, 409 passed, 3 failed, 0 skipped` | Exemple sympa mais pas de spec sur le format exact (séparateur, ordre, pluralisation). | Soit accepter "indicatif", soit figer le format dans FR69. |
| m4 | 231 | FR61 : `the plugin scopes the bind to the entire pytest_runtest_protocol` | Léger leak d'implémentation (nom de hook pytest dans une FR). Acceptable ici car le plugin EST une intégration pytest, mais à surveiller. | OK en l'état pour OSS. |
| m5 | 322 | `⊘ test_legacy             skip` | Glyphes Unicode dans le mockup — vérifier rendu cross-terminal/font web. | Mineur, juste à valider en QA. |
| m6 | 394 | `≥ 25 new tests` | Anti-pattern BMad léger : "≥ 25" sans justification (pourquoi pas 15 ou 50 ?). Pour un solo OSS c'est OK comme rough target. | Acceptable, sinon préciser "≥ 1 test par hook + ≥ 1 par CLI flag + xdist scenarios". |
| m7 | 365-381 | Open questions §8 | 4 questions ouvertes, aucune ne bloque, mais OQ1 (`capture stdout`) et OQ3 (`xdist NFS`) ont un impact UX. | Trancher OQ1 avant impl (impact sur le schéma). OQ3 OK à laisser ouvert. |
| m8 | — | Aucun anti-pattern lexical détecté ("multiple", "several", "various", "robust", "scalable") — propre. | RAS. | — |
| m9 | — | Pas de section "Risques" / "Assumptions". | Pas standard BMad strict, mais utile : ajouter §10 "Risques" (ex. xdist+SQLite sur NFS, perf overhead réel sur grosse suite, conflit avec autres plugins pytest). | Optionnel. |

---

## Points forts

1. **Pitch §0 excellent** — 30 secondes, problème → solution → 3 étapes. Modèle à reproduire pour les autres PRDs.
2. **FRs concrètes et numérotées** — 19 FRs (FR51-FR69), tables propres, descriptions actionables. Bien au-dessus de la moyenne d'un draft v1.
3. **Non-goals explicites §2.2** — 6 deferred items avec versions cibles (v0.4, v0.5). Excellent pour cadrer le scope.
4. **API surface §5** — exemples conftest + API programmatique, ça aide énormément un dev qui implémente.
5. **DoD checklist §9** — concrète, vérifiable, ferme bien le PRD.
6. **Open questions assumées** — les 4 questions §8 sont honnêtes, pas du bullshit "à clarifier plus tard". OQ1 et OQ2 ont même un "lean: yes/no" qui montre le doc est vivant.
7. **Cohérence avec l'ADR (parent_prd)** — référence claire à v0.2 storage+UI, le bind/unbind via contextvars présuppose v0.1 → la chaîne de dépendances est tracée.

---

## Implementation-readiness

**Verdict : implementation-ready à 80%.** Un dev (toi en l'occurrence) peut commencer à coder demain en démarrant par FR51-FR58 (plugin + recording), parallèlement aux FRs UI. Les 20% manquants :

- **Trancher OQ1** (capture stdout) — impacte le schéma JSON (lignes 115-119) et donc les requêtes UI.
- **Trancher OQ2** (params field) — décision frontière avec v0.4 mais doit être figée pour la stabilité du `test_id`.
- **Décider du fallback JSONL xdist** (M3) — design decision, pas juste un NFR.
- **Ajouter Success Criteria mesurables** (M1) — sinon impossible de dire "v0.3 est shipped et un succès" autrement que "le code marche".

Ces 4 items se règlent en 1h de travail. Après ça, le PRD passe en `ready-for-impl`.
