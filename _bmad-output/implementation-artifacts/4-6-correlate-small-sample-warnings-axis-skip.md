# Story 4.6: `correlate()` small-sample warnings + axis-skip

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-6-correlate-small-sample-warnings-axis-skip`
**Implements:** FR102.
**Built on:** Story 4.5 (`correlate` core + `CorrelationRow` dataclass).

## Story

As a **user interpreting correlate output**,
I want **explicit warnings when `in_filter < 30` (small-sample bias) and when an axis is included but IS the filter axis itself**,
so that I don't draw wrong conclusions from spurious lifts.

## Acceptance Criteria

1. **`CorrelationRow` gains `warning: str | None = None`** — values: `"small_sample"`, `"axis"`, or `None`.
2. **`warning="small_sample"`** when `in_filter < 30`. Row stays in `top_over` / `bottom_under` but carries the flag.
3. **`warning="axis"`** when the row IS the filter axis (e.g. filter `level=ERROR` → row `tag="level", value="ERROR"`). EXCLUDED from `top_over` / `bottom_under` ranking.
4. **`CorrelationReport` gains `axis_rows: tuple[CorrelationRow, ...]`** — the excluded axis rows, exposed for inspection (so the user can see them without sifting through everything).
5. **Story 4.5's behaviour preserved**: top/bottom ranking unchanged for non-axis non-small-sample rows.
6. **Tests** — append to `tests/test_correlate.py`:
   - `test_small_sample_warning_when_in_filter_under_30`
   - `test_no_warning_when_in_filter_30_or_more`
   - `test_axis_row_gets_axis_warning_and_excluded_from_top`
   - `test_axis_row_exposed_in_axis_rows_tuple`
   - `test_small_sample_and_axis_dont_overlap` (axis wins; row gets axis warning + is excluded from rank).

## Tasks / Subtasks

- [ ] Update `CorrelationRow` + `CorrelationReport` dataclasses.
- [ ] Update `correlate()` to compute warnings + populate `axis_rows`.
- [ ] 5 new tests.

## Dev Notes

Small-sample threshold = 30 (frequentist convention). Decision: hardcoded; configurable in v0.6.x if user demand surfaces.

## Dev Agent Record

### Completion Notes List

- `CorrelationRow` gained `warning: str | None = None` (defaults
  to `None`; values: `"small_sample"` for `in_filter < 30`,
  `"axis"` for the filter-axis row).
- `CorrelationReport` gained `axis_rows: tuple[...] = ()` —
  exposes the excluded axis rows for inspection.
- Decision: axis warning WINS over small_sample (axis is more
  actionable; small sample is statistical noise).
- `SMALL_SAMPLE_THRESHOLD = 30` module constant (configurable in
  v0.6.x if user demand surfaces).
- 18 / 18 tests in `tests/test_correlate.py` green (13 from 4.5
  + 5 new for 4.6).
- mypy --strict / ruff / format / deptry all clean.

### File List

- `ulog/_correlate.py` — `CorrelationRow.warning`,
  `CorrelationReport.axis_rows`, threshold constant, dispatch logic.
- `tests/test_correlate.py` — 5 new tests appended.
