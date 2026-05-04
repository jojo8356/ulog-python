---
validationTarget: docs/prds/PRD-v0.1-core.md
validationDate: 2026-05-04
validator: bmad-validate-prd
verdict: FIX_NEEDED
---

# Validation report — PRD v0.1 (ulog-python core)

## Score global

| Critère | Note /10 | Commentaire |
|---|---|---|
| Densité | 9 | Style direct, peu de filler. Quelques tournures littéraires en intro (§0, §1) — acceptable pour un PRD OSS. |
| Mesurabilité | 6 | NFRs chiffrés mais méthodes de mesure absentes pour PERF-2/3. Pas de section "Success Criteria" business distincte de la DoD. |
| Traçabilité | 7 | Personas → cas d'usage clairs, mais FRs ne référencent pas explicitement les personas (Marco/Lin/Sara) ni les besoins §1.1 (1, 2, 3). |
| Complétude | 7 | Sections principales présentes. Manque : critères de succès mesurables (§ dédiée), méthode de bench, résolution de la contradiction ucolor. |
| **Global** | **7.25/10** | Bon premier jet. Corrections ciblées suffisent — pas de rewrite. |

---

## Findings

### BLOCKER

**B1. Contradiction dépendance `ucolor` — required vs optional**
- Lignes : 105–106 (§2.1) vs 162 (FR14) vs 189 (NFR-DEP-1) vs 313–315 (§9 Q4)
- Extraits :
  - §2.1 ligne 105–106 : « ucolor integration … Falls back gracefully if ucolor isn't installed (it's an optional dep). »
  - NFR-DEP-1 ligne 189 : « One required dep: `ucolor`. »
  - FR14 ligne 162 : « When `ucolor` is not installed, … fall through to a built-in 8-color palette »
- Raison : impossible de savoir si `ucolor` est `install_requires` ou `extras_require`. Bloque l'écriture du `pyproject.toml` (cf. DoD §10) et la sémantique de FR14.
- Suggestion : trancher en faveur de **optional** (cohérent avec FR14 + §9 Q4 + ethos zero-dep). Réécrire NFR-DEP-1 : « Zero required deps. Optional via `[color]` extra: `ucolor` (24-bit truecolor). Optional via `[json]` extra: `orjson`. »

### MAJOR

**M1. NFR-PERF-2 : pas de méthode de mesure**
- Ligne : 187
- Extrait : « Per-log-call overhead within 1.2× of stdlib `logging` for level-filtered cases »
- Raison : le format BMad attend « [métrique] [condition] [méthode de mesure] ». « 1.2× » n'est pas vérifiable sans benchmark de référence. La DoD §10 ligne 330 mentionne `BENCHMARK.md` mais le NFR ne le référence pas.
- Suggestion : « Per-log-call overhead ≤ 1.2× stdlib `logging` baseline, mesuré par `pytest-benchmark` sur `tests/bench_filtered.py` (1M calls level-filtered, médiane 5 runs), résultats consignés dans `BENCHMARK.md`. »

**M2. NFR-PERF-3 : conditions de mesure floues**
- Ligne : 188
- Extrait : « JSON formatter throughput ≥ 50K records/sec on a single core (5 fields, 100-char message, no exc_info). »
- Raison : « single core » + payload défini, mais OS, CPU, Python interpreter (CPython 3.10/3.11/3.12 ?) et stream destination (`/dev/null` vs in-memory ?) non spécifiés. Reproductibilité = 0.
- Suggestion : ajouter « CPython 3.12, stream=`io.BytesIO`, machine de référence documentée dans `BENCHMARK.md` ; CI-gated sur GitHub Actions `ubuntu-latest`. »

**M3. Section "Success Criteria" mesurables absente**
- Lignes : 0 (manquant)
- Raison : BMad attend une section "Success Criteria" distincte (objectifs business/adoption) — différente de la DoD §10 (qui est une checklist d'implémentation). Pour un PRD lib OSS : cibles d'adoption (qlnes migré sans regression, X étoiles GitHub, X downloads/mois v0.1+30j, zéro `breaking change` reporté).
- Suggestion : ajouter §3.bis « Success Criteria » :
  - SC1 : qlnes migre vers `ulog.setup()` sans changement de l'output `test_cli_audio` (byte-stable).
  - SC2 : 0 issue GitHub `bug:critical` ouverte 30 jours après tag v0.1.0.
  - SC3 : la `dictConfig`-based migration d'au moins une autre lib (ucolor, ou app jouet) validée avant v0.2.

**M4. Traçabilité FR ↔ persona/besoin manquante**
- Lignes : 137–179 (toute la table FR)
- Raison : aucun FR ne pointe vers Marco/Lin/Sara (§1.3) ni vers les 3 patterns récurrents §1.1. Lecteur doit reconstruire le lien.
- Suggestion : ajouter une colonne « Traces » ou un suffixe en italique. Exemples : FR6 (qlnes formatter) → *Marco + pattern §1.1.1* ; FR9 (json formatter) → *Lin + pattern §1.1.2* ; FR17 (library compat) → *Sara + pattern §1.1.3*.

**M5. FR1 expose la signature complète comme contrat**
- Ligne : 139
- Extrait : « `ulog.setup(level='INFO', format='qlnes', color='auto', stream=sys.stderr, name=None)` »
- Raison : pour un PRD lib, l'API EST le contrat — donc OK en principe. MAIS la signature liste 5 params dont 3 ne sont pas re-spécifiés isolément. `stream=sys.stderr` est une décision de design non justifiée (pourquoi stderr et pas stdout ?). Risque : implémenteur fige le default sans relire le PRD.
- Suggestion : extraire un sous-bloc « Default rationale » sous FR1 expliquant **stderr** (logs ≠ data, conforme 12-factor), **'qlnes'** comme default (pourquoi pas 'simple' ?), **color='auto'** (ergonomie TTY+CI).

### MINOR

**N1. Adjectifs subjectifs en intro narrative**
- Lignes : 23 (« notoriously bad »), 24 (« hostile to humans »), 31 (« sensible defaults »), 110 (« sensible defaults » bis), 253 (« absolute fastest »)
- Raison : ton OK pour la pitch §0–1, mais « sensible defaults » est répété en §2.1 ligne 110 dans le SCOPE, où la précision est attendue.
- Suggestion : remplacer ligne 110 « with sensible defaults » par « with the defaults specified in FR1 ».

**N2. §1.1 ligne 47 — chiffre non sourcé**
- Extrait : « 80 lines per project, copy-pasted with subtle bugs »
- Raison : « 80 lines » est une estimation. Pour un PRD pragmatique OSS, c'est OK, mais préciser « ~80 » ou « observed range 40–120 » signale l'estimation.
- Suggestion : « ~80 lines per project (sample: qlnes 73, ruff 91, …) ».

**N3. FR4/FR5 — `unbind` et `clear` mentionnés en passant**
- Lignes : 142, 143
- Extrait : FR4 décrit `bind()`, mentionne `unbind(*keys)` et `clear()` dans la même cellule.
- Raison : 3 capacités distinctes en un FR rend le suivi de couverture (DoD ligne 322) ambigu.
- Suggestion : éclater en FR4a (`bind`), FR4b (`unbind`), FR4c (`clear`). DoD ligne 322 « bind() / context() / unbind() / clear() working » devient alors 1:1 traçable.

**N4. §7 v0.3 « Prometheus metric increment per ERROR »**
- Ligne : 277
- Raison : OK comme vision, mais le verbe « increment » n'est pas une métrique configurable. Ambigu : compteur global ? par logger ? par module ?
- Suggestion : « Prometheus `Counter` exporter — increment a `ulog_errors_total{logger="..."}` counter per ERROR+CRITICAL record. »

**N5. §10 DoD : pas de cible de coverage tests**
- Lignes : 324–326
- Extrait : « ≥ 30 unit tests covering setup idempotency … »
- Raison : nombre de tests ≠ coverage. 30 tests peuvent couvrir 40 % du code.
- Suggestion : ajouter « `pytest --cov=ulog` ≥ 90 % line coverage, branch coverage ≥ 85 %. »

**N6. Frontmatter — `status: draft v1` non standard**
- Ligne : 7
- Raison : conventions BMad attendent typiquement `draft | review | approved | locked`. « draft v1 » mélange status et version.
- Suggestion : `status: draft` (la version est déjà en frontmatter ligne 4).

---

## Points forts

1. **Pitch §0 efficace** — 30 secondes suffisent à comprendre positionnement vs `loguru`/`structlog`. Différenciateur clair (« stdlib-rooted, no fork of logger hierarchy »).
2. **Personas concrets et nominaux** (Marco/Lin/Sara) avec scénarios shell-level — bien meilleur qu'une persona abstraite. Adapté au format lib.
3. **§2.2 Explicit non-goals** — 5 items listés avec rationale et redirection (« use stdlib's `dictConfig` if you do »). Excellent pour cadrer le scope.
4. **§6 Tradeoffs** — table comparative honnête, qui dit où ULog perd (`loguru` plus rapide à importer, `structlog` plus riche en API événementielle). Crédibilité +1.
5. **FR15** — explicite la non-interaction avec `basicConfig()` et le tag `_ulog_managed=True`. Ce niveau de précision API évite des bugs de regression. Modèle à reproduire pour FR1.
6. **§5 API surface (sketch)** — 33 lignes de code-as-spec valent 200 lignes de prose. Garder.
7. **Roadmap §7** progressive et réaliste (v0.2 async + dictConfig, v0.3 OTel, v1.0 freeze).
8. **§8 Reference users (chicken-and-egg)** — explicite que qlnes est le first-customer. Évite le syndrome « lib qui cherche un user ».
9. **DoD §10** actionnable et mesurable (à l'exception de N5).
10. **Densité** : 335 lignes pour un scope v0.1 complet — pas de gras inutile.

---

## Verdict final

**FIX_NEEDED** — 1 BLOCKER (contradiction `ucolor`) + 5 MAJOR. Aucun ne demande un rewrite ; tous sont des éclaircissements ciblés. Estimation correction : 30–45 minutes.
