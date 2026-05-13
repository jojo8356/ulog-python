# Coverage matrix — FR / edge-case → test mapping

Story 7.11 / SC3 (secondary indicator). Each functional requirement
and each PRD §2.3 edge case must map to ≥1 passing test name.

Rows below are sorted by Epic. Where one test covers multiple FRs,
the same test name appears multiple times — that's expected (one
behavior, many FRs).

---

## Epic 1 — Test integration (FR51 → FR69)

| FR | Description | Test(s) |
|---|---|---|
| FR51 | Plugin entry-point registration | `tests/test_pytest_plugin.py::test_plugin_registered_via_entry_point` |
| FR52 | Plugin OFF by default | `tests/test_pytest_plugin.py::test_plugin_off_without_setup_or_flag` |
| FR53 | `--ulog-disable` short-circuit | `tests/test_pytest_plugin.py::test_ulog_disable_flag` |
| FR54 | started + outcome records emitted | `tests/test_pytest_plugin.py::test_started_and_outcome_emitted` |
| FR55 | Stable test_id format | `tests/test_pytest_plugin.py::test_stable_test_id` |
| FR56 | Traceback on failure | `tests/test_pytest_plugin.py::test_traceback_on_failure` |
| FR57 | Phase field (setup/call/teardown) | `tests/test_pytest_plugin.py::test_phase_field` |
| FR58 | duration_s populated | `tests/test_pytest_plugin.py::test_duration_field` |
| FR59 | bind/unbind test_id | `tests/test_pytest_plugin.py::test_test_id_propagation` |
| FR60 | App records inherit test_id | `tests/test_pytest_plugin.py::test_app_records_inherit_test_id` |
| FR61 | Fixture records carry test_id | `tests/test_pytest_plugin.py::test_fixture_test_id_inheritance` |
| FR62 | Tests sidebar | `tests/test_tests_sidebar.py` |
| FR63 | Failed-only quick filter | `tests/test_tests_sidebar.py::test_failed_only_filter` |
| FR64 | Slowest top 10 | `tests/test_tests_sidebar.py::test_slowest_top_10` |
| FR65 | Click test → filter | `tests/test_tests_sidebar.py::test_click_test_filters_records` |
| FR66 | Detail view test-context panel | `tests/test_detail_view_e2e.py::test_test_context_panel` |
| FR67 | `--ulog-db PATH` override | `tests/test_cli_flags_e2e.py::test_ulog_db_flag` |
| FR68 | `--ulog-disable` | `tests/test_cli_flags_e2e.py::test_ulog_disable_flag` |
| FR69 | `--ulog-summary` | `tests/test_cli_flags_e2e.py::test_ulog_summary_flag` |

## Epic 2 — Author attribution (FR70 → FR81)

| FR | Description | Test(s) |
|---|---|---|
| FR70 | AuthorIndex API | `tests/test_author_index.py` |
| FR71 | unique_file_line_pairs | `tests/test_author_index.py::test_unique_file_line_pairs` |
| FR72 | --repo flag | `tests/test_cli_repo_flags.py` |
| FR73 | --no-author-index flag | `tests/test_cli_repo_flags.py::test_no_author_index_flag` |
| FR74 | --rebuild-author-index flag | `tests/test_cli_repo_flags.py::test_rebuild_author_index_flag` |
| FR75 | Authors cache (SQLite sidecar) | `tests/test_author_cache.py` |
| FR76 | Authors sidebar | `tests/test_authors_sidebar.py` |
| FR77 | Multi-select OR + URL persistence | `tests/test_authors_filter.py` |
| FR78 | show_unknown toggle | `tests/test_show_unknown_toggle_e2e.py` |
| FR79 | Ghost-count contract | `tests/test_authors_summary.py` |
| FR80 | Detail-view Authored-by panel | `tests/test_authors_detail_panel.py` |
| FR81 | `/diff/<sha>/` view | `tests/test_diff_view.py` + `test_diff_security_e2e.py` |
| §2.3 ec1 (v0.4) | Author untracked file | `tests/test_author_edge_cases.py::test_untracked_file` |
| §2.3 ec2 (v0.4) | Author with non-UTF-8 email | `tests/test_author_edge_cases.py::test_non_utf8_email` |
| §2.3 ec3 (v0.4) | Cache invalidation on .git/HEAD change | `tests/test_author_cache.py::test_invalidates_on_git_head_change` |
| §2.3 ec4 (v0.4) | Re-run with no changes (cached fast path) | `tests/test_author_cache.py::test_fast_path_on_unchanged_repo` |

## Epic 3 — Chain integrity (FR82 → FR95)

| FR | Description | Test(s) |
|---|---|---|
| FR82 | Hash-chain columns | `tests/test_chain.py::test_schema_columns_present` |
| FR83 | record_hash formula | `tests/test_chain.py::test_record_hash_formula` |
| FR84 | Immutable trigger | `tests/test_chain.py::test_immutable_trigger_blocks_update` |
| FR85 | SchemaError upgrade SQL | `tests/test_chain_emit.py::test_schema_error_upgrade_message` |
| FR86 | ChainWriter protocol | `tests/test_chain.py::test_chain_writer_protocol` |
| FR87 | WAL + BEGIN IMMEDIATE | `tests/test_chain_concurrency.py` |
| FR88 | setup integrity / min_retention_days | `tests/test_setup_v05_params.py` |
| FR89 | `ulog verify` CLI | `tests/test_cli_verify.py` |
| FR90 | `ulog repair --confirm` | `tests/test_cli_repair.py` |
| FR91 | `ulog purge --before` | `tests/test_cli_purge.py` |
| FR92 | verify_state.json sidecar | `tests/test_verify_state_sidecar.py` |
| FR93 | Multi-process chain unbroken | `tests/test_chain_concurrency.py::test_8_writers_10k_records` |
| §2.3 ec1 (v0.5 storage) | BROKEN blocks chain setup | `tests/test_chain_edge_cases.py::test_broken_blocks_setup` |
| §2.3 ec2 (v0.5 storage) | immutable_when raise → fail-safe | `tests/test_chain_edge_cases.py::test_immutable_when_raises` |
| §2.3 ec3 (v0.5 storage) | Tampered record_hash detected | `tests/test_chain_edge_cases.py::test_tampered_hash_detected` |
| §2.3 ec4 (v0.5 storage) | Retention-floor regression | `tests/test_chain_edge_cases.py::test_retention_floor_protects` |

## Epic 4 — Queryability (FR96 → FR104)

| FR | Description | Test(s) |
|---|---|---|
| FR96 | replay() core + MappingProxyType | `tests/test_replay_core.py` |
| FR97 | is_replaying contextvar | `tests/test_replay_state.py` |
| FR98 | replay_records context manager | `tests/test_replay_core.py::test_replay_records_context_manager` |
| FR99 | Filter DSL grammar | `tests/test_filter_dsl.py` |
| FR100 | correlate() lift formula | `tests/test_correlate.py` |
| FR101 | bisect() over chain | `tests/test_bisect.py` |
| FR102 | `ulog replay` CLI + --to-pytest | `tests/test_cli_queryability.py` |
| FR103 | `ulog correlate` CLI | `tests/test_cli_queryability.py::test_correlate_cli` |
| FR104 | `ulog bisect` CLI | `tests/test_cli_queryability.py::test_bisect_cli` |
| §2.3 ec1 (v0.5 query) | Write attempt during replay → silent skip | `tests/test_replay_to_pytest.py::test_replay_record_is_replay_flag` |

## Epic 5 — Incident lifecycle (FR105 → FR108)

| FR | Description | Test(s) |
|---|---|---|
| FR105 | resolve() API + FK validation | `tests/test_incidents.py::test_resolve_emits_resolved_record_with_resolves_field` |
| FR106 | reopen() + latest-wins | `tests/test_incidents.py::test_compute_states_latest_wins_resolve_reopen_resolve` |
| FR107 | `ulog incidents --status` exit code | `tests/test_incidents_cli.py::test_incidents_status_open_exit_code_equals_open_count` |
| FR108 | `--report --since` Markdown | `tests/test_incidents_cli.py::test_incidents_report_markdown_has_required_rows` |
| §2.3 ec1 (v0.5 incidents) | resolve unknown → LookupError | `tests/test_incidents.py::test_resolve_unknown_raises_no_record_emitted` |
| §2.3 ec2 (v0.5 incidents) | resolve already-resolved → allowed | `tests/test_incidents.py::test_resolve_twice_emits_two_records` |

## Epic 6 — Cross-service & UI (FR109 → FR115)

| FR | Description | Test(s) |
|---|---|---|
| FR109 | OTel auto-bind from env/contextvar | `tests/test_otel_bind.py` |
| FR110 | `ulog trace <id>` CLI | `tests/test_cli_trace.py` |
| FR111 | Issue-template URL + URL-encoded + body window (G3) | `tests/test_issue_url.py` |
| FR112 | Multi-track adapter + Django view | `tests/test_multi_track_adapter.py` + `test_multi_track_view.py` |
| FR113 | Integrity badge 3-state | `tests/test_integrity_badge.py` |
| FR114 | Detail Resolves/Resolved-by cross-links | `tests/test_incidents_detail_links.py` |
| FR115 | Sidebar Incidents quick filters | `tests/test_incidents_sidebar.py` |
| NFR-SEC-51 | Issue URL placeholders URL-encoded | `tests/test_issue_url.py::test_render_encodes_spaces_and_quotes` |
| Gap G3 | 5-record body window | `tests/test_issue_url.py::test_body_window_picks_5_records_around_target` |
| Gap G4 | OTel silent no-op when absent | `tests/test_otel_bind.py::test_no_trace_when_env_absent` |
| §2.3 ec1 (v0.5 cross-service) | OTel SDK absent | `tests/test_otel_bind.py` (entire module — no SDK import) |
| NFR-PORT-50 | Locale glyph fallback | `tests/test_glyphs.py` |

## Epic 7 — Release consolidation (FR116 → FR117)

| FR | Description | Test(s) |
|---|---|---|
| FR116 | v0.5-forensic-archive doc page | `tests/test_qa_view.py` (renders + linked from index) |
| FR117 | Existing doc pages updated | manual eyeball (doc page changes only) |
| I5 / SC5 | qlnes byte-stable contract | `tests/test_qlnes_compat.py` |
| SC4 / NFR-DEP-50 | `dependencies = []` CI gate | `.github/workflows/ci.yml::regression-gate-zero-deps` |
| SC1 | `ulog verify` ≤ 5s / 100K | `tests/bench_verify.py` (advisory) |
| SC2 | `ulog correlate` ≤ 500ms | `tests/bench_correlate.py` (advisory) |
| SC7 | Multi-track TTI ≤ 200ms | `tests/bench_multitrack.py` (advisory) |

---

## How to regenerate this matrix

For now, manual. A future v0.7 patch could parse the FR identifiers
from each story doc + `grep` the test files for matching FR
references; that's out of scope for v0.5.

Verify the matrix is in sync:

```bash
# Every test name in the matrix must exist in the suite.
for t in $(grep -oE "tests/test_[a-z_]+\.py::test_[a-z_0-9]+" tests/coverage_matrix.md | sort -u); do
  if ! pytest --collect-only -q "$t" >/dev/null 2>&1; then
    echo "MISSING: $t"
  fi
done
```
