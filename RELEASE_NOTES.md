# Release notes

## v0.5.0 — Forensic black box (unreleased)

### Headlines

- **Hash-chained SQLite storage** — every record links to the previous
  via SHA-256; `ulog verify` (re)plays the chain and reports OK / BROKEN
  with the exact tampered chain position.
- **Replay / correlate / bisect** — Python API + CLI for forensic
  exploration of a chain.
- **Incident lifecycle** — `ulog.resolve()` / `ulog.reopen()` +
  `ulog incidents --status` (CI gate) + `--report --since` (Markdown
  KPIs).
- **Cross-service & UI** — OTel auto-bind (`traceparent` env / contextvar,
  zero PyPI dep), `ulog trace <id>`, integrity badge on every page,
  multi-track 4-axis SVG view, issue-template URL button on the detail
  page.

### Breaking: `ulog-web` is now `ulog web`

The standalone `ulog-web` console script has been removed. Every
entry point is now under the single `ulog <subcommand>` dispatcher
(Decision C1).

**Migrate:** replace `ulog-web <path>` with `ulog web <path>`.

```bash
# Before (v0.4)
ulog-web /var/log/myapp.sqlite --debug --repo .

# After (v0.5)
ulog web /var/log/myapp.sqlite --debug --repo .
```

All flags are identical — `--port`, `--host`, `--no-open`, `--repo`,
`--no-author-index`, `--rebuild-author-index`, `--debug` are unchanged.
The only difference is the invocation prefix.

Scripts that hard-coded `ulog-web` will fail with "command not found"
after upgrade. A one-shot sed across your repo:

```bash
grep -rl 'ulog-web' . | xargs sed -i 's/\bulog-web\b/ulog web/g'
```

### Added (Epic 3 — chain integrity)

- Schema extension: `chain_pos`, `record_hash`, `prev_hash`,
  `immutable`, `is_replay` columns on the `logs` table.
- `setup(integrity="hash-chain", min_retention_days=N)`.
- CLI: `ulog verify`, `ulog repair --confirm`, `ulog purge --before`.
- `<db>.verify_state.json` sidecar — last-check audit trail.

### Added (Epic 4 — queryability)

- `ulog.replay(db, where_dsl=...)` — iterate records via filter DSL.
- `ulog.testing.replay_records(...)` — pytest helper.
- `ulog correlate` / `ulog bisect` / `ulog replay --to-pytest`.
- Filter DSL parser (level / logger / context fields, AND/OR/NOT).

### Added (Epic 5 — incident lifecycle)

- `ulog.resolve(incident_hash, by, note)` + `ulog.reopen(hash, reason)`.
- `ulog.compute_states(records)` — chain walk, latest-wins.
- `ulog incidents --status open|closed|reopened|all` (exit code = open
  count for CI gates).
- `ulog incidents --report --since 1m` — Markdown KPIs (MTTR, P95,
  top closers, etc.).

### Added (Epic 6 — cross-service & UI)

- OTel auto-bind from `traceparent` env or `_OTEL_TRACE_CONTEXT`
  contextvar.
- `ulog trace <trace_id>` CLI.
- `setup(issue_template_url="https://...?title={msg}&body={body}")`
  — "Open issue" button on detail view, URL-encoded with a 5-record
  body window.
- `/multi-track` Django view — 4 horizontal SVG strips (level /
  service / author / file) with mute toggles.
- Integrity badge in `base.html` header — OK / BROKEN / never-verified.
- Locale-aware glyph fallback (`∞ ⚠ ✓` → `inf WARN OK` when locale
  is not UTF-8).

### Removed

- `ulog-web` console script (see migration above).

### Migration checklist

- [ ] Replace every `ulog-web ...` invocation with `ulog web ...`.
- [ ] Re-pin in dependent projects: `ulog ~= 0.5.0`.
- [ ] Existing v0.4 SQLite DBs continue to work in read-only mode.
  To enable chain integrity on an existing DB, the SQLHandler emits a
  copy-paste `ALTER TABLE` SQL block on first write — apply it once
  and chain mode kicks in.

---

## v0.4.x and earlier

See git tags + the `docs/prds/` directory.
