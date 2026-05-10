---
docType: prd
project_name: ulog-python
version: 0.7.0
date: 2026-05-10
author: jojo8356
status: draft v1
parent_prd: PRD-v0.3-test-integration.md
---

# ULog v0.7 — Test execution stack & timeline

> **Pitch :** pour chaque test pytest, capturer la pile d'exécution
> hiérarchique (fixtures → setup → body → teardown → sub-spans
> manuels) avec leurs durées, comme `EXPLAIN ANALYZE` en SQL.
> Visualiser dans le viewer en waterfall, identifier les bottlenecks,
> réduire le temps total de la suite.

---

## 0. The 30-second pitch

Ta suite de tests pytest dure 18s. Tu sais pas où le temps est passé.
Tu ouvres `pytest --duration=10` → tu vois "test_X = 4.2s" mais pas
**pourquoi** test_X est lent : c'est le fixture DB qui prend 3s ?
Le `git clone` du fixture ? Le sleep de 1s entre 2 retries ? La
sérialisation JSON du fixture object ?

ULog v0.7 capture cette pile automatiquement. Chaque test devient un
**arbre d'exécution timestampé** :

```
test_authors_filter (5.8s)
├─ fixture: setup_demo_repo  (3.1s)  ← BOTTLENECK
│  ├─ git init                (0.2s)
│  ├─ git commit × 8          (2.8s)
│  └─ ulog.setup              (0.1s)
├─ body                       (0.4s)
│  ├─ adapter.query           (0.05s)
│  └─ assert checks           (0.35s)
└─ teardown                   (2.3s)  ← BOTTLENECK
   ├─ ulog.clear              (0.01s)
   └─ tmp_path cleanup        (2.29s)
```

Le viewer affiche ça en waterfall sur le panneau Test detail. **Tu
vois en 1 coup d'œil** que setup + teardown = 5.4s sur 5.8s, et que
le body fait 0.4s. Décision : refactor le fixture pour partager le
git repo entre tests, gain de ~3s × N tests.

C'est `EXPLAIN ANALYZE` pour ta suite de tests.

---

## 1. Vision

### 1.1 Why this exists

L'observabilité d'une suite de tests est mauvaise par défaut. Les
outils existants (`pytest --durations`, `pytest-profiling`,
`pytest-timer`) donnent un total par test mais **pas le breakdown
intra-test**. Pour profiler intra-test, il faut sortir `cProfile` ou
`py-spy` — outil séparé, parsing manuel, aucune intégration avec le
viewer ULog.

ULog v0.3 a déjà introduit le concept de "test event records". Cette
v0.7 étend : chaque sub-opération significative (fixture, sub-call,
DB query, http call) émet un **span record** lié au test_id parent
via `parent_span_id`. Le viewer reconstruit l'arbre.

**Pourquoi ça compte** : pour les équipes avec une suite >100 tests
qui dure >5min en CI, identifier les 3 tests qui consomment 50% du
temps via un waterfall visuel = ROI immédiat. Tu refactor 3 fixtures
au lieu de chasser dans 100 tests.

### 1.2 What v0.7 isn't

- Un profiler CPU. cProfile / py-spy restent recommandés pour
  function-level CPU analysis. v0.7 capture des **opérations
  identifiées par toi** (avec un nom human-readable), pas chaque
  appel de fonction.
- Un APM (Application Performance Monitoring). Pas de aggregation
  cross-runs, pas de moyennes glissantes, pas de alerts.
- Un remplacement d'OpenTelemetry tracing. OTel = inter-service
  distribué. v0.7 = intra-test local.
- Un outil de production. C'est pour les **tests en dev / CI**, pas
  pour profiler le code prod (utilise OTel pour ça).

### 1.3 Target users (en plus des personas v0.3)

- **Lead dev / tech lead** — veut réduire le temps CI sans
  micro-optimiser à l'aveugle. Identifie les 5 tests qui coûtent 50%
  du temps total via le waterfall.
- **Junior dev** — apprend à reconnaître ce qui rend un test lent
  (fixture trop large, IO synchrone, sleep oublié).
- **CI maintainer** — corrèle le temps total CI avec les contributions
  spécifiques (commit X a ajouté un fixture qui a doublé le temps).

### 1.4 Success criteria

| SC | Description |
|---|---|
| SC1 | Pour 100% des tests d'une suite, le viewer affiche le waterfall complet (fixtures + body + teardown + sub-spans manuels). |
| SC2 | Overhead du tracking ≤ 5% du temps total de la suite (mesuré sur la propre suite ulog-python : 18s → ≤ 19s avec v0.7 active). |
| SC3 | API `with ulog.span("name"):` est trivialement ajoutable dans n'importe quelle fonction (≤ 2 lignes / opération). |
| SC4 | Le top-3 bottlenecks d'une suite (par temps cumulé) est identifiable en ≤ 30 secondes via le viewer. |
| SC5 | Cross-language : la spec span est dans le wire format → portable à `ulog-js` plus tard. |

---

## 2. Scope (v0.7)

### 2.1 In scope

#### 2.1.1 Span recording API

```python
import ulog

# Manual span
with ulog.span("db_setup") as span:
    populate_test_data()
# span.duration_s captured automatically when context exits

# Decorator
@ulog.timed
def expensive_helper():
    ...

# Or as a logger method (auto-emit a span record at __exit__)
log = ulog.get_logger("myapp.test")
with log.span("compute_features") as s:
    s.set_attr("feature_count", 100)  # custom attrs persisted in context
    compute_features()
```

Chaque `span` émet **un record `INFO` avec `logger='ulog.span'`** au
moment du `__exit__`, avec dans `context` :

```json
{
  "test_id": "tests/test_x.py::test_y",
  "span_id": "<uuid>",
  "parent_span_id": "<uuid|null>",
  "span_name": "db_setup",
  "duration_s": 3.124,
  "duration_ms": 3124.0,
  "started_at": "2026-05-10T14:32:01.001Z",
  "ended_at": "2026-05-10T14:32:04.125Z",
  "exit_status": "ok"
}
```

#### 2.1.2 Pytest plugin auto-instrumentation

Le pytest plugin (Story 1.1) est étendu pour émettre des spans automatiques :

- `pytest_runtest_setup` → span "setup" autour de l'invocation des
  fixtures.
- `pytest_runtest_call` → span "call" autour du body du test.
- `pytest_runtest_teardown` → span "teardown" autour du cleanup.
- Pour chaque fixture, **si le fixture est instrumenté** (décoré par
  `@ulog.timed_fixture` ou si auto-detect ON), un sub-span est émis.

Tous les spans héritent du `test_id` courant (ContextVar) et chaînent
leur `parent_span_id` via une stack interne.

#### 2.1.3 Viewer waterfall

Le panneau "Test context" sur la detail view (Story 1.8) gagne une
section "Execution timeline" qui rend les spans en waterfall :

```
┌──────────────────────────── 5.81s total ────────────────────────────┐
│ setup                               ████████████  3.10s              │
│   ├─ git init                       █  0.20s                         │
│   ├─ git commit ×8                  ███████████  2.80s               │
│   └─ ulog.setup                     ▌  0.10s                         │
│ call                                ██  0.40s                        │
│   ├─ adapter.query                  ▌  0.05s                         │
│   └─ assertions                     █  0.35s                         │
│ teardown                            ████████  2.31s                  │
│   └─ tmp_path cleanup               ████████  2.29s                  │
└──────────────────────────────────────────────────────────────────────┘
```

Bars sont proportionnelles au temps total. Sub-spans sont indentés.
Les spans qui dépassent un seuil rouge (configurable, default 25% du
total) sont highlightés.

#### 2.1.4 Sidebar quick-filter

Dans la TESTS sidebar (Story 1.6), nouveau filtre "Slowest spans" qui
liste les top-N spans par duration_s à travers tous les tests, pas
juste par test.

#### 2.1.5 CLI dump : `ulog explain <test_id>`

Subcommand qui dump le waterfall en text (terminal-friendly) :

```bash
$ ulog explain tests/test_authors_filter.py::test_filter_single_author --db /tmp/ulog-demo/logs.sqlite
test_authors_filter (5.81s)
├─ setup                       3.10s  53.4%
│  ├─ git init                 0.20s
│  ├─ git commit ×8            2.80s  ← BOTTLENECK
│  └─ ulog.setup               0.10s
├─ call                        0.40s   6.9%
└─ teardown                    2.31s  39.7%
```

Sortie en couleur (rouge ≥ 25%, jaune 10-25%, vert <10%).

### 2.2 Explicit non-goals (deferred to later)

- Span recording in production code (pas seulement tests). v0.8 peut-être.
- Aggregation cross-runs (genre "moyenne du fixture X sur 100 runs").
  v0.8 ou un sidecar tool.
- OTel exporter (transformer les spans ulog en OTel spans pour les
  envoyer à Jaeger / Tempo). Trop tôt.
- Flame graph render (waterfall suffit pour v0.7 ; flame graph
  demande beaucoup de viewer JS).
- Span sampling (tout est capturé en v0.7 ; le NFR-PERF-70 limite à
  ≤ 5% overhead — si une suite a >100K spans, ce sera révisité).

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| **Span exit raise une exception** | `exit_status="error"`, le span record est émis avec exc structurée. Le tracking ne mange pas l'exception. |
| **Span instrumenté sans test_id parent** (utilisé hors test) | `test_id=null`, `parent_span_id=null`. Le span est tracé mais pas attaché à un test. |
| **Spans imbriqués profondément (>10 niveaux)** | Pas de limite, mais le viewer indente jusqu'à 6 niveaux puis collapse. |
| **Fixture session-scoped** | Span émis 1× au tout premier test qui le déclenche, attaché à ce test_id. (Pas de double-comptage.) |
| **Test parametrized** | Chaque parametrize = un test_id distinct = ses propres spans. |
| **Async test (`@pytest.mark.asyncio`)** | Spans en ContextVar (Python 3.7+ ContextVar) → propagés correctement à travers `await`. |
| **xdist parallel** | Chaque worker écrit dans son propre DB (Story 1.10) → pas de collision span_id (UUID). Le viewer assemble. |
| **Timer wrap-around / clock skew** | `started_at` + `ended_at` en monotonic time (pas wall clock) → pas affecté par NTP adjusts. ISO timestamps stockés en wall pour le display. |

---

## 3. Functional requirements

### 3.1 Span recording

| FR | Description |
|---|---|
| FR140 | `ulog.span(name: str) -> ContextManager` retourne un span; `__enter__` push sur la stack ContextVar, `__exit__` émet le record + pop. |
| FR141 | Le span émet 1 record `INFO` au logger `ulog.span` avec les champs §2.1.1 dans `context`. |
| FR142 | `span.set_attr(key, value)` ajoute une clé custom dans `context`. Reserved keys (`test_id`, `span_id`, etc.) sont rejetés avec `ValueError`. |
| FR143 | `@ulog.timed` wrap une fonction et émet un span autour de chaque appel. Le span name = `module.function_name`. |
| FR144 | `parent_span_id` est dérivé de la stack ContextVar — pas de paramètre explicite à passer. |
| FR145 | `span_id` est un UUID v4 (string 36 chars hex+dash). |

### 3.2 Pytest plugin auto-instrumentation

| FR | Description |
|---|---|
| FR146 | `pytest_runtest_setup` ouvre un span `setup` (parent = aucun, le test_id sert de root). |
| FR147 | `pytest_runtest_call` ouvre un span `call`. |
| FR148 | `pytest_runtest_teardown` ouvre un span `teardown`. |
| FR149 | Si une fixture est décorée `@ulog.timed_fixture`, un sub-span est émis dedans (parent = setup). |
| FR150 | Auto-instrumentation des fixtures stdlib (`tmp_path`, `monkeypatch`, etc.) : OFF par défaut, opt-in via `--ulog-trace-fixtures`. |
| FR151 | Au teardown du test, si la durée totale de la session > 1s OU si le test a échoué, un summary record est émis avec le top-5 spans par duration. |

### 3.3 Viewer waterfall

| FR | Description |
|---|---|
| FR152 | Detail view d'un record qui a `test_id` rend une section "Execution timeline" sous le panneau "Test context". |
| FR153 | Waterfall query : `SELECT * FROM logs WHERE logger='ulog.span' AND json_extract(context,'$.test_id')=?` ordered by `started_at`. |
| FR154 | Reconstruction de l'arbre : group by parent_span_id, root spans = ceux avec parent NULL ou égal au test_id sentinel. |
| FR155 | Bars proportionnelles à la durée totale du test (pas du parent direct — donne une perspective absolue). |
| FR156 | Highlight rouge si span_duration / total_duration > 0.25 ; jaune si > 0.10. |
| FR157 | Indentation max 6 niveaux ; au-delà, collapse avec un toggle "+3 deeper spans". |

### 3.4 CLI

| FR | Description |
|---|---|
| FR158 | `ulog explain <test_id> --db <path>` dump le waterfall en text. |
| FR159 | Sortie ANSI couleur sauf si `NO_COLOR=1` ou stdout pas un TTY. |
| FR160 | `ulog explain --slowest 10 --db <path>` liste les top-10 spans toutes-tests-confondus. |

---

## 4. Non-functional requirements

| NFR | Budget |
|---|---|
| NFR-PERF-70 | Overhead total ≤ 5% du temps de la suite (sur ulog-python's own 280-test suite : 18s → ≤ 19s). |
| NFR-PERF-71 | Page load du detail view avec waterfall ≤ 800ms pour un test ayant ≤ 100 spans. |
| NFR-DEP-70 | Aucune nouvelle dep. UUID est dans stdlib. ContextVar idem. |
| NFR-COMPAT-70 | Linux / macOS / Windows. xdist supporté (héritage Story 1.10). |
| NFR-DOC-70 | Doc page `/docs/test-execution-stack.md` couvrant: API, decorator, viewer waterfall, exemple "find slow tests". |
| NFR-CROSS-LANG-70 | Le format span (logger='ulog.span', champs context §2.1.1) est dans la spec wire format v1.0 (cf. `docs/vision-cross-language.md` §3.4) → portable à ulog-js / ulog-go ultérieurement. |

---

## 5. API surface (sketch)

### 5.1 Programmatic spans

```python
import ulog

# Basic
with ulog.span("expensive_op") as s:
    do_work()

# With custom attrs
with ulog.span("query") as s:
    s.set_attr("rows_scanned", 12345)
    s.set_attr("table", "logs")
    rows = db.execute(...)

# Decorator
@ulog.timed
def fetch_user(user_id):
    return db.get(user_id)

# Nested
with ulog.span("outer"):
    with ulog.span("inner"):
        pass  # both emitted, inner has parent_span_id=outer.span_id
```

### 5.2 Pytest

```python
# conftest.py — opt-in fixture instrumentation
import ulog

@ulog.timed_fixture
@pytest.fixture
def expensive_repo(tmp_path):
    setup_git_repo(tmp_path)
    return tmp_path

def test_using_repo(expensive_repo):
    # The fixture's setup time is auto-tracked as a sub-span of "setup"
    ...
```

CLI :

```bash
pytest tests/ --ulog-db /tmp/logs.sqlite --ulog-trace-fixtures
ulog-web /tmp/logs.sqlite           # waterfall in browser
ulog explain tests/test_x.py::test_y --db /tmp/logs.sqlite  # waterfall in terminal
ulog explain --slowest 10 --db /tmp/logs.sqlite             # top spans across all tests
```

### 5.3 Wire format addition (v1.0 spec extension)

Ajouté dans `docs/vision-cross-language.md` §3.4 :

```
| span_id        | uuid string  | ulog.span emit            | Sub-test timeline parent |
| parent_span_id | uuid|null    | ulog.span emit            | Idem |
| span_name      | string       | ulog.span emit            | Display label in waterfall |
| duration_s     | float        | ulog.span / pytest plugin | Already reserved (Story 1.2) |
| started_at     | ISO-8601     | ulog.span emit            | Waterfall positioning |
| ended_at       | ISO-8601     | ulog.span emit            | Idem |
| exit_status    | "ok"|"error" | ulog.span emit            | Red bar if error |
```

---

## 6. Worked examples

### 6.1 "Find why CI takes 12 minutes"

```bash
pytest tests/ --ulog-db /tmp/ci.sqlite --ulog-trace-fixtures
ulog explain --slowest 10 --db /tmp/ci.sqlite
```

Output:

```
TOP 10 SPANS BY DURATION (across 287 tests)
===============================================
1. setup_postgres_container  (test_integration_db_pool)    8.21s
2. setup_postgres_container  (test_integration_migrations) 7.89s
3. setup_postgres_container  (test_integration_indexes)    7.84s
4. download_fixture_data     (test_recommendation_model)   6.12s
5. setup_redis_container     (test_session_store)          4.30s
...
```

→ Insight : 4 tests appellent `setup_postgres_container` chacun (~8s).
Refactor → fixture session-scoped → gain de ~25s.

### 6.2 "Pourquoi ce test précis est lent"

```bash
ulog explain tests/test_authors_filter.py::test_filter_single_author --db /tmp/ci.sqlite
```

Output :

```
test_filter_single_author (5.81s)
├─ setup                                       3.10s  53.4%  [RED]
│  ├─ fixture: setup_demo_repo                 3.05s
│  │  ├─ git init                              0.20s
│  │  ├─ git commit ×8                         2.80s  ← BOTTLENECK
│  │  └─ ulog.setup                            0.05s
│  └─ misc setup                               0.05s
├─ call                                        0.40s   6.9%
│  ├─ adapter.query                            0.05s
│  └─ assertions                               0.35s
└─ teardown                                    2.31s  39.7%  [RED]
   └─ tmp_path cleanup                         2.29s
```

→ Insight : le fixture `setup_demo_repo` fait 8 commits Git (~350ms
chacun). Réduire à 2 commits ou utiliser `--depth=1` git → gain ~2s.

---

## 7. Definition of Done — v0.7

✅ FR140-160 implémentés avec tests pytest + tests viewer
✅ NFR-PERF-70 vérifié : overhead ≤ 5% sur la propre suite ulog-python
✅ NFR-PERF-71 vérifié : detail view avec waterfall ≤ 800ms pour 100 spans
✅ Wire format §5.3 ajouté à `docs/vision-cross-language.md` §3.4
✅ Doc page `/docs/test-execution-stack.md` rendue dans le viewer
✅ CLI `ulog explain` shipped avec subcommands `--slowest`
✅ Suite test ≥ 30 nouveaux tests sur l'API span + plugin + viewer + CLI
✅ SC4 préservé : `dependencies = []` toujours

---

## 8. Open questions

### Q1 — Auto-instrumentation des fixtures stdlib

Faut-il auto-tracer `tmp_path`, `monkeypatch`, `caplog`, etc. quand
`--ulog-trace-fixtures` est on ? Pro : visibility totale. Con : noise
(la plupart sont <1ms et polluent le waterfall).

**Décision draft** : OFF par défaut même avec le flag. Le flag active
uniquement les fixtures décorées `@ulog.timed_fixture`. Une option
`--ulog-trace-all-fixtures` peut être ajoutée v0.8 si demandée.

### Q2 — Span aggregation : moyennes vs runs individuels

Le pitch est "single run analysis". Une feature "comparer 2 runs"
(ex: avant/après refactor) serait utile mais demande un sidecar tool
(`ulog diff <run1.db> <run2.db>`). Reporté à v0.8.

### Q3 — Granularité `started_at` / `ended_at` (microsec vs millisec)

Stockage en ISO-8601 microsec (matches Python datetime.isoformat()).
Display dans le viewer en ms (plus lisible). CLI `ulog explain` en
seconds avec 2 décimales.

### Q4 — Span IDs : UUID v4 vs sequence

UUID v4 (16 bytes, ~36 chars en hex+dash). Pourquoi pas séquentiel ?
Parce que xdist parallel writers nécessitent un ID globalement unique
sans coordination. UUID v4 zéro-collision pratique.

### Q5 — Limite hard sur le nombre de spans par test

Pas de limite hard en v0.7, mais NFR-PERF-71 documente le budget
≤ 100 spans pour la perf viewer. Si un test a 10K spans, le waterfall
sera moche (à explorer en v0.8 — peut-être collapse / summarize).

---

## 9. Roadmap continuation

- **v0.7.1** — `ulog diff <run1> <run2>` pour comparer 2 sessions.
- **v0.8** — Auto-detect des bottlenecks (pattern matching : "ce
  fixture prend 4× plus de temps que la moyenne" → suggestion
  "session-scope it ?").
- **v0.9** — Port du span recording vers `ulog-js` (test runners JS
  : Vitest, Jest).
- **v1.0** — Wire format figé pour les ports satellites.

---

## 10. Change log

- **2026-05-10 v1.0** — Initial draft. Span API + pytest plugin
  extension + viewer waterfall + CLI explain. Cible "EXPLAIN ANALYZE
  pour ta suite de tests". Cohabite avec v0.3 test integration.

---

## 11. Sources

- [PostgreSQL EXPLAIN ANALYZE docs](https://www.postgresql.org/docs/current/sql-explain.html) — l'inspiration UX
- [OpenTelemetry Tracing Spec](https://opentelemetry.io/docs/specs/otel/trace/api/) — vocabulaire span / parent-id
- [Pytest hooks reference](https://docs.pytest.org/en/stable/reference/reference.html#hooks) — runtest_setup / call / teardown points
- [pytest-profiling](https://pypi.org/project/pytest-profiling/) — le competitor existant (cProfile-based, pas waterfall)
- [Chrome DevTools Performance panel](https://developer.chrome.com/docs/devtools/performance) — référence UX waterfall
