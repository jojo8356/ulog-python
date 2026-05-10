---
docType: vision
project_name: ulog
version: 1.0
date: 2026-05-10
author: jojo8356
status: draft
---

# ULog — Universal logging system across all languages

> **Pitch :** une seule pile de logging utilisable depuis Python / JS /
> Go / Rust / Java / etc. Tes logs s'écrivent dans un format wire
> commun (SQLite + JSONL + CSV), et un seul **viewer browser local**
> les visualise tous, peu importe le langage qui les a produits.
> Zéro infra. Zéro cloud. Aucune SaaS.

---

## 0. The 30-second pitch

Le marché de logging actuel a deux extrêmes :

- **Une libe par langage** (Pino en JS, zap en Go, structlog en Python, …) → tu écris dans des fichiers, tu cat / tail / grep.
- **Une SaaS hébergée** (Datadog, Splunk, Grafana Cloud) → ton équipe paye, tes données partent ailleurs.

Personne n'occupe le créneau du milieu : **logs locaux + UI moderne + multi-langages dans le même viewer**. C'est ce que ULog vise.

Le format wire (SQLite + JSONL + CSV avec un schema commun, déjà figé en v0.2) est le contrat universel. La libe Python (`ulog-py`) est la première implémentation. Les ports satellites (`ulog-js`, `ulog-go`, `ulog-rs`, …) viennent ensuite. **Le viewer est langage-agnostic dès aujourd'hui** — il consomme le format, pas le langage qui l'a écrit.

---

## 1. Vision

### 1.1 Why this exists

Une équipe moderne mélange souvent plusieurs langages : un service Python pour ML, un gateway Go, un frontend Node, un binary Rust pour la perf. Quand un incident traverse les services, **le développeur doit naviguer entre 4 outils différents** pour assembler la timeline. C'est inacceptable.

Loki + Grafana résolvent ça mais demandent une infra (Docker, retention policy, IAM). Datadog résoud ça mais coûte $$$ et envoie tes logs au cloud. **Pour une équipe de 1-50 devs, ULog se positionne entre les deux** : zéro infra, données locales, viewer drop-in pour tous les langages.

### 1.2 What ULog is NOT

- Une SaaS (jamais).
- Un service distribué (pas de gRPC, pas de OTel collector).
- Un remplacement de Loki/Grafana (pour grosses orgs : utilise Loki).
- Une lib qui force ses propres APIs (`ulog-py` cohabite avec stdlib `logging`, jamais ne le remplace).
- Un OTel-clone (OTel = trace-distribué ; ULog = log-local).

### 1.3 Target users

| Persona | Use case |
|---|---|
| **Solo dev / 1-3 devs** | Mélange Python + JS dans un side-project ; veut un viewer unique sans setup |
| **Petit team OSS** | Bibliothèque qui tourne en CI dans plusieurs langages ; veut un seul format pour tester / debug |
| **DevOps junior** | Veut "voir mes logs sans setup Loki" pour des CLI tools |
| **Compliance officer** (v0.5+) | Audit forensique sans cloud (HIPAA / SOC2 lite) |

### 1.4 Success criteria

| SC | Description |
|---|---|
| SC1 | Format wire stable v1.0 — toute lib qui écrit ce format est instantanément compatible avec le viewer existant. |
| SC2 | ≥ 3 langages portés (Python, JS, Go) avant tag v2.0. |
| SC3 | Viewer exportable en HTML statique (Epic 8 / v0.6) → un dev JS pur peut visualiser sans installer Python. |
| SC4 | "Hello world" en JS / Go : `npm install ulog-js` → 5 lignes de code → record visible dans `ulog-web` lancé depuis n'importe quel autre dev de l'équipe. |
| SC5 | **Habit preservation** : les fonctions clés (`setup`, `get_logger`, `bind`, `unbind`, `clear`, `context`, `span`) portent le **même nom sémantique** dans tous les ports. Un dev Python qui passe à `ulog-js` retrouve les mêmes verbes — seul le casing s'adapte à la convention locale (cf. §4.4). |

---

## 2. Architecture en 3 couches

```
┌──────────────────────────────────────────────────────────────┐
│                    WIRE FORMAT SPEC                          │
│           (le contrat — JSON minimal, schema SQLite)         │
└──────────────────────────────────────────────────────────────┘
              ▲                                  ▲
              │ écrit                            │ lit
              │                                  │
┌─────────────────────────────┐   ┌──────────────────────────────┐
│ LIBS PAR LANGAGE            │   │ VIEWERS                      │
│ • ulog-py    (DONE — v0.4)  │   │ • ulog-web   (Django, DONE)  │
│ • ulog-js    (TODO — Epic 9)│   │ • Static HTML export         │
│ • ulog-go    (TODO — Epic 10│   │     (Epic 8 / v0.6 — TODO)   │
│ • ulog-rs    (TODO — later) │   │ • [Future: Tauri / Electron  │
│ • ulog-java  (TODO — later) │   │    desktop wrapper]          │
│ • ulog-dotnet (TODO — later)│   │                              │
└─────────────────────────────┘   └──────────────────────────────┘
```

**Le viewer est déjà universal aujourd'hui.** Il lit n'importe quelle SQLite/JSONL/CSV qui respecte le schema. La suite consiste à publier la spec + faire des libs minces dans les autres langages.

---

## 3. Wire format spec (draft v1.0-rc)

### 3.1 SQLite (recommended)

```sql
CREATE TABLE logs (
    id         INTEGER PRIMARY KEY,                 -- auto-increment
    ts         TEXT    NOT NULL,                    -- ISO-8601 UTC, microseconds OK
    level      TEXT    NOT NULL,                    -- DEBUG | INFO | WARNING | ERROR | CRITICAL
    logger     TEXT    NOT NULL,                    -- dotted name; "myapp.api.checkout"
    msg        TEXT    NOT NULL,                    -- human-readable (UTF-8)
    file       TEXT    NOT NULL,                    -- basename: "checkout.py" / "checkout.go"
    line       INTEGER NOT NULL,                    -- 1-indexed
    exc        TEXT,                                -- JSON {type:str, msg:str, tb:list[str]} or NULL
    context    TEXT                                 -- JSON object — bound fields, free-form
);

CREATE INDEX ix_logs_ts ON logs(ts);
CREATE INDEX ix_logs_level ON logs(level);
CREATE INDEX ix_logs_logger ON logs(logger);
CREATE INDEX ix_logs_file ON logs(file);
```

**`level` values** are exactly the 5 strings listed (case-sensitive). No custom levels in v1.0 — the viewer expects this set for its filter buttons.

**`ts` format** : ISO-8601 with TZ designator. Microseconds optional but consistent within a single source. Example: `2026-05-10T14:32:01.234567Z`.

**`logger` convention** : dotted, lower-case, hierarchical. The viewer's "Sectors" filter splits on dots.

**`file` convention** : basename only (not absolute path). This matches Python's `record.filename` and lets author-attribution work uniformly across machines.

### 3.2 JSONL (alternative, 1 record = 1 line)

```json
{"ts":"2026-05-10T14:32:01.234Z","level":"INFO","logger":"myapp.api","msg":"req ok","file":"checkout.go","line":42,"context":{"user":"u_42"}}
```

Same field names, same semantics. `exc` and `context` may be omitted entirely (interpreted as null).

### 3.3 CSV (compat, 1 record = 1 row)

Header row: `id,ts,level,logger,msg,file,line,exc_json,context_json`. JSON columns serialized as strings.

### 3.4 Reserved context keys (cross-lang invariants)

These keys, when present in `context`, have specific viewer behavior. Implementations should not use these names for unrelated data.

| Key | Type | Origin | Viewer behavior |
|---|---|---|---|
| `test_id` | string | Pytest plugin (Py), `go test` wrapper, JUnit hook (Java/JS) | Tests sidebar filtering (Story 1.7) |
| `request_id` | string | HTTP middleware | Convention only (filterable via Bound fields) |
| `trace_id` | string | OTel bridge (v0.5) | Convention; OTel compat |
| `span_id` | string | Idem | Idem |
| `record_hash` | hex string | Forensic chain (v0.5) | `/integrity/` view |
| `prev_hash` | hex string | Idem | Idem |
| `chain_pos` | integer | Idem | Idem |
| `phase` | "setup"/"call"/"teardown" | Test integration (Story 1.4) | Test detail panel |
| `outcome` | "passed"/"failed"/"skipped"/"errored" | Test integration | Test sidebar badge |
| `duration_s` | float | Test integration | Test sidebar duration |

### 3.5 Versioning

The wire format version is **implicit in the schema columns present**. v1.0 = the columns above. v2.0 (hypothetical) might add new columns; readers must tolerate unknown columns gracefully (ignore them). New libraries should add a `_version` row in the DB metadata table once defined.

---

## 4. Library implementation contract

To call yourself a "ULog port", a library MUST provide:

### 4.1 Mandatory

1. **Write conformance** — output is byte-equivalent (or schema-equivalent for SQLite) to the spec above.
2. **Drop-in posture** — wrap or extend the language's stdlib logger, not replace it. (`logging` in Python, `slog` in Go 1.21+, `tracing` in Rust, `console` in JS, `java.util.logging` or SLF4J in Java.)
3. **Levels** — exactly the 5 string values. Mapping from native levels (`Console.warn` → `WARNING`) is the lib's job.
4. **Caller location** — `file` + `line` automatically captured from the stack frame.
5. **Context binding** — analogous to `ulog.bind(key=value)` (Python ContextVar) → JS AsyncLocalStorage, Go ctx, Rust span fields.
6. **At least one storage backend** — SQLite (recommended) OR JSONL. CSV optional.
7. **Zero external deps** for the core — same SC4/NFR-DEP-50 invariant as Python.

### 4.2 Optional (nice-to-have)

- Test runner integration (pytest plugin equivalent in JS/Go/Rust).
- Author attribution (the `git blame`-driven enrichment is reader-side; lib only needs to store `file` + `line`).
- Forensic hash chain (only after the spec freezes in v0.5).

### 4.3 Naming convention (packages)

| Language | Package name | Repo |
|---|---|---|
| Python | `ulog` (PyPI) | `jojo8356/ulog-python` |
| JavaScript | `ulog-js` or `@ulog/core` | `jojo8356/ulog-js` (TODO) |
| Go | `github.com/jojo8356/ulog-go` | TODO |
| Rust | `ulog` (crates.io) | TODO |
| Java | `io.ulog:ulog-core` | TODO |

Each repo's README must link back to the spec doc.

### 4.4 Canonical API names — habits stay across languages

**The rule.** Each port MUST expose the same **semantic verbs** as
`ulog-py`, with only the casing adapted to the language's native
convention. A dev who knows the Python API should be able to write
ULog code in JS / Go / Rust without checking docs — only the casing
changes, never the verb itself.

**Why.** Cross-language consistency is THE differentiator versus
"another logging lib per language". Pino's API has nothing in common
with zap's API which has nothing in common with structlog's API.
ULog's pitch falls apart if `ulog-js` has `setContext()` while
`ulog-py` has `bind()` — the user has to relearn for every language.

**The canonical API surface (Python source-of-truth):**

| Concept | Python (`ulog-py`) | JavaScript (`ulog-js`) | Go (`ulog-go`) | Rust (`ulog`) | Java (`ulog-core`) |
|---|---|---|---|---|---|
| Configure | `ulog.setup(...)` | `ulog.setup(...)` | `ulog.Setup(...)` | `ulog::setup(...)` | `Ulog.setup(...)` |
| Get a logger | `ulog.get_logger(name)` | `ulog.getLogger(name)` | `ulog.GetLogger(name)` | `ulog::get_logger(name)` | `Ulog.getLogger(name)` |
| Bind context | `ulog.bind(k=v, ...)` | `ulog.bind({k: v})` | `ulog.Bind(ctx, "k", v)` | `ulog::bind(("k", v))` | `Ulog.bind("k", v)` |
| Unbind | `ulog.unbind("k", ...)` | `ulog.unbind("k", ...)` | `ulog.Unbind(ctx, "k")` | `ulog::unbind("k")` | `Ulog.unbind("k")` |
| Clear all bindings | `ulog.clear()` | `ulog.clear()` | `ulog.Clear(ctx)` | `ulog::clear()` | `Ulog.clear()` |
| Read bindings | `ulog.get_bound()` | `ulog.getBound()` | `ulog.GetBound(ctx)` | `ulog::get_bound()` | `Ulog.getBound()` |
| Scoped context | `with ulog.context(k=v):` | `ulog.context({k: v}, () => {...})` | `ulog.Context(ctx, "k", v, func() {...})` | `ulog::context!(...)` | `try (var _ = Ulog.context("k", v)) {...}` |
| Open a span (v0.7) | `with ulog.span("name"):` | `ulog.span("name", () => {...})` | `ulog.Span(ctx, "name", func() {...})` | `ulog::span!("name", ...)` | `try (var _ = Ulog.span("name")) {...}` |
| Logger.level call | `log.info(msg, **kw)` | `log.info(msg, ctx?)` | `log.Info(msg, fields...)` | `log.info!(msg)` | `log.info(msg, fields)` |
| Test event API (v0.3) | `with test_event("name"):` | `testEvent("name", () => {...})` | `TestEvent(ctx, "name", func() {...})` | `test_event!("name", ...)` | (JUnit hook equivalent) |

**Casing rule per language:**

- **Python / Rust** — `snake_case` for functions, kwargs supported.
- **JavaScript / TypeScript** — `camelCase` for functions, single object arg for "kwargs-like" patterns.
- **Go** — `PascalCase` for exported. Use `context.Context` as first arg for binding (Go convention).
- **Java / Kotlin** — `camelCase` methods. Builder pattern OK for setup.
- **C# / .NET** — `PascalCase` methods.

**Verbs that are NEVER allowed to mutate** (preserve semantic identity):

- `setup` (NOT `init`, NOT `configure`, NOT `boot`)
- `get_logger` / `getLogger` / `GetLogger` (NOT `logger`, NOT `factory`, NOT `getInstance`)
- `bind` (NOT `setContext`, NOT `withFields`, NOT `addContext`)
- `unbind` (NOT `removeContext`, NOT `clearField`)
- `context` (NOT `withContext`, NOT `scope`, NOT `frame`)
- `span` (NOT `trace`, NOT `track`, NOT `measure`, NOT `timed_block`)
- `clear` (NOT `reset`, NOT `purge`, NOT `wipe`)

**Acceptance test for any new port (CI gate):**

A "Rosetta test" file in each port repo that exercises every canonical
verb in a smoke-test style. Reviewing the file side-by-side with
`ulog-py`'s equivalent must show 1:1 verb correspondence. If a port
introduces a verb not in this table, it requires a spec amendment
(this doc + cross-port discussion).

**Anti-patterns to refuse in code review:**

- A port that renames `bind` to "be more idiomatic" in its language.
- A port that adds `bindAll`, `bindMany`, `bindStrict` because it
  feels needed — propose to extend `bind` in the spec instead.
- A port that uses different verbs based on whether you call it from
  a logger instance (`log.bind`) vs the module (`ulog.bind`) — both
  must work and behave identically.

**Documented exception:**

Each language MAY add **non-canonical helpers** in addition to the
canonical verbs, IF those helpers don't replace canonical ones and
don't get exposed in the README's "5-line hello world" example.
Example: `ulog-go` may add a `WithContext(parent, ...)` helper for
Go's `context.Context` propagation — additive, not a rename of `bind`.

---

## 5. Roadmap des langages

### Phase 1 — Stabiliser Python (en cours)

Avant tout port, finir Epics 3-7 du `ulog-python` repo (v0.5 forensic + v0.6 static export + v0.7 release tag). **La spec wire format n'est pas figée tant que Python n'a pas tout shipped.**

### Phase 2 — Spec v1.0 publiée + Static HTML export shipped

Tag `v1.0.0` du `ulog-python` repo. Crée `ulog/spec/wire-format-v1.md` (extension de §3 ci-dessus) avec tous les détails finaux.

### Phase 3 — Premier port satellite : `ulog-js`

**Pourquoi JS d'abord** : plus gros marché de devs, et l'écosystème logging Node (Pino, Winston) n'a pas de viewer browser unifié. Le pitch ULog y résonne fort.

Effort : ~1 sem. Repo séparé `jojo8356/ulog-js`. NPM publish.

### Phase 4 — `ulog-go`

**Pourquoi Go ensuite** : `slog` stdlib (1.21+) facilite l'implémentation. Communauté CLI/devops apprécie les drop-in tools.

Effort : ~1 sem. Repo `jojo8356/ulog-go`. Go modules.

### Phase 5 — `ulog-rs`, `ulog-java`, `ulog-dotnet`

Ouverts à contributions externes une fois le pitch démontré.

---

## 6. Distribution & viewer story

Le viewer Django Python est l'implémentation "first-party". Mais un dev JS pur ne veut pas installer Python juste pour visualiser ses logs.

**La solution : Static HTML export (Epic 8 / v0.6 du roadmap actuel).**

Une fois `ulog-web export-html /path/to/logs.sqlite ./out/` shipped, n'importe quel dev peut :
1. Soit lancer `ulog-web` localement (s'il a Python).
2. Soit demander à un coéquipier Python de générer le HTML statique et le partager (zip, S3, GitHub Pages).
3. Soit bientôt utiliser un wrapper Tauri / Electron desktop.

**Ne pas implémenter le viewer dans plusieurs langages.** Maintenir 1 viewer Django + son export statique = 100x moins coûteux que maintenir 5 viewers. Le pitch "1 viewer pour tous les langages" est aussi un USP.

---

## 7. Non-goals (lock-in du scope)

| Non-goal | Pourquoi |
|---|---|
| Distributed tracing | OTel le fait déjà bien. ULog reste local. |
| Cloud SaaS hébergée | Le pitch est "données restent chez toi". |
| Real-time streaming dashboards | Loki/Grafana le font. ULog est post-mortem. |
| Per-language viewer reimplementations | 100x trop coûteux. 1 viewer + export statique = ROI. |
| Custom log levels au-delà des 5 standards | Maintient la compat cross-lang. |
| Schema migrations entre versions du wire format | Ajouter des colonnes seulement (forward-compat). Jamais break. |

---

## 8. Future PRDs that depend on this vision

Les PRDs suivantes s'appuient sur cette vision et seront implementées au fur et à mesure :

| PRD | Status | Description |
|---|---|---|
| [PRD-v0.5 Forensic archive](./prds/PRD-v0.5-forensic-archive.md) | draft | Hash chain integrity — fige le format avant ports satellites. |
| [PRD-v0.6 Static HTML export](./prds/PRD-v0.6-static-export.md) | draft | Critical pour distribution lang-agnostic. |
| [PRD-v0.7 Test execution stack](./prds/PRD-v0.7-test-execution-stack.md) | draft | "SQL EXPLAIN-like" timeline pour chaque test, voir où le temps est passé et identifier les bottlenecks. |
| PRD-v1.0 Wire format freeze | not yet | Doc officielle figée + version field + future-compat policy. |
| PRD-v1.1 ulog-js | not yet | Premier port satellite. |
| PRD-v1.2 ulog-go | not yet | Deuxième port. |

---

## 9. Definition of Done — pour cette vision

✅ Doc créé dans `docs/vision-cross-language.md`
✅ Architecture en 3 couches diagram inline
✅ Wire format spec draft (§3) avec schema SQLite + JSONL + CSV + reserved keys
✅ Library implementation contract (§4) — write conformance + drop-in + naming + canonical API verbs (§4.4)
✅ Roadmap par langage (§5)
✅ Non-goals lock-in (§7)
✅ Lien vers les PRDs futures (§8)

## 10. Change log

- **2026-05-10 v1.0** — Initial draft. Pitch + architecture + spec draft + roadmap. Posé comme nord-magnétique pour les Epics 8+ et les ports satellites.
- **2026-05-10 v1.1** — Added §4.4 *Canonical API names* + SC5 *habit preservation*. Locks the 9 canonical verbs (`setup`, `get_logger`, `bind`, `unbind`, `clear`, `get_bound`, `context`, `span`, `test_event`) with cross-language casing table + anti-pattern list + Rosetta-test acceptance gate. Ensures a Python user reading `ulog-js` / `ulog-go` code recognizes the API on sight.
