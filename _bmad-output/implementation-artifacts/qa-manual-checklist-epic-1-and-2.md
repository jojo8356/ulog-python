# QA manual checklist — Epic 1 (v0.3) + Epic 2 (v0.4) + perf v0.4.1

**Goal:** vérifier visuellement dans le browser que toutes les features de v0.3 (test integration) + v0.4 (author attribution) + le perf patch v0.4.1 fonctionnent comme spec'd. Coche au fur et à mesure. Note les bugs en bas.

---

## 0. Setup

### 0.A — Génère une DB de test réaliste

```bash
cd ~/Documents/programmation/projets/autres/ulog-python
source .venv/bin/activate

# Demo DB par défaut : ~50K records, 8 auteurs, 10 fichiers de tests, 7 jours
python3 scripts/seed_demo_db.py /tmp/ulog-demo

# (option) Plus gros : 200K records, 200 tests/file
# python3 scripts/seed_demo_db.py /tmp/ulog-big --records 200000 --tests-per-file 200
```

Vérifier que le script imprime :
```
=== Building synthetic git repo at /tmp/ulog-demo ===
  28 source files, 8 authors, ~9000 total lines
=== Generating log DB at /tmp/ulog-demo/logs.sqlite ===
inserting 43546 records...
wrote /tmp/ulog-demo/logs.sqlite
```

- [ ] Script tourne sans erreur
- [ ] DB fait > 5 MB (`ls -lh /tmp/ulog-demo/logs.sqlite`)

### 0.B — Lance le viewer

```bash
ulog-web --repo /tmp/ulog-demo /tmp/ulog-demo/logs.sqlite
```

Attendu sur stderr (premier launch) :
```
ulog: indexing authors... 29 files, NNNN/5878 records (10%)
...
ulog: indexed 5878 records across 29 files in X.XXs
ulog-web: serving /tmp/ulog-demo/logs.sqlite (sqlite) on http://127.0.0.1:NNNNN/
```

- [ ] Stderr montre les progress lines author-indexer
- [ ] Pas de stack trace
- [ ] Browser s'ouvre sur la page (ou tu copies l'URL manuellement)

⚠️ **Si tu oublies `--repo`** → l'auto-detect va viser le repo `ulog-python` (cwd) au lieu de `/tmp/ulog-demo` → tous les records → `<unknown>` author. Symptôme : sidebar AUTHORS avec une seule entrée `<unknown> (43546)`.

---

## 1. Epic 1 — v0.3 Test integration

### 1.1 TESTS sidebar (Story 1.6 — FR62)

À gauche, **entre Files et le bloc principal de records**, tu dois voir une section "TESTS".

- [ ] La section "TESTS" est visible avec icône
- [ ] Listing groupé par fichier (ex: `tests/checkout.py`, `tests/login.py`...)
- [ ] Les **5 premiers groupes** sont **dépliés par défaut** (`<details open>`)
- [ ] Les groupes au-delà du 5ème sont **repliés** (cliquables pour expand)
- [ ] Chaque test affiche : icône d'outcome (✓/✗/🔥/⊘) + nom + duration formatée (ms / s)
- [ ] Mix d'outcomes visible : passed (vert ✓), failed (rouge ✗), errored (rouge 🔥), skipped (ambre ⊘)

**Bug récent fixé** : le commentaire `{# Test list grouped by file... #}` ne doit PAS s'afficher comme texte brut au-dessus de la section.

- [ ] Aucun texte de commentaire `{# ... #}` ou `regroup` visible dans la sidebar

### 1.2 Quick filters Tests (Story 1.6 — FR63 / FR64)

En haut du bloc TESTS, deux checkboxes :

- [ ] **Failed only** — coche → records list filtre aux tests failed/errored uniquement
- [ ] **Slowest top 10** — coche → records list filtre aux 10 tests les plus lents (par duration)
- [ ] Les 2 checkboxes peuvent être combinées (ex: failed + slowest)
- [ ] Décocher restaure la liste complète

### 1.3 Click test name → filter (Story 1.7 — FR65)

- [ ] Clique sur un nom de test dans la sidebar → URL devient `/?test_id=tests%2F...`
- [ ] La records list se filtre aux records émis pendant ce test (incluant les app records via Story 1.4 propagation)
- [ ] Le test cliqué est **visuellement distinct** dans la sidebar (background ou bold)
- [ ] Re-clique sur le même test → désélectionne (ou clique un autre test → switch)
- [ ] Avec d'autres filtres actifs (level, search), le clic test_id préserve les autres filtres

### 1.4 Detail view "Test context" panel (Story 1.8 — FR66)

Clique sur n'importe quel record qui appartient à un test (regarde le `test_id` dans le `context` column).

- [ ] Panel "Test context" présent **entre Context et Exception**
- [ ] Affiche : icône outcome + outcome name + duration
- [ ] Test ID (full path) affiché en bas
- [ ] Phase affichée (si record == outcome record : `phase: call`)
- [ ] Ligne avec count + 2 liens : "view all records for this test →" et "errors+warnings only →"
- [ ] Le link "view all" navigate vers `/?test_id=...` (la liste filtrée)
- [ ] Si record n'a pas de test_id → panel hidden complètement

### 1.5 Doc page `/docs/test-integration/` (Story 1.11)

- [ ] `/docs/test-integration/` retourne 200 et rend
- [ ] Sections présentes : Install, CLI flags, Schema, Worked example, Programmatic API, Troubleshooting
- [ ] L'exemple `conftest.py` est dans un bloc de code rendu (pas de markdown brut visible)
- [ ] Listed dans `/docs/` index
- [ ] Aucun raw `#`, `**`, ` ``` ` ne traîne dans le HTML

---

## 2. Epic 2 — v0.4 Author attribution

### 2.1 AUTHORS sidebar (Story 2.6 — FR76)

Position : **entre Files et Time range** dans la sidebar gauche.

- [ ] Bloc "AUTHORS" visible avec icône user
- [ ] 8 noms d'auteurs listés (Alice Chen, Bob Martin, Charlie Patel, Dana Wong, Erwin Schmidt, Fatima Khouri, Gao Li, Hiroshi Sato)
- [ ] Chaque ligne : nom + email tronqué `<...20 chars...>` + count à droite
- [ ] Counts ~5K records par author (Pareto-distribué)
- [ ] Entrée `<unknown>` à la fin de la liste (les ~1100 records de tests qui ont `file=pytest_plugin.py`)
- [ ] Checkbox "Show unknown" en bas (cochée par défaut, FR78)

### 2.2 Multi-select OR + URL persistence (Story 2.7 — FR77)

- [ ] Coche un seul auteur → records list filtre à cet author
- [ ] Coche **2 auteurs** → records list filtre aux records de l'un OU l'autre
- [ ] URL contient `?author=alice@globex.io&author=bob@globex.io` après submit
- [ ] Recharge la page → la sélection est preservée (URL canonical)
- [ ] Décoche tous → liste revient au full set

### 2.3 Show unknown toggle (Story 2.7 — FR78)

- [ ] Décoche "Show unknown" → records avec `<unknown>` author disparaissent de la liste
- [ ] Recoche → ils reviennent
- [ ] URL change : `?show_unknown=0` quand off

### 2.4 Detail view "Authored by" panel (Story 2.8 — FR80)

Clique un record (ex: `/r/100/`).

- [ ] Panel "Authored by" présent **entre Test context et Exception**
- [ ] Format : `<Name> <email tronqué 40 chars> · <7-char short-sha>`
- [ ] Ligne `committed X days/hours/minutes ago` (relative-date)
- [ ] 2 liens :
  - [ ] "view all records from this author →" → navigate `/?author=<email>`
  - [ ] "view diff: <short_sha> →" → navigate `/diff/<full_sha>/`

### 2.5 `/diff/<sha>/` view (Story 2.9 — FR81 / NFR-SEC-30)

Clique le lien "view diff" du panel "Authored by" depuis n'importe quel record.

- [ ] Page rend en 200 avec le diff complet (`git show <sha>`)
- [ ] Header affiche `git show <short_sha>`
- [ ] Lien "← back to records" en haut
- [ ] Le code du diff est dans `<pre>` monospace, pas de syntax highlighting (v0.4)
- [ ] Le contenu est HTML-escaped (cherche un commit avec `<` ou `>` dans le message → doit être affiché littéralement, pas interprété)

**Tests de sécurité** :

- [ ] Tape dans la barre URL `/diff/abc/` (sha trop court) → 400 Bad Request
- [ ] `/diff/abc;rm/` (caractères shell) → 400 Bad Request
- [ ] `/diff/0000000000000000000000000000000000000000/` (40 chars hex valide mais inexistant) → 404
- [ ] `/diff/../etc/passwd/` → 400 Bad Request

### 2.6 Doc page `/docs/author-filter/` (Story 2.11)

- [ ] Page rend en 200
- [ ] Sections : How it works, CLI flags, `<unknown>` semantics, Code vs commit author, Multi-select OR + URL, Worked example, Performance, Security, Troubleshooting
- [ ] Listed dans `/docs/` index
- [ ] Code blocks rendus

### 2.7 CLI flags (Story 2.2)

Test depuis terminal (Ctrl-C le serveur courant entre chaque test) :

- [ ] `ulog-web /tmp/ulog-demo/logs.sqlite` (sans `--repo`) — depuis cwd ulog-python → utilise le repo ulog-python (mauvais résultat — sidebar AUTHORS = uniquement `<unknown>` car les fichiers demo ne sont pas dedans)
- [ ] `ulog-web --no-author-index /tmp/ulog-demo/logs.sqlite` → bloc AUTHORS hidden + démarrage instantané (skip indexer)
- [ ] `ulog-web --rebuild-author-index --repo /tmp/ulog-demo /tmp/ulog-demo/logs.sqlite` → drops le cache `authors` et reblame from scratch (progress lines visibles)
- [ ] `cd /tmp && ulog-web /tmp/ulog-demo/logs.sqlite` → auto-detect échoue (pas de .git/ dans /tmp), warning stderr `no git repo detected`, sidebar AUTHORS hidden
- [ ] `ulog-web --no-author-index --rebuild-author-index ...` → erreur argparse (mutually exclusive)

---

## 3. Perf v0.4.1 (PRD-v0.4.1 — page-load < 3s)

Avec `/tmp/ulog-demo/logs.sqlite` (~43K records).

Test via curl en parallèle dans un autre terminal :

```bash
# Cible <3s sur tous les paths
time curl -sS -o /dev/null http://127.0.0.1:NNNNN/                              # cold cache
time curl -sS -o /dev/null http://127.0.0.1:NNNNN/                              # warm cache (devrait être <200ms)
time curl -sS -o /dev/null 'http://127.0.0.1:NNNNN/?level=ERROR'                # filter
time curl -sS -o /dev/null 'http://127.0.0.1:NNNNN/?author=alice@globex.io'    # author filter
time curl -sS -o /dev/null 'http://127.0.0.1:NNNNN/?page=10'                    # pagination
time curl -sS -o /dev/null 'http://127.0.0.1:NNNNN/r/100/'                      # detail view
```

- [ ] Cold cache (1er request) < 1s
- [ ] Warm cache (2e+) < 200ms
- [ ] Filter level/sector/file < 200ms
- [ ] Filter author actif < 2s
- [ ] Pagination < 200ms
- [ ] Detail view < 100ms
- [ ] Aucune réponse > 3s

**Symptôme de régression perf** : le browser "tourne" plus de 3s sur `/`. Si ça arrive, profiler côté Django ou voir s'il y a une fuite de cache.

---

## 4. Cross-epic regressions (features v0.1/v0.2 toujours OK)

- [ ] Levels sidebar (DEBUG/INFO/WARNING/ERROR/CRITICAL) avec ghost counts
- [ ] Sectors sidebar (logger names) — multi-select OR
- [ ] Files sidebar — multi-select OR
- [ ] Search msg — substring match dans les messages
- [ ] Time range filter (from/to ISO-8601)
- [ ] Bound fields filter — `?bound=tenant_id=tenant_001` filtre par contexte JSON
- [ ] Pagination (boutons précédent/suivant en bas)
- [ ] Tutorial overlay au premier launch (FR38)
- [ ] Dark mode toggle (header right) — preference persistée localStorage
- [ ] `/api/records/` retourne JSON valide
- [ ] Detail view affiche : ts, level, logger, msg, file:line, context (key:value), exception (si présent)

---

## 5. Régressions perf à surveiller

- [ ] Pas de fuite mémoire évidente (reload la page 20× → process Django reste sous 200 MB en RES)
- [ ] Pas de stderr noise répété (cherche `Logging error`, `OperationalError` dans la stderr du serveur pendant que tu navigues)
- [ ] Pas de `git blame` qui se relance si tu navigues normalement (cherche `--porcelain` dans `ps -ef` pendant la navigation, ne devrait apparaître que pendant le startup)

---

## 6. Bugs trouvés (template à remplir)

```
[ ] Bug #1
    Steps : ...
    Expected : ...
    Got : ...
    Story responsible : 2-X / 1-X / cross-epic
    Severity : blocker / high / med / low

[ ] Bug #2
    ...
```

---

## 7. Sign-off

Une fois toutes les sections passées (ou les bugs notés en §6) :

- [ ] Tu peux dire à Claude "checklist QA done, bugs : [liste]" → je file les patches
- [ ] OU "checklist QA verte 100%" → on enchaîne Epic 3 v0.5 chain integrity
