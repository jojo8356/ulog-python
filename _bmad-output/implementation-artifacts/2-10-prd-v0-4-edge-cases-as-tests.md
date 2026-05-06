# Story 2.10: PRD-v0.4 §2.3 edge cases as tests

Status: done

**Epic:** 2 — v0.4 Author attribution
**Story key:** `2-10-prd-v0-4-edge-cases-as-tests`
**Implements:** SC4 — each of the 5 edge cases listed in PRD-v0.4 §2.3 covered by ≥1 test
**Source:** PRD-v0.4 §2.3 + epics.md Story 2.10

## Story
As a release manager, I want each PRD-v0.4 §2.3 edge case covered by ≥1 test, so the indexer's behavior on git pathologies is regression-protected.

## Edge cases & coverage map

| Case | Test |
|---|---|
| Line deleted (line out-of-range) | `tests/test_author_index.py::test_line_out_of_range_returns_none` (Story 2.1) — already covered |
| File renamed (`git mv`) | NEW `tests/test_author_edge_cases.py::test_file_renamed_falls_through_to_unknown` |
| Squashed/rebased commit (cached sha unreachable) | `tests/test_diff_view.py::test_diff_view_unknown_sha_returns_404` (Story 2.9) — already covered |
| Submodule path | NEW `tests/test_author_edge_cases.py::test_submodule_blame_resolves` (best-effort: skipped if `git submodule` unavailable) |
| No git at --repo | `tests/test_cli_repo_flags.py::test_resolve_repo_flag_no_git_warns` (Story 2.2) — already covered |

## Acceptance Criteria
- **AC1** — All 5 edge cases above have ≥1 test that exercises them.
- **AC2** — Tests pass on Linux + macOS (Windows submodule support best-effort).
- **AC3** — `tests/test_author_edge_cases.py` adds 4-5 new tests; existing 3 cases reuse current coverage.

## Dev Agent Record
### File List
- `tests/test_author_edge_cases.py` — NEW

### Completion Notes
Suite at 258 + 4 = 262/262.
