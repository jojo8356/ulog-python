# Story 4.5: `correlate()` core (lift formula + GROUP BY SQL)

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-5-correlate-core-lift-formula-group-by-sql`
**Implements:** FR101 (correlate), NFR-PERF-53 (10K/1M ≤ 500 ms), SC2.
**Built on:** Story 4.4 (DSL → SQL WHERE clause), Story 3.1 (chain schema), Story 4.1 (record dict shape).
**Foundation for:** Story 4.6 (small-sample warnings + axis-skip), Story 4.8 (`ulog correlate` CLI).

## Story

As a **developer investigating a spike**,
I want **`ulog.correlate(db, filter)` to compute `lift = P(tag=v | filter) / P(tag=v | ¬filter)` for every `(tag, value)` pair**,
so that **I can find the over-represented dimensions in the spike in seconds**.

## Acceptance Criteria

1. **`ulog.correlate(db_path, *, where=None, where_dsl=None, top=10, bottom=5) -> CorrelationReport`**.
2. **`CorrelationReport`** is a frozen dataclass: `top_over: tuple[CorrelationRow, ...]` (length ≤ `top`, sorted by lift DESC), `bottom_under: tuple[CorrelationRow, ...]` (length ≤ `bottom`, sorted by lift ASC), `filter_count: int`, `baseline_count: int`, `wall_time_ms: float`.
3. **`CorrelationRow`** frozen dataclass: `tag: str` (e.g. `"level"`, `"context.tenant_id"`), `value: Any`, `in_filter: int`, `in_baseline: int`, `lift: float`.
4. **Tag axes covered**: top-level columns `level`, `logger`, `file`; plus every `(key, value)` pair found in the `context` JSON column (key surfaced as `context.<k>`).
5. **SQL-side aggregation** — one CTE that labels each row with `is_filtered ∈ {0,1}`, then a `UNION ALL` expansion across the tag axes + `GROUP BY tag_name, tag_value` with `SUM(is_filtered)` / `SUM(1 - is_filtered)` for the per-(tag,value) counts. Single round trip.
6. **Filter is parameterised** — when `where_dsl` is set, compile via Story 4.4's `.to_sql() -> (clause, params)`, bind those params into the CTE's `CASE WHEN <clause> THEN 1 ELSE 0 END`. NEVER string-interpolate user data.
7. **Lift formula** — `lift = (in_filter / filter_count) / (in_baseline / baseline_count)` when both denominators are > 0. Edge cases: `baseline_count=0` → lift = `+inf` (uniquely-in-filter); `in_baseline=0` but `baseline_count>0` → lift = `+inf` too. `filter_count=0` → empty report (no rows match the filter). Documented.
8. **Excludes self-tautology rows** — if the user filters `level=ERROR`, the row `tag="level", value="ERROR"` is removed from the report (lift would be `+inf` and uninformative).
9. **`json_each` requirement** — SQLite must have the JSON1 extension. Stdlib SQLite ≥ 3.38 bundles it; documented requirement. Story 4.5 raises a clear `RuntimeError("SQLite < 3.38 lacks json_each; correlate() unavailable")` if `sqlite3.sqlite_version < "3.38"`.
10. **`ulog.correlate` exported** from `ulog/__init__.py` + `__all__`.
11. **Tests** — `tests/test_correlate.py`:
    - `test_correlate_returns_top_over_sorted_by_lift_desc`
    - `test_correlate_returns_bottom_under_sorted_by_lift_asc`
    - `test_correlate_self_tautology_excluded`
    - `test_correlate_with_where_dsl_filter`
    - `test_correlate_returns_in_filter_and_in_baseline_counts`
    - `test_correlate_unique_in_filter_yields_infinite_lift`
    - `test_correlate_on_empty_filter_returns_empty_report`
    - `test_correlate_context_keys_surface_as_dotted_tags`
    - `test_correlate_no_sql_injection_via_dsl_value`
    - `test_correlate_wall_time_under_budget_on_1k_records` (scaled smoke: NFR-PERF-53 is 1M, ship a 1K assert ≤ 100 ms as proxy).

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/_correlate.py` (NEW)** ~ 220 LOC.
- [ ] **Task 2 — Public API** — `ulog.correlate` export.
- [ ] **Task 3 — Tests** in `tests/test_correlate.py` (10 tests).
- [ ] **Task 4 — Validation** — mypy / ruff / deptry clean.

## Dev Notes

### SQL skeleton

```sql
WITH labeled AS (
    SELECT
        level, logger, file, context,
        CASE WHEN <filter_sql> THEN 1 ELSE 0 END AS is_filtered
    FROM logs
), expanded AS (
    SELECT 'level' AS tag, level AS value, is_filtered FROM labeled
    UNION ALL
    SELECT 'logger', logger, is_filtered FROM labeled
    UNION ALL
    SELECT 'file', file, is_filtered FROM labeled
    UNION ALL
    SELECT 'context.' || je.key, je.value, labeled.is_filtered
    FROM labeled, json_each(labeled.context) AS je
    WHERE labeled.context IS NOT NULL
)
SELECT tag, value, SUM(is_filtered), SUM(1 - is_filtered)
FROM expanded
GROUP BY tag, value
```

Plus a totals query:

```sql
SELECT
    SUM(CASE WHEN <filter_sql> THEN 1 ELSE 0 END) AS in_filter,
    COUNT(*) - SUM(CASE WHEN <filter_sql> THEN 1 ELSE 0 END) AS in_baseline
FROM logs
```

### References

- [Source: epics.md, lines 1399-1421] — Story 4.5 AC
- [Source: PRD-v0.5 §3.4, FR101] — correlate
- [SQLite json_each docs] — JSON1 extension

## Dev Agent Record

### Completion Notes List

- New module `ulog/_correlate.py` (~220 LOC) with `CorrelationRow`,
  `CorrelationReport`, `correlate()` + helpers `_compute_lift`,
  `_collect_eq_pairs`, `_coerce_value`.
- Single SQL round-trip: CTE labels rows via DSL→SQL with bind
  params, UNION ALL expands across tag axes (level/logger/file +
  `json_each(context)` for nested keys surfaced as `context.<k>`),
  GROUP BY tag,value with SUM(is_filtered) / SUM(1-is_filtered).
- Lift formula correctly handles edge cases: filter_count=0 →
  empty report; in_baseline=0 with in_filter>0 → math.inf; p_out=0 →
  math.inf.
- Self-tautology removal — `_collect_eq_pairs` walks the DSL AST,
  collects `(key, value)` from every `=` Cmp, and the report skips
  matching rows.
- SQLite version guard: `RuntimeError` if `sqlite_version < 3.38`
  (json_each requirement).
- Public API: `ulog.correlate`, `ulog.CorrelationRow`,
  `ulog.CorrelationReport` exported + in `__all__`.
- 13 / 13 tests in `tests/test_correlate.py` green: lift DESC/ASC
  sort, tautology exclusion, DSL filter, in_filter/in_baseline
  counts, infinite-lift edge case, empty-filter report, context
  dotted-key surfacing, no-SQL-injection via DSL value, 1K perf
  smoke (< 250 ms — proxy for NFR-PERF-53 1M target), and 3
  argument-validation tests.
- mypy --strict / ruff check / ruff format / deptry all clean.

### File List

- `ulog/_correlate.py` (NEW) — `correlate()` + dataclasses + helpers.
- `ulog/__init__.py` — `correlate`, `CorrelationRow`,
  `CorrelationReport` exports + `__all__`.
- `tests/test_correlate.py` (NEW) — 13 tests.
