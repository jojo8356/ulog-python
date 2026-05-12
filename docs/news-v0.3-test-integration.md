ULog — v0.3 Test integration shipped

Pas de refonte UI sur cette release, mais une grosse intégration côté
infra : ULog s'accroche maintenant à pytest, et chaque test devient
une suite de records structurés interrogeables depuis le viewer.
Voici ce qui a changé.

Changements
- **Plugin pytest auto-discover** : `pip install ulog[testing]` puis
  `pytest` — le plugin s'enregistre via l'entry-point `pytest11`, zéro
  conftest à toucher. OFF par défaut tant que `setup()` host ou
  `--ulog-db PATH` n'est pas appelé
- **Propagation `test_id`** : chaque `log.info()` / `log.error()`
  émis pendant un test inherit son `test_id` automatiquement via
  `ulog.bind()` / `ulog.unbind()` au logstart/logfinish. Plus besoin
  d'instrumenter chaque log call
- **Viewer Tests sidebar** : nouvelle section TESTS au-dessus de
  "Sectors", groupée par fichier, badges ✓/✗/⊘ + duration. Filtres
  "Failed only" et "Slowest top 10". Clic sur un test = URL filtrée
  par `test_id` (partageable)
- **Vue détail Test context** : pour un record avec `test_id`,
  panneau dédié dans `/r/<id>/` avec file:line, outcome, duration,
  phase + liens "all records this test" / "errors+warnings only"
- **CLI flags** : `--ulog-db PATH` (override destination DB),
  `--ulog-disable` (kill switch), `--ulog-summary` (ligne récap
  stderr, ON par défaut, OFF sous `-q`)
- **xdist edge cases** : SQLite WAL en local, swap silencieux vers
  JSONL sur NFS (avec warning stderr), guard contre la race
  `CREATE TABLE` quand 4 workers bootstrap en parallèle
- **API programmatique** : `from ulog.testing import test_event` pour
  les test runners non-pytest, même contrat de records émis

En chiffres
13 stories · ~180 tests verts · overhead plugin < 5 ms / test · mypy
strict + ruff + deptry + pip-audit à 0 · 2 stories correct-course
post-retro pour boucher 2 régressions découvertes au QA pass

Repo : https://github.com/jojo8356/ulog-python
Si le projet vous intéresse une petite étoile sur GitHub ca fait
toujours plaisir.
