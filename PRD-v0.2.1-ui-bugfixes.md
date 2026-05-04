---
docType: prd
project_name: ulog-python
version: 0.2.1
date: 2026-05-04
author: jojo8356
status: draft v1
parent_prd: PRD-v0.2-storage-and-ui.md
priority: high (visible UX bugs)
---

# ULog v0.2.1 — UI bugfixes

> Three visible UX issues in the v0.2.0 inspection UI, identified by
> the first user (Johan) on the first real run. Patch release — no
> behavior changes outside the affected widgets, no API changes.

---

## 0. The 30-second pitch

Johan ran `ulog-web` on `~/.cache/qlnes/last-run.sqlite` and hit
three UX issues:

1. **Spacing**. In the Sectors / Files / Levels sidebar, the count
   number renders flush against the label text (`qlnes.apu2`) — no
   visual gap. Hard to read.
2. **Counts collapse under self-filter**. When Johan ticks `DEBUG` in
   the Level sidebar, the **other** level counts drop to `(0)` —
   `INFO (0) WARNING (0) ERROR (0) CRITICAL (0)`. They should show
   the count Johan would get if he ALSO ticked that level (i.e. `INFO
   (9)` because there are 9 INFO records in the data, regardless of
   his current DEBUG filter). This is the standard "ghost count" UX
   pattern from Datadog/Sentry/Grafana.
3. **Counts at the wrong axis level**. Same bug as #2 affects Sectors
   counts — a user who ticked `qlnes.audio` sees the Sectors tree
   filter ITSELF, so unrelated sector counts go to zero.

Bugs #2 and #3 are the same root cause: the per-axis count query
applies the FULL filter set instead of "all filters except this axis".

---

## 1. Root cause

`SQLiteAdapter._count_by` in
`ulog/web/viewer/adapters.py` (and the in-memory equivalent in
`_filter_and_paginate`) applies the SAME `where` clause for:
- the main record list (correct)
- the level_counts aggregate (wrong)
- the file_counts aggregate (wrong)
- the logger_counts aggregate (wrong)

When the user adds a level filter, the level_counts dict is computed
WITH that filter applied, so it only ever has one non-zero entry —
the level that's currently checked. The user can't see "if I ALSO
ticked WARNING, would I get more results?" without unticking and
re-ticking.

**Fix.** Compute each axis's counts with a `where` clause that
EXCLUDES that axis's filter. So:

- `level_counts` query uses filters from {sectors, files, search,
  bound, time} — but NOT levels.
- `file_counts` query uses filters from {levels, sectors, search,
  bound, time} — but NOT files.
- `sector_counts` query uses filters from {levels, files, search,
  bound, time} — but NOT sectors.

The main record list query keeps using the full filter set (correct
behavior).

---

## 2. Functional Requirements

### FR1 — Ghost counts on every faceted axis

Each of the four faceted-filter sidebar sections (Level, Sectors,
Files, Bound fields) computes its counts ignoring its OWN axis but
applying every other axis. This way the user always sees what they'd
get if they added a value to that axis on top of the current filter.

| Sidebar | Counts ignore | Counts apply |
|---|---|---|
| Level | levels | sectors, files, search, bound, time |
| Sectors | loggers (all sector prefixes) | levels, files, search, bound, time |
| Files | files | levels, sectors, search, bound, time |
| Bound (auto-detected keys) | bound | levels, sectors, files, search, time |

### FR2 — Spacing fix in the sidebar

Each sidebar row currently renders as:

```html
<input> <span>qlnes.apu</span><span>2</span>
```

…and the count `2` lands flush against `apu`. Add a Tailwind
`ml-2` (or equivalent) on the count span so there's at least 0.5rem
between label and count. Same fix for the Files dropdown and the
Level checkboxes.

### FR3 — Visual separator on long counts

When a count goes over 4 digits (e.g. `qlnes.audio.renderer 12345`),
the alignment breaks. Right-align the count column with a fixed
min-width so all rows visually align.

### FR4 — Tests

Two new tests added to `tests/test_web.py`:

- `test_level_counts_unaffected_by_level_filter` — tick DEBUG, query,
  assert that `result.level_counts['INFO']` is still 9 (not 0).
- `test_sector_counts_unaffected_by_sector_filter` — same shape for
  the sectors axis.

---

## 3. Implementation sketch

### `ulog/web/viewer/adapters.py`

Refactor `SQLiteAdapter.query` so each axis's count uses its own
"where minus this axis" clause:

```python
def query(self, filters: Filters, ...):
    full_where = self._build_where(filters)
    where_no_levels = self._build_where(replace(filters, levels=[]))
    where_no_loggers = self._build_where(replace(filters, loggers=[]))
    where_no_files = self._build_where(replace(filters, files=[]))

    with self._engine.begin() as conn:
        rows = ...  # uses full_where (page list)
        total = ... # uses full_where
        level_counts = self._count_by(conn, t.c.level, where_no_levels)
        file_counts = self._count_by(conn, t.c.file, where_no_files)
        logger_counts = self._count_by(conn, t.c.logger, where_no_loggers)
```

Same shape for `_filter_and_paginate` (in-memory JSONL/CSV adapters):
build per-axis filter copies, run the count loop with the appropriate
subset.

### `ulog/web/templates/ulog/list.html`

Replace each `<span class="text-slate-500…">{{ count }}</span>` with
a properly-spaced version:

```html
<span class="ml-2 text-slate-500 dark:text-slate-400 text-xs tabular-nums w-12 text-right">
    {{ count }}
</span>
```

`tabular-nums` keeps digit widths consistent (cosmetic but fixes
alignment for 4-digit counts). `w-12 text-right` reserves a fixed
column.

---

## 4. Non-functional requirements

| NFR | Budget |
|---|---|
| NFR-PERF-1 | Per-axis count queries triple the DB-roundtrip count (1 → 4) but each is cheap on the indexed columns. Page-load budget stays ≤ 500 ms on a 100K-record DB. |
| NFR-REL-1 | Output schema unchanged — `QueryResult.level_counts` etc. now contain different numbers, but the dict shape is identical. JSON `/api/records/` consumers see the new counts but no key changes. |
| NFR-DOC-1 | `/docs/sectors-and-files` adds a sentence: "Counts shown next to each filter value are GHOST counts — they reflect what you'd get if you added that value, not the current view." |

---

## 5. Definition of Done

- [ ] Adapters return ghost counts per axis.
- [ ] Sidebar template fixes spacing + tabular alignment.
- [ ] Two new tests pin the ghost-count behavior.
- [ ] Existing 69 tests still pass.
- [ ] `/docs/sectors-and-files.md` updated with the ghost-count note.
- [ ] Tag `v0.2.1` + push.
