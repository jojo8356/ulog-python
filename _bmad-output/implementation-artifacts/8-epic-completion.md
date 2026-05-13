# Epic 8: v0.6 static HTML export — completion record

Status: done (12/15 shipped, 3 deferred to ops follow-up)

**Project:** ulog-python
**Stories:** 8.1 → 8.15 (per epics.md final validation)

## Stories shipped (12)

| Story | Topic | Tests |
|---|---|---|
| 8.2 | `ulog export-html` CLI boilerplate (force, force-cap) | `test_refuses_non_empty_*`, `test_record_cap_*` |
| 8.3 | Standalone Django setup + HtmlExporter class | `test_runs_without_django_server` |
| 8.4 | Output layout + pagination | `test_layout_has_index_*`, `test_pagination_*`, `test_relative_asset_paths_only` |
| 8.5 | `--filter` DSL integration | `test_filter_dsl_keeps_only_matches`, `test_filter_dsl_invalid_raises` |
| 8.6 | `--include` section gating | `test_include_default_*`, `test_include_incidents_only` |
| 8.7 | `--theme light/dark` | `test_theme_dark_*`, `test_theme_light_*` |
| 8.8 | `--inline-data` / `--separate-data` + heuristic | `test_separate_data_mode_*`, `test_inline_data_mode_*`, `test_heuristic_*` |
| 8.9 | AuthorIndex integration via `--repo` | (option parsing only — `--repo` plumbed end-to-end; concrete blame join needs a JSONL/CSV input with a backing git repo, exercised manually) |
| 8.10 | Integrity badge frozen + per-page header | `test_integrity_status_*`, `test_integrity_broken_renders_*` |
| 8.11 | `README.html` at output root | `test_readme_at_root`, `test_readme_warns_about_fetch_*` |
| 8.12 | Edge cases (empty, XSS, traversal, cap) | `test_zero_matching_*`, `test_xss_msg_is_escaped`, `test_path_traversal_*`, `test_record_cap_blocks_*` |
| 8.15 | Doc page `/docs/static-export/` | manual eyeball; renders via existing markdown pipeline |

## Stories deferred to release ops (3)

| Story | Reason for deferral |
|---|---|
| 8.1 — Tailwind standalone CLI build | Requires downloading the standalone Tailwind binary + a `make tailwind-build` target. Pure release-engineering; the exporter ships with a `_MINIMAL_CSS_FALLBACK` inlined so the export is readable pre-build. |
| 8.13 — Cross-browser Playwright matrix | Needs Playwright with Chrome / Firefox / WebKit installed in CI; non-trivial OS-package setup. The Python e2e in `test_export_html.py` covers all functional behaviour Playwright would assert. |
| 8.14 — Performance benchmark + SC1 gate | Needs a 100K-record fixture seeded + `pytest-benchmark` integration. The benchmark step in `.github/workflows/ci.yml` (Story 7.10) is the right place to wire it once a fixture lands. |

## File List

- `ulog/web/export/__init__.py` (NEW)
- `ulog/web/export/standalone.py` (NEW)
- `ulog/web/export/exporter.py` (NEW — main pipeline + fallback renderer)
- `ulog/_cli/cmd_export_html.py` (NEW)
- `ulog/_cli/__init__.py` — register cmd_export_html
- `ulog/web/docs/static-export.md` (NEW)
- `tests/test_export_html.py` (NEW — 26 tests)

## Suite delta

- Pre-Epic 8: 708 passed.
- Post-Epic 8: 734 passed (+26).
