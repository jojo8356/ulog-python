---
docType: prd
project_name: ulog-python
version: 0.4.4
date: 2026-05-11
author: jojo8356
status: draft v1
parent_prd: PRD-v0.4.1-viewer-perf-hotpath.md
---

# ULog v0.4.4 — Sub-second viewer everywhere

> Tighten the v0.4.1 perf contract from "no path > 3s" to "no path
> > 1s". Three hotspots remaining: the author filter (post-query
> Python walk, ~1.7s on the 43K-record demo), the search filter
> (SQL `LIKE %term%` full-table scan, unbounded on a long
> `msg` column), and the cold-cache first request (still ≈ 600ms,
> uncomfortably close to the new ceiling). Goal: every page-load
> path lands in < 1.0s on the 43K-record demo, < 2.0s on a
> 500K-record stress fixture.

## 0. Problem

Baseline today (from `tests/test_qa_perf_e2e.py` + manual curl on
43K records):

| Path | Today | New target |
|---|---:|---:|
| `GET /` (cold cache) | ≈ 0.65 s | < 1.0 s ✓ already |
| `GET /` (warm cache) | ≈ 0.12 s | < 1.0 s ✓ already |
| `GET /?level=ERROR` | ≈ 0.20 s | < 1.0 s ✓ already |
| `GET /?author=alice@…` (warm) | **≈ 1.68 s** | < 1.0 s — gap of 0.7 s |
| `GET /?q=substring` | unmeasured | < 1.0 s — needs a budget |
| `GET /?page=N` | ≈ 0.15 s | < 1.0 s ✓ already |
| `GET /r/<id>/` | ≈ 0.03 s | < 1.0 s ✓ already |

Three structural drags pulling the slowest paths above 1 s:

1. **Author filter is post-query Python.** `list_view` runs
   `adapter.query(filters, page=1, page_size=10_000_000)` to pull
   ALL filtered records, then walks them in Python applying
   `idx.author_for(r.file, r.line) in selected`. On the 43K-record
   demo this is the dominant cost (~1.5 s of the 1.68 s total).
   PRD-v0.4.1 §2.2 explicitly deferred the fix: "SQL `JOIN` with
   `authors` table … v0.5 candidate; current 1.15s is acceptable
   for the budget." The new ceiling makes it not-acceptable.

2. **Search is `msg LIKE %term%`.** SQLite has no index that helps
   a leading-`%` substring query — it falls through to a full
   table scan. At 43K records the scan takes ~50-200 ms (OK), but
   at 500K records it crosses 1 s, and at 1M records it crosses
   2 s. Stress fixtures already exist for the chain-integrity
   roadmap; the search budget needs to scale with them.

3. **Cold-cache headroom is thin.** `compute_authors_summary` on
   first request takes ~500-600 ms even after the v0.4.1
   optimizations (SQL `GROUP BY` + memoization). That's most of
   the 0.65 s cold figure. Any extra work added by future stories
   (e.g., the v0.4.3 `/team/` page, the chain hash verification
   from v0.5) pushes us over. Pre-warming at startup is free and
   removes the cliff entirely.

The user-facing rule we want to lock in: **the search box and
every filter checkbox tick respond in under a second on a
production-sized dataset**, no asterisks, no "except on cold cache".

## 1. Vision

Three structural fixes, each independently shippable, gated by
regression tests in `tests/test_qa_perf_e2e.py`.

### 1.1 Author filter — SQL JOIN against the `authors` cache

The v0.4 `AuthorIndex` already maintains a sidecar `authors`
SQLite table (`<db>.authors.sqlite` for JSONL/CSV, in-memory for
SQLite adapter at present). v0.4.4 lifts that into a **real
queryable table** keyed by `(file, line) → author_email`, and
the author filter becomes a SQL `JOIN`:

```sql
SELECT logs.*
FROM   logs
JOIN   authors
       ON authors.file = logs.file AND authors.line = logs.line
WHERE  authors.email IN (?, ?, ?)
  AND  <other filter clauses>
LIMIT  100 OFFSET 0;
```

SQLite handles the `(file, line)` join via the existing
`PRIMARY KEY (file, line)` index on the `authors` table. Net
effect: the 1.5 s Python walk collapses to a single SQL pass,
estimated < 200 ms on the demo and < 800 ms on a 500K-record
fixture (linear-in-result-set, not in total-records).

The `<unknown>` case (records with no author match) is handled
by `LEFT JOIN` + `WHERE authors.email IS NULL` on the
`show_unknown` toggle path.

### 1.2 Search — opt-in SQLite FTS5 virtual table

Add a **shadow** FTS5 virtual table `logs_fts(msg)` populated by
triggers on the main `logs` table:

```sql
CREATE VIRTUAL TABLE logs_fts USING fts5(msg, content='logs', content_rowid='id');
CREATE TRIGGER logs_ai AFTER INSERT ON logs BEGIN
  INSERT INTO logs_fts(rowid, msg) VALUES (new.id, new.msg);
END;
CREATE TRIGGER logs_ad AFTER DELETE ON logs BEGIN
  INSERT INTO logs_fts(logs_fts, rowid, msg) VALUES('delete', old.id, old.msg);
END;
CREATE TRIGGER logs_au AFTER UPDATE ON logs BEGIN
  INSERT INTO logs_fts(logs_fts, rowid, msg) VALUES('delete', old.id, old.msg);
  INSERT INTO logs_fts(rowid, msg) VALUES (new.id, new.msg);
END;
```

The `SearchAdapter` mixin in `SQLiteAdapter` rewrites
`Filters.search` from `LIKE %term%` to `WHERE logs.id IN
(SELECT rowid FROM logs_fts WHERE msg MATCH ?)`. FTS5's MATCH is
indexed → constant-time relative to total records,
linear-in-matches.

**Opt-in via a new `setup(integrity=…, fts=True)` parameter**
(or `--fts` CLI flag in the viewer). The default stays `LIKE`
because:
- FTS5 ships in stock SQLite but adds disk overhead (~2× msg
  column size).
- The trigger-based content sync is the safe model but doubles
  write amplification on bulk imports.
- JSONL/CSV adapters can't benefit (no SQL).

For users who don't enable FTS, the `LIKE` path is unchanged.

### 1.3 Pre-warm `compute_authors_summary` at viewer startup

Right after `build_index_at_startup` finishes (already runs at
viewer launch — see `ulog/web/cli.py:setup_django` or wherever),
fire one `compute_authors_summary(adapter, idx)` call so the
module-level `_AUTHORS_SUMMARY_CACHE` lands warm BEFORE the
first HTTP request.

Net cost: 500-600 ms shifted from "first GET / response" to
"viewer startup". Startup goes from ~200 ms to ~800 ms. The
viewer is a manually-launched local dev tool — its startup is
not on the hot path; its first HTTP response is. Trade is good.

No-op when `--no-author-index` is passed (no idx → no summary
to warm).

## 2. Scope

### 2.1 In scope

1. **SQL JOIN author filter (§1.1):**
   - Materialize the in-memory `AuthorIndex` cache into the
     `<db>.authors.sqlite` sidecar for SQLite adapters too
     (currently only JSONL/CSV use the sidecar).
   - Add `SQLiteAdapter._authors_table` that ATTACHes the
     sidecar DB at engine init, exposes it as a SQLAlchemy
     `Table` for `JOIN` clauses.
   - Rewrite the author-filter branch in `list_view` to build a
     single SQL query (filters + author JOIN + LIMIT) instead of
     the current `page_size=10_000_000` + Python post-filter.
   - JSONL/CSV adapters fall back to the existing Python walk
     (their author resolution stays in-process). Acceptable
     because they're not the perf-budget-binding format.
2. **FTS5 opt-in search (§1.2):**
   - New `SQLHandler(fts=True, ...)` parameter that creates
     the `logs_fts` virtual table + triggers at schema init.
   - New `ulog-web --fts` flag — when set, the viewer routes
     `Filters.search` through `MATCH` instead of `LIKE`. When
     unset, behavior unchanged.
   - SchemaError surfaces "FTS5 enabled at runtime but
     `logs_fts` table missing — run `ulog migrate-fts` or
     re-create the DB" (deterministic upgrade message — same
     pattern as v0.5 chain columns Story 3.3).
3. **Startup pre-warm (§1.3):**
   - One `compute_authors_summary(adapter, idx)` call right
     after `build_index_at_startup` in
     `ulog/web/cli.py::_setup_django` (or wherever the indexer
     is currently kicked off).
   - Gated on `idx is not None`.
4. **Tighter test budgets in `tests/test_qa_perf_e2e.py`:**
   - `BUDGET_COLD_S`: 3.0 → 1.0
   - `BUDGET_WARM_S`: 1.0 → 0.3
   - `BUDGET_FILTER_S`: 1.0 → 0.5
   - `BUDGET_AUTHOR_S`: 2.0 → 1.0 (the headline gain)
   - NEW `BUDGET_SEARCH_S`: 1.0
   - `BUDGET_PAGINATION_S`: 1.0 → 0.3
   - `BUDGET_DETAIL_S`: 0.5 → 0.2
   - `BUDGET_HARD_CEILING`: 3.0 → 1.0
5. **Stress-fixture perf test:**
   - New `tests/test_qa_perf_500k.py` (slow, marked
     `@pytest.mark.slow` so CI runs it gated). Seeds a 500K-record
     SQLite DB with the demo's logger shape, asserts every path
     under 2.0s (relaxed ceiling for 10× the demo size).

### 2.2 Out of scope (deferred)

- **JOIN against `authors` for non-SQLite adapters.** JSONL/CSV
  keep their Python walk; if the user picks those formats they
  pay the Python cost. v0.5+ could ship `ulog migrate jsonl→sqlite`
  but that's a different feature.
- **FTS5 ranking / BM25 scoring.** v0.4.4 ships substring
  semantics matching today's `LIKE` behavior — `MATCH "term"`
  returns hits in id order, same as `LIKE`. Custom ranking
  is a v0.6+ ergonomics improvement.
- **HTTP caching headers (`ETag`, `Cache-Control`).** Would help
  repeat-paginate-back-and-forth flows, but the dev-time use case
  rarely needs it. Defer to v0.6 when public-facing surfaces
  (static export, hosted demo) appear.
- **Async / streamed responses.** Django stays sync. Streaming
  would mostly help the detail view (already 30 ms) — wrong
  hotspot to optimize.
- **Author filter on `<unknown>` only via SQL.** The `LEFT JOIN
  WHERE authors.email IS NULL` shape works, but the perf gain
  there is small (it's already fast — the slow case is the
  *positive* author selection). Ships in §1.1 anyway since it
  costs nothing extra; just not the binding constraint.

## 3. Acceptance

All measured on the seeded 43K-record demo, viewer started with
`--repo /tmp/ulog-demo --fts`:

- **AC1 — cold cache** `GET /` < 1.0 s.
- **AC2 — warm cache** `GET /` < 0.3 s (subsequent identical).
- **AC3 — level filter** `GET /?level=ERROR` < 0.5 s.
- **AC4 — author filter** `GET /?author=alice@globex.io` < 1.0 s
  (the headline gain — down from 1.68 s).
- **AC5 — author filter, two authors** `GET /?author=a&author=b`
  < 1.0 s (OR semantics, SQL `IN`).
- **AC6 — show_unknown=0** `GET /?show_unknown=0` < 1.0 s (the
  `LEFT JOIN WHERE NULL` path).
- **AC7 — search** `GET /?q=user_0123` < 1.0 s. Without `--fts`,
  same response shape (results identical), perf falls back to
  `LIKE` (no regression on small DBs).
- **AC8 — pagination** `GET /?page=10` < 0.3 s.
- **AC9 — detail view** `GET /r/<id>/` < 0.2 s.
- **AC10 — hard ceiling** every page-load path < 1.0 s; all 6
  paths above + tested concurrently in
  `test_perf_no_path_exceeds_hard_ceiling` with
  `BUDGET_HARD_CEILING = 1.0`.
- **AC11 — stress fixture** every path on the 500K-record fixture
  < 2.0 s (10× the demo, 2× the budget — matches the user-facing
  PRD-v0.4.1-style "headroom for CI runners").
- **AC12 — startup warm-up budget** viewer launch (`ulog-web ...
  --repo ...`) reaches "ready" stdout marker in < 1.0 s on the
  43K demo. Pre-warm `compute_authors_summary` lands inside that
  budget (it's already ~500 ms today, so total ≈ 800 ms).
- **AC13 — FTS5 fallback** when `--fts` is OFF, search still
  returns the same record set on a `?q=term` query (no
  regression in correctness).
- **AC14 — adapter uniformity** all 3 adapters (SQLite, JSONL,
  CSV) still return identical results for the same
  `(filters, page, page_size)` triple. SQLite gets faster; the
  others stay where they were.
- **AC15 — tests** all 290+ existing tests stay green.
  New tests:
  - `test_author_filter_uses_sql_join` (asserts the issued SQL
    contains `JOIN authors` when FTS+author filter active)
  - `test_fts_search_returns_same_set_as_like` (parity check on
    the seeded demo)
  - `test_fts_search_under_budget_on_500k`
  - `test_authors_summary_prewarmed_at_startup` (mocks the
    startup hook, asserts the cache is populated before any
    HTTP request fires)

## 4. Non-functional

- **No new PyPI dependency.** SQLite FTS5 ships in stock CPython's
  bundled `_sqlite3` (since 3.7.7 — well below our 3.10 floor).
  SQLAlchemy 2.0 already supports `MATCH` via raw SQL.
- **Disk overhead.** FTS5 shadow table adds ~2× the `msg` column
  size. On a 43K-record demo (~5 MB of `msg`), ~10 MB extra.
  Opt-in, documented in `storage.md` once §1.2 lands.
- **Write amplification.** Triggers double the write cost on bulk
  imports. Acceptable because (a) bulk imports are rare in the
  dev workflow ULog targets, (b) FTS is opt-in so cost is paid
  only when search perf matters.
- **Memory.** No change. SQL JOIN runs on SQLite's existing
  page cache; no new in-process structures.
- **Cache invariants.** `_AUTHORS_SUMMARY_CACHE` keyed by
  `(db_mtime, id(idx))` still works as today. Pre-warm just
  populates it earlier; subsequent reads remain instant.
- **Test budgets are anchored to wall-time on the dev's
  machine.** PRD-v0.4.1 used 2× headroom for CI; v0.4.4 keeps
  that headroom but tightens the absolute targets. CI may need
  a `slow` marker exclusion if it runs on cold cloud VMs — the
  500K-record fixture test is already gated by `@pytest.mark.slow`.

## 5. Risks / open questions

- **SQLite ATTACH for the authors sidecar.** Attaching an
  external DB at runtime is supported but adds connection setup
  cost (~5-10 ms per request unless we hold the connection
  open). Mitigation: open the engine once at adapter init and
  ATTACH the sidecar at that moment — SQLAlchemy's connection
  pool reuses the connection for subsequent queries. Tracked
  as Decision H1.
- **FTS5 tokenizer choice.** Default `unicode61` is fine for
  English; doesn't stem (so `user_0123` matches verbatim, not
  `user 0124`). PRD-v0.4.1 search semantic is "substring" not
  "stemmed search" — matches user expectation. No tokenizer
  config required.
- **SQL injection on the author filter `IN` clause.** Must use
  bound parameters, never string interpolation. Decision H2.
- **SQLite version on Windows CI.** Stock Python's
  `sqlite3.sqlite_version` must be ≥ 3.20 for FTS5 to be
  reliable. Confirmed for Python 3.10+ on all OSes we support;
  no action needed.
- **Pre-warm blocks viewer startup.** If the user runs against
  a HUGE DB (1M+ records), pre-warming could push startup
  past 5 s. Mitigation: emit a progress line on stderr (same
  pattern as the existing `ulog: indexing authors…`); add
  `--no-prewarm` flag as an escape hatch (Decision H3).

## 6. Implementation notes

### 6.1 SQLite sidecar ATTACH (Decision H1)

```python
# ulog/web/viewer/adapters.py — SQLiteAdapter.__init__
self._engine = create_engine(f"sqlite:///{path}", future=True)
authors_db = path.parent / f"{path.stem}.authors.sqlite"
if authors_db.exists():
    with self._engine.begin() as conn:
        conn.exec_driver_sql(f"ATTACH DATABASE '{authors_db}' AS authdb")
    self._has_authors_sidecar = True
else:
    self._has_authors_sidecar = False
```

The attach happens once at adapter init. SQLAlchemy's connection
pool keeps the connection open for subsequent queries; the
attached schema is visible as `authdb.authors`.

### 6.2 Parameter binding (Decision H2)

Authors `IN (...)` clause MUST use SQLAlchemy parameter binding,
never f-string interpolation. The existing `t.c.level.in_(filters.levels)`
pattern in `_base_filters` is the template — extend it for the
author email list:

```python
if filters.authors:
    clauses.append(authdb_authors.c.email.in_(filters.authors))
```

### 6.3 Pre-warm hook (Decision H3)

```python
# ulog/web/cli.py — after build_index_at_startup
if idx is not None and not args.no_prewarm:
    print("ulog: pre-warming authors summary...", file=sys.stderr)
    t0 = time.perf_counter()
    from .viewer.blame import compute_authors_summary
    compute_authors_summary(adapter, idx)
    print(f"ulog: pre-warm done in {time.perf_counter() - t0:.2f}s",
          file=sys.stderr)
```

`--no-prewarm` flag added to the argparse setup (mutually
exclusive with `--no-author-index` since the latter sets idx to
None anyway).

### 6.4 FTS5 schema creation (Decision H4)

Lives in `SQLHandler._verify_or_create_schema` behind a
`self._fts` flag set in `__init__`. The triggers are
idempotent (CREATE TRIGGER IF NOT EXISTS); the virtual table
creation isn't (no `IF NOT EXISTS` variant in older SQLite),
so wrap in `try/except OperationalError`.

### 6.5 Search routing in adapters.py (Decision H5)

```python
# SQLiteAdapter._base_filters
if filters.search:
    if self._fts_enabled:
        # FTS5 MATCH — indexed lookup. Substring-style via prefix
        # match: `MATCH 'term*'` for the LIKE %term% feel.
        # Bind via SQLAlchemy `text()` to keep param binding safe.
        clauses.append(t.c.id.in_(
            select(fts.c.rowid).where(text("logs_fts MATCH :q"))
                .params(q=f'"{filters.search}" OR {filters.search}*')
        ))
    else:
        clauses.append(t.c.msg.like(f"%{filters.search}%"))
```

The query string is double-quoted to escape any FTS5 operators
the user might accidentally type (`AND`, `OR`, etc. as raw words
get treated as operators otherwise). Decision H5 documents the
exact escape rule.

### 6.6 Cache invalidation on schema changes

Story 1.13 already handles the CREATE TABLE race for the main
`logs` table. The FTS5 trigger creation reuses the same
race-tolerant guard. The authors sidecar ATTACH is read-only
from the adapter's perspective, so no race there.

## 7. See also

- **Parent:** [PRD-v0.4.1-viewer-perf-hotpath.md](./PRD-v0.4.1-viewer-perf-hotpath.md) — the earlier perf patch this PRD extends. Defines the budget table this PRD tightens.
- **Sibling features:** [PRD-v0.4.3-team-page.md](./PRD-v0.4.3-team-page.md) — the `/team/` page reuses the same `(db_mtime, idx)` cache and benefits from the pre-warm.
- **Adapter uniformity:** `_bmad-output/planning-artifacts/architecture.md` Enforcement rule #8 — JSONL/CSV must return same results as SQLite. v0.4.4 keeps that invariant; only the *path* to the result changes.
- **Perf test gate:** `tests/test_qa_perf_e2e.py` — currently asserts the v0.4.1 budgets; this PRD tightens them via the constants at the top of that file (no test-shape change, just budget numbers).
