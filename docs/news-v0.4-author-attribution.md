ULog — v0.4 Author attribution shipped

Cette release attaque un truc qui me frustrait depuis longtemps :
ouvrir un log et savoir tout de suite **qui a écrit la ligne de code
qui a produit ce record**. Maintenant ULog l'enrichit automatiquement
via `git blame`, et le viewer te laisse filtrer / pivoter par auteur.

Changements
- **`AuthorIndex` via `git blame --porcelain`** : chaque `(file, line)`
  d'un record résout à un `Author(name, email, sha, ts)`. Cache disque
  + mtime check → zero re-blame entre runs. Zero dépendance externe :
  pas de `GitPython`, juste `subprocess` + parsing stdlib
- **Sidebar Authors avec ghost counts** : multi-select OR, sémantique
  ghost-count v0.2.1 respectée (ticker "Lin" n'écrase pas les counts
  des autres). Filtre URL-persisté, partageable
- **`<unknown>` first-class** : checkbox "Show unknown" séparée pour
  les records dont le fichier n'est pas dans le repo. Toggle URL
  également partageable
- **Vue détail "Authored by"** : panneau dédié avec nom, email
  tronqué, short-sha 7 chars, date relative, lien "all records this
  author" + "view diff"
- **Vue `/diff/<sha>`** : `git show` rendu safe — sha validé contre
  `[0-9a-f]{4,40}` puis `git rev-parse --verify` avant tout subprocess.
  Pas d'injection possible (NFR-SEC-30)
- **CLI flags** : `--repo PATH` (override repo root), `--no-author-index`
  (skip indexing + hide sidebar), `--rebuild-author-index` (force
  rebuild du cache)
- **Sidecar cache pour JSONL/CSV** : `<logs>.authors.sqlite` créé à
  côté du fichier log non-SQL pour reuse entre lancements
- **Edge cases couverts** : fichier renommé (`git mv`), ligne hors
  range (file shrunk), commit unreachable après `git gc`, submodule,
  repo sans `.git`

En chiffres
12 stories (2.1 → 2.11 canoniques + 2.13 correct-course) · cible
NFR-PERF-30 ≤ 5 s sur 100K records / 30 files atteinte · cible
PRD-v0.4.1 page-load < 3 s atteinte après le patch perf (43K records,
de 4,2 s à < 3 s) · mypy strict + ruff + deptry + pip-audit à 0

La suite c'est **v0.5 — Forensic archive** (déjà draft) : intégrité
hash-chain sur l'archive, replay, correlate, bisect. Story 3.1 est
shippée (extension de schéma : `chain_pos`, `record_hash`, `prev_hash`,
`immutable`), reste 11 stories sur l'epic.

Repo : https://github.com/jojo8356/ulog-python
Si le projet vous intéresse une petite étoile sur GitHub ca fait
toujours plaisir.
