# Cheat sheet

One-screen reference for every `ulog` subcommand + Python API entry.

## CLI quick-look

```
ulog web      <db>                      open the inspection UI
ulog verify   <db>                      walk the chain, OK / BROKEN
ulog repair   --confirm <db>            archive orphans + truncate
ulog purge    --before <date> <db>      delete rotable rows
ulog enable-fts5 <db>                   opt-in full-text search

ulog correlate "<dsl>" --db <db>        over/under-represented dims
ulog bisect   "<regex>" --db <db>       first match in the chain
ulog replay   "<dsl>"  --db <db>        iterate (+ --to-pytest)
ulog trace    <trace_id> --db <db>      records sharing an OTel trace
ulog explain  --db <db> [--root <id>]   span waterfall tree

ulog incidents --status open --db <db>  list open · exit = count
ulog incidents --report --since 1m --db <db>   Markdown KPIs

ulog fix      resolve  --record-id N --writeup '…' --by 'X' --db <db>
ulog fix      {list,show,unresolve}     local fix DB sidecar

ulog import   <file>… --db <out>.sqlite          ingest external logs
ulog snapshot --format {log,jsonl,csv,html,pdf}  point-in-time export
ulog export-html <db> --output <dir>             static HTML bundle
ulog validate-resources --path .                 JSON/TOML/CSV/INI gate

ulog bug-cache {refresh,search,status,clear}     known-bugs cache
ulog solutions {keygen,publish,fetch}            community site client
```

## Python API quick-look

```python
import ulog

# v0.1+ — core
ulog.setup(format='qlnes', color='auto')
log = ulog.get_logger(__name__)
ulog.bind(request_id="abc")
with ulog.context(rom="alter_ego"):
    log.info("rendering")

# v0.2 — storage
ulog.setup(handlers=['stream', 'sql', 'json'], sql_url='sqlite:///./logs.sqlite')

# v0.5 — forensic chain + replay
ulog.setup(integrity='hash-chain', min_retention_days=30, ...)
ulog.replay(db, where_dsl='level=ERROR', on=lambda r: print(r['msg']))
ulog.correlate('level=ERROR', db='./logs.sqlite')
ulog.bisect('timeout', db='./logs.sqlite')

with ulog.replay_records([{'level': 'ERROR', 'msg': 'x'}]) as session:
    do_thing()
    assert session.matches(lambda r: r.level == 'ERROR')

# v0.5 — incidents
ulog.resolve('3f7c12a', by='Johan', note='restarted pool')
ulog.reopen('3f7c12a', reason='recurrence')
states = ulog.compute_states(records)

# v0.7 — spans
with ulog.span('setup_db'):
    with ulog.span('git_clone'):
        ...

# v0.10 — fleet probes (pytest decorator)
from ulog.fleet import probe
@probe(target='https://api.example.com/health', parents=['db.internal'])
def test_api_health(): ...

# v0.12 — call-stack capture
ulog.setup(capture_stack=True, capture_stack_locals=True)
```

## Setup options (v0.5+)

| Arg | Default | Purpose |
|---|---|---|
| `format` | `'qlnes'` | qlnes / simple / verbose / json / custom |
| `color` | `'auto'` | TTY-detect or 'always' / 'never' |
| `handlers` | `['stream']` | stream / sql / json / csv |
| `integrity` | `None` | `'hash-chain'` enables Epic 3 |
| `min_retention_days` | `0` | Rows past this date become immutable |
| `issue_template_url` | `None` | URL template for the "Open issue" button |
| `capture_stack` | `False` | Attach `traceback.extract_stack()` to every record |
| `capture_stack_locals` | `False` | Add `repr()` of frame locals (10 KB cap) |
| `profile` | `None` | `'prod'` / `'test'` / `'auto'` — sets sql_url path |

## Env vars (viewer-side)

| Var | Sets | Where |
|---|---|---|
| `ULOG_AUTHOR_REPO` | git repo for `git blame` + file:// source links | `ulog web --repo`, v0.4 |
| `ULOG_AUTHOR_INDEX_DISABLED` | skip the author indexer | `--no-author-index` |
| `ULOG_AUTHOR_INDEX_REBUILD` | drop + rebuild the authors cache | `--rebuild-author-index` |
| `ULOG_LOGS_PATH` | DB path | set by `ulog web <path>` |
| `ULOG_LOGS_KIND` | sqlite / jsonl / csv | auto-detected |
| `ULOG_DEBUG` | enable `/_qa/` + `--debug` features | `ulog web --debug` |
| `ULOG_RESOURCES_DIR` | enable the Resources sidebar panel | v0.9 phase 2 |
| `ULOG_SOURCE_BASE_URL` | GitHub-style permalink for file:line links | v0.12 phase 3 |
| `ULOG_SOLUTIONS_ENDPOINT` | self-hosted community site URL | v0.15 |
| `traceparent` | W3C OTel cross-service trace_id auto-bind | v0.5 / v0.6 |

## Exit codes

| Command | 0 | 1 | 2 |
|---|---|---|---|
| `verify` | OK | BROKEN | missing DB / arg error |
| `repair` | repaired | already clean | missing flag |
| `purge` | rows deleted | retention floor blocked | invalid date |
| `incidents --status open` | 0 open | N open (exit = count) | missing DB |
| `validate-resources` | 0 broken | N broken (exit = count) | bad path / unknown type |
| `fix show <sig>` | found | not found | missing DB |
| `bug-cache search <sig>` | found | not found | missing source-file |

## Decision references

- [STABILITY.md](../STABILITY.md) — the 7 invariants the contract preserves forever.
- [BENCHMARK.md](../BENCHMARK.md) — SC1/SC2/SC7 baselines.
- [RELEASE_NOTES.md](../RELEASE_NOTES.md) — `ulog-web` → `ulog web` migration.
- [docs/prds/](../docs/prds/) — every PRD with full design rationale.
