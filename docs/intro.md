Salut tout le monde, je viens vous partager **ULog**, un projet que je
développe en solo depuis cet été.

C'est un **système de logging universel cross-langages** : tes logs
s'écrivent dans un format wire commun (SQLite + JSONL + CSV), et un
viewer browser local les visualise tous, peu importe le langage qui
les a produits. Zéro infra, zéro cloud, MIT.

Le marché du logging actuel a deux extrêmes :

1. **Une lib par langage** (Pino en JS, zap en Go, structlog en
   Python) où tu finis par `cat / tail / grep` des fichiers.
2. **Une SaaS hébergée** (Datadog, Splunk, Grafana Cloud) à 30-300 €
   /mois qui envoie tes données ailleurs.

Personne n'occupe le milieu : **logs locaux + UI moderne +
multi-langages dans le même viewer**. C'est là que ULog se place.

Le format wire est figé depuis la v0.2 — c'est le contrat universel.
La libe Python (`ulog-py`) est la première implémentation et tient
sur zéro dépendance runtime. Les ports satellites (`ulog-js`,
`ulog-go`, `ulog-rs`) viennent ensuite. **Le viewer est
langage-agnostic dès aujourd'hui** : il consomme le format, pas le
langage. Roadmap target ≥ 3 langages portés avant tag v2.0.

Pour la pitch détaillée de la vision multi-langages, voir
https://github.com/jojo8356/ulog-python/blob/main/docs/vision-cross-language.md.

## Stack actuelle

- **Python 3.10+** pour la première lib (stdlib `logging`-compatible,
  drop-in)
- **Django + Tailwind** pour le viewer web local
- **SQLAlchemy 2.0** optionnel pour le handler SQL
- **Playwright** pour les tests e2e
- **pytest plugin** auto-discoverable via entry-point
- **mypy --strict + ruff + deptry + pip-audit** verts à zéro erreur
- Cible v0.5 : intégrité hash-chain pour archive forensique
  (HIPAA / SOC2 lite)
  
## Où en est le projet

- **v0.1** : core API (4 formatters, contextvars binding, ucolor) —
  shipped
- **v0.2** : storage handlers (SQL / JSONL / CSV) + Django inspection
  UI — shipped
- **v0.2.1** : ghost counts + sidebar polish — shipped
- **v0.3** : pytest plugin + test integration UI — draft v1
- **v0.4** : git-blame author enrichment + sidebar "By author" —
  draft v1
- **v0.5** : forensic archive (immutable chain, replay, correlate) —
  draft v1
- **v0.6-v0.8** : static-export, test-execution-stack, modern
  frontend (Tailwind CLI + Alpine + HTMX) — draft v1

Tous les PRDs : https://github.com/jojo8356/ulog-python/tree/main/docs/prds.

## Snippet "hello world" en Python

```python
import ulog
ulog.setup(format='qlnes', color='auto')
log = ulog.get_logger(__name__)
log.error("boom")     # → qlnes: error: boom  (rouge sur TTY)
```

## Liens

- **GitHub (lib Python)** : https://github.com/jojo8356/ulog-python
- **Vision cross-langages** : https://github.com/jojo8356/ulog-python/blob/main/docs/vision-cross-language.md
- **PRD roadmap** : https://github.com/jojo8356/ulog-python/blob/main/docs/prds/index.md

Ce que je cherche : **du feedback**. Sur la pertinence du créneau
(logs locaux + UI moderne + multi-langages), sur la lib Python en
elle-même, sur la roadmap, sur la DX, sur le naming, sur tout. C'est
un projet solo et j'ai besoin de regards extérieurs pour valider /
invalider les choix avant que les ports satellites soient ouverts.

Si vous êtes chauds pour porter ulog dans un autre langage
(`ulog-js`, `ulog-go`, `ulog-rs`…) je suis aussi très preneur.

Une petite étoile sur GitHub aide à attirer d'autres devs sur le
projet.
