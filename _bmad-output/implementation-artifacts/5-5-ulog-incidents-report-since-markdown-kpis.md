# Story 5.5: `ulog incidents --report --since` Markdown KPIs

Status: done

**Epic:** 5 — v0.5 Incident lifecycle
**Story key:** `5-5-ulog-incidents-report-since-markdown-kpis`
**Implements:** FR108.

## Story

As a tech lead writing a postmortem,
I want `ulog incidents --report --since 1m` to output aggregated
KPIs (opened / closed / net debt / MTTR / P95 / reopens / top
closers) as Markdown,
so that I can paste it directly into a postmortem doc.

## Acceptance Criteria

1. `--report` requires `--since <span>` (exit 2 if missing).
2. `--since` accepts `Nm` / `Nd` / `Nh` / `Nw` / `Ny` or ISO date.
3. Output is a valid Markdown table:
   `# Incidents report — since <iso>` + a `| Metric | Value |` table.
4. Rows: Opened, Closed, Net debt, MTTR, P95, Reopens, Top closers.
5. MTTR / P95 computed from open-ts → first resolve-ts pairs.
6. Top closers ranked by `context.by`.

## Dev Agent Record

### Completion Notes List

- Implemented in `ulog/_cli/cmd_incidents.py` (`_build_report`).
- 3 / 3 tests for report mode green (markdown shape, --since
  requirement, missing-db handling).

### File List

- `ulog/_cli/cmd_incidents.py`
- `tests/test_incidents_cli.py`
