---
docType: prd-validation
validationTarget: PRD-v0.2.1-ui-bugfixes.md
validationDate: 2026-05-04
validator: bmad-validate-prd (jojo8356)
verdict: PASS
---

# Validation — PRD v0.2.1 UI bugfixes

> **Note de cadrage.** Ce PRD est un **patch release** (v0.2.1, déjà
> shipped) couvrant 3 bugs visuels du PRD parent v0.2. La barre de
> qualité BMad est ajustée en conséquence : on n'attend ni Executive
> Summary, ni vision/scope/user-journeys. On vérifie : densité,
> description bug → cause → fix → critère, FRs SMART, NFRs minimes,
> cohérence frontmatter. Verdict global : **PASS** — bon document de
> référence pour les prochains patchs.

---

## Score global

| Critère | Note | Commentaire |
|---|---|---|
| Densité | 9 / 10 | Aucun filler, chaque section porte de l'info technique. |
| Mesurabilité (FRs SMART) | 8 / 10 | FR1 et FR4 sont testables (et testés). FR2/FR3 ont des spécifications visuelles précises (`ml-2`, `0.5rem`, `tabular-nums`, `w-12`) — manque seulement un seuil pour FR3 ("≥ 4 digits"). |
| Complétude (patch context) | 9 / 10 | Bug → cause racine → fix → DoD coché. Implementation sketch présent. NFRs mesurés. Une seule lacune : pas de mention explicite "no API contract change" hors NFR-REL-1. |
| (skipped) Vision / Strategy | n/a | Patch release, hors scope. |

**Note pondérée : 8.7 / 10.** Suffisant pour être promu en référence
"comment on écrit un PRD de patch chez ulog-python".

---

## Findings

### BLOCKER

_Aucun._

### MAJOR

_Aucun._

### MINOR

#### MINOR-1 — FR3 sans seuil chiffré sur "long counts"
- **Lignes** : 105–108
- **Extrait** :
  > "When a count goes over 4 digits (e.g. `qlnes.audio.renderer 12345`),
  > the alignment breaks. Right-align the count column with a fixed
  > min-width so all rows visually align."
- **Raison** : Le seuil "over 4 digits" est utilisé pour illustrer le
  bug, pas comme critère d'acceptation. La solution (`w-12 text-right`)
  est précise mais le critère testable manque. Anti-pattern frôlé :
  "alignment breaks" sans définition opérationnelle.
- **Suggestion** : Ajouter une AC du genre _"Pour `count ∈ [1, 99999]`,
  la colonne count reste alignée à droite à `min-width: 3rem` ; les
  digits utilisent `tabular-nums` pour largeur constante."_

#### MINOR-2 — Frontmatter `status` non-standard
- **Ligne** : 7
- **Extrait** : `status: shipped v0.2.1 (4 tests added; ghost counts + spacing fixed)`
- **Raison** : Le champ `status` BMad attend un enum simple
  (`draft | review | approved | shipped | deprecated`). Ici il contient
  un changelog inline, ce qui casse le parsing automatisable.
- **Suggestion** : `status: shipped` + ajouter un champ
  `release_notes: "4 tests added; ghost counts + spacing fixed"` (ou
  laisser cette info en section dédiée).

#### MINOR-3 — DoD line 192 : "Tag v0.2.1 + push"
- **Ligne** : 192
- **Extrait** : `- [x] Tag v0.2.1 + push.`
- **Raison** : Item de release engineering mélangé à la DoD produit.
  Pas un blocker, mais brouille la frontière "ce qui valide la valeur
  livrée" vs "rituel git".
- **Suggestion** : Déplacer en section "Release checklist" séparée, ou
  laisser tel quel si la convention projet est de tout regrouper.

#### MINOR-4 — FR4 annonce 2 tests, DoD en compte 4
- **Lignes** : 110–117 (FR4) vs 184–188 (DoD)
- **Extrait FR4** : "Two new tests added to `tests/test_web.py`"
- **Extrait DoD** : "Four new tests pin the ghost-count behavior"
- **Raison** : Discrepance numérique. Visiblement le scope a doublé en
  cours d'implémentation (file_counts + jsonl adapter ajoutés). C'est
  une bonne nouvelle côté couverture, mais le PRD reste désynchronisé.
- **Suggestion** : Mettre FR4 à jour pour lister les 4 tests
  effectivement ajoutés — c'est un PRD historique, autant qu'il
  documente la réalité shippée.

#### MINOR-5 — `Bound` axis dans FR1 mais absent du sketch d'implémentation
- **Lignes** : 88–89 (FR1 table) vs 128–141 (sketch)
- **Extrait** : FR1 mentionne explicitement "Bound (auto-detected
  keys)" comme 4e axe à ghost-count, mais le code sketch ne montre que
  `where_no_levels`, `where_no_loggers`, `where_no_files`.
- **Raison** : Le PRD prescrit 4 axes mais documente seulement 3.
  Risque de fausse piste pour quelqu'un qui voudrait lire ce PRD comme
  référence.
- **Suggestion** : Soit ajouter `where_no_bound = ...` au sketch, soit
  noter explicitement que l'axe Bound est out-of-scope pour v0.2.1 et
  reporté.

---

## Points forts

- **Pitch 30s exemplaire** (lignes 20–41). Reproduit la frustration
  utilisateur réelle (Johan sur `qlnes.apu2`), nomme le pattern UX
  (Datadog/Sentry/Grafana ghost counts), et regroupe correctement les
  bugs #2 et #3 sous une cause racine commune. C'est exactement la
  densité attendue d'un patch PRD.
- **Section 1 "Root cause"** (lignes 44–73) : nomme le fichier exact
  (`ulog/web/viewer/adapters.py`), le symbole exact (`_count_by`,
  `_filter_and_paginate`), et explique en prose simple pourquoi les
  counts collapsent. Aucun lecteur futur ne se demande "où je
  cherche ?".
- **Tableau FR1 (lignes 84–89)** : matrice "ignore / apply" par axe.
  Format optimal pour une règle métier symétrique — un dev peut coder
  directement à partir de cette table.
- **Implementation sketch (lignes 121–161)** : code Python + HTML
  inline. Pour un patch, c'est le bon niveau de détail — assez pour
  guider, pas assez pour remplacer le PR.
- **NFR-PERF-1 chiffré** : "1 → 4 roundtrips, budget ≤ 500 ms sur 100K
  records". Mesurable, ni vague ni surdimensionné.
- **DoD coché à 100 %** avec preuve quantitative ("69 → 73 tests
  green"). Frontmatter status cohérent avec la DoD.
- **Pattern réutilisable** : ce PRD est un bon template pour les
  prochains patchs ulog-python — on peut s'en servir comme exemple
  canonique pour v0.2.x, v0.3.x.
