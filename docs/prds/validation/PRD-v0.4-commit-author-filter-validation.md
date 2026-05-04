---
validationTarget: PRD-v0.4-commit-author-filter.md
validationDate: 2026-05-04
validator: bmad-validate-prd
verdict: FIX_NEEDED
---

# Validation report — PRD v0.4 (Commit author filter)

Target: `/home/jojokes/Documents/programmation/projets/autres/ulog-python/docs/prds/PRD-v0.4-commit-author-filter.md`
Lines reviewed: 1–335 (full document).

---

## Score global

| Axe              | Note  | Commentaire |
|------------------|-------|-------------|
| Densité          | 8/10  | Filler quasi inexistant; quelques tirades narratives en §0/§1.1 OK pour OSS solo. |
| Mesurabilité     | 6/10  | NFR perf chiffrés. Mais pas de Success Criteria global, et plusieurs FRs ont des seuils flous. |
| Traçabilité      | 7/10  | Personas → workflows → FRs lisible. Pas de matrice user→FR explicite mais déductible. |
| Complétude       | 5/10  | Section "Executive Summary" et "Success Criteria" manquantes au sens BMad. Edge cases majoritairement zappés (file rename, ligne supprimée, squash, submodules). Sensibilité "blame-shaming" effleurée mais sans mesure concrète. |
| **Moyenne**      | **6.5/10** | Solide sur la forme, lacunaire sur les edge cases git et la mesurabilité macro. |

---

## Findings

### BLOCKER

**B1 — Aucune section "Success Criteria" mesurable au niveau PRD**
- Lignes : N/A (absente)
- Extrait : —
- Raison : BMad exige une section "Success Criteria" / "Métriques de succès" au niveau PRD, distincte des NFRs. Ici on a §1 Vision (qualitatif) puis §3 FRs / §4 NFRs ; il manque le pont "comment sait-on que v0.4 a réussi ?". Sans ça : impossible de juger si la release a atteint son but.
- Suggestion : ajouter une `## 1.4 Success Criteria` avec 3-5 critères mesurables. Ex: "≥ 90 % des `(file, line)` d'un repo standard résolus à un author non-`<unknown>`", "indexer ne dépasse pas le budget NFR-PERF-30 sur 3 repos test (qlnes, ulog-python, un repo public 100K LOC)", "0 régression de page-load sans auteur filtré actif".

**B2 — Edge cases git critiques non couverts**
- Lignes : 184-217 (FR70-FR83), 305-320 (Open questions)
- Extrait : "If a file in the records is not present in the repo... the record's author is `<unknown>`" (FR75)
- Raison : Les cas suivants ne sont traités nulle part — ni en FR, ni en non-goal explicite :
  1. **Ligne supprimée depuis** : un log émis à `foo.py:280` mais le fichier ne fait plus que 200 lignes aujourd'hui. `git blame -L 280,280` échoue. Comportement attendu ? `<unknown>` ? Fallback sur `git log --follow --diff-filter=D` ? Silence dans le PRD.
  2. **Fichier renommé** : `git blame --follow` n'est PAS mentionné. Sans `-C -M`, un rename casse l'attribution silencieusement.
  3. **Commit squashé / rebasé** : si HEAD a été squashé, le `commit_sha` cached pointe vers un sha qui peut disparaître après `git gc` → `/diff/<sha>` 404. Aucune mention.
  4. **Submodules** : un fichier dans un submodule est-il blamé contre le submodule, le superprojet, ou `<unknown>` ?
- Suggestion : ajouter une `## 2.3 Edge cases & failure modes` avec une ligne par cas + comportement attendu. Au minimum le PRD doit dire lequel des 4 cas est résolu, lequel est `<unknown>`, lequel est non-goal explicite.

### MAJOR

**M1 — Sensibilité "blame-shaming" mentionnée, pas adressée**
- Lignes : 17-18 ("blame attribution (in a kind way)"), 67-70 ("Not a vanity tool... no counts in a way that can be abused for performance review")
- Extrait : "The UI does NOT show counts in a way that can be abused for performance review."
- Raison : C'est une déclaration d'intention. Mais §2.1.2 ligne 117 affiche littéralement `Johan Nalin (johan@…) (412)` — un compteur **par auteur**. Le PRD se contredit : il dit "pas de score" et la sidebar **est** un tableau de scores trié (implicite) par volume de logs. La parade "ghost counts" (FR79) ne change pas ça.
- Suggestion : soit assumer ("counts are shown, on purpose, for debugging — see /docs/author-filter.md philosophie"), soit ajouter un FR concret : tri alphabétique forcé (pas par count), masquage des counts < N, ou flag `--hide-author-counts`. Choisir et l'inscrire en FR.

**M2 — FR81 sécurité partiellement spécifiée**
- Lignes : 209, 229
- Extrait : "Server validates the sha is reachable in `--repo`... Rejects shell-special characters in the sha (must match `[0-9a-f]{4,40}`)."
- Raison : OK pour le sha. Mais `git show <sha> -- path/to/file:line` (mentionné ligne 137) prend AUSSI un path. Le path vient du record loggé, qui peut être attaquant-contrôlé si les logs sont chargés depuis une source tierce. Pas de validation du path mentionnée (path traversal `../../etc/passwd`, option injection `--upload-pack=...`).
- Suggestion : préciser dans NFR-SEC-30 : "le path doit résoudre à un fichier tracké dans `--repo` via `git ls-files --error-unmatch` ; rejet sinon. Le path est passé via `--` separator pour éviter l'option injection."

**M3 — NFR-PERF-30 budget faiblement défensif**
- Lignes : 224
- Extrait : "Indexer adds ≤ 5 s to startup for a 100K-record DB on a 30-file repo."
- Raison : Le budget est mesurable mais le worst case n'est pas borné. Que se passe-t-il sur un repo 500-file 1M-record ? Réponse implicite "plus que 5 s" mais pas de plafond. Pour OSS ça reste tolérable, mais BMad demande typiquement un budget *et* un degraded-mode (timeout → bascule `<unknown>` ?).
- Suggestion : ajouter NFR-PERF-32 : "Au-delà de 30 s d'indexer, l'utilisateur reçoit un avertissement stderr et un prompt `--no-author-index` recommandé. Pas de timeout dur (l'opt-out est explicite)."

**M4 — FR82 cache invalidation vraisemblablement cassée**
- Lignes : 215, 311-313
- Extrait : "subsequent runs reuse the cache when the file's mtime hasn't changed"
- Raison : Le PRD reconnaît lui-même en §8.2 que `git checkout` ne touche pas toujours mtime. Donc FR82 est connu-faux par les Open Questions. Un FR ne devrait pas être contredit par une Open Question — soit on choisit la stratégie mtime et on documente la limite comme accepted, soit on choisit "key cache by file+HEAD-sha" tout de suite.
- Suggestion : remplacer FR82 par "cache key = `(file, blob_sha_at_HEAD)` via `git ls-tree HEAD -- path`. Évite la fragilité mtime, gratuit en perf." Et fermer Open Question 8.2.

### MINOR

**m1 — §3 sections sans IDs de FR contigus**
- Lignes : 188 (FR70 commence)
- Raison : FRs précédents (PRD-v0.2) vont jusqu'à FR69 ? À vérifier dans `index.md`. Si oui parfait, sinon trou dans la numérotation.
- Suggestion : vérifier la continuité avec PRD-v0.2 / v0.3.

**m2 — "Lin Wong" / "Lin Erwan" incohérence**
- Lignes : 33 ("Lin Erwan"), 78, 117, 207 ("Lin Wong")
- Raison : Deux noms pour le même persona. Cosmétique mais fait douter.
- Suggestion : choisir et `replace_all`.

**m3 — Non-goals 2.2 mélange feature-creep et limites techniques**
- Lignes : 163-179
- Raison : "co-author detection" (feature) et "mailmap normalization" (limite technique connue) sont au même niveau. Lisible quand même.
- Suggestion : sous-grouper "Out-of-scope features" vs "Known technical limitations".

**m4 — DoD ligne 332 "≥ 15 new tests" est arbitraire**
- Lignes : 332
- Raison : Compteur de tests ≠ critère de qualité. BMad préfère "tests couvrent FR70, FR74, FR75, FR81 explicitement + edge cases B2".
- Suggestion : remplacer par une matrice FR → test.

**m5 — Ligne 137 "view diff" : path-vs-sha syntaxe douteuse**
- Lignes : 137
- Extrait : `git show a3f7c12 -- path/to/file:line`
- Raison : `git show <sha> -- path` est valide ; `path:line` n'est pas une syntaxe `git show` (c'est `git blame`/`git log`). Probable confusion.
- Suggestion : `git show <sha> -- path/to/file` (le diff complet du commit sur ce fichier).

**m6 — Frontmatter manque `prevDoc`/`updated`**
- Lignes : 1-9
- Raison : `parent_prd` présent ; `updated` (date dernière modif) absent — utile quand status=draft v1 évolue.
- Suggestion : ajouter `updated: 2026-05-04` aligné sur `date`.

---

## Points forts

- §2.2 non-goals **explicites et défendus** — discipline de scope rare en draft v1.
- NFR-SEC-30 (validation sha + regex) montre une vraie réflexion sécurité.
- §1.2 "What v0.4 isn't" pose la philosophie anti-vanity tôt — c'est la bonne place.
- §6 Worked examples concrets, traçables aux FRs (search → detail view → author panel).
- §8 Open questions assumées comme questions, pas comme bugs déguisés.
- Le PRD intègre proprement les apports v0.2.1 (ghost counts) sans les redéfinir.
- FR74 fallback hors-repo (`<unknown>` + warn) est exactement ce que BMad attend pour un wrapper resilient.
- Densité globalement bonne : pas de filler corporate, pas de "leverage best-in-class".

---

## Recommandation

`FIX_NEEDED` — pas `MAJOR_REWORK` parce que la structure tient. Un passage v1→v2 qui :
1. Ajoute §1.4 Success Criteria.
2. Ajoute §2.3 Edge cases (les 4 cas git de B2).
3. Tranche M1 (assumer les counts ou les masquer — décision binaire).
4. Renforce M2 (path validation) et corrige M4 (cache key).

…et le PRD est prêt pour `bmad-create-epics-and-stories`.
