# Troubleshooting

Common gotchas, with the fix.

## "SQLite says database is locked"

Another process has the file open. Close it (the IDE's "DB browser",
another `ulog-web` instance, …), or enable WAL mode on the DB:

```sql
PRAGMA journal_mode=WAL;
```

The default `SQLHandler` opens the file in autocommit mode; multiple
writers don't deadlock unless something holds an exclusive transaction.

## "JSON file too big to load"

The JSONL adapter loads the whole file into memory in v0.2. For a
10M-record file that's fine on a workstation; on a 4GB-RAM CI it
won't be. Workarounds:

1. Split the file by time: `awk -F'"ts":"' '{print > substr($2,1,10)".jsonl"}' big.jsonl`
2. Migrate to SQL: `sqlite3 logs.sqlite < schema.sql; ulog-import-jsonl big.jsonl logs.sqlite`
   (the import script lives in `tools/`, see source).

v0.3 will add a streaming JSONL adapter that filters without loading
the full file.

## "Records missing"

Three places to check:

1. **Logger level**: `ulog.setup(level='WARNING')` filters out INFO.
2. **Handler list**: `ulog.setup(handlers=['stream'])` won't write to a DB.
3. **Buffered batch**: `SQLHandler` buffers up to `sql_batch_size`
   records before flushing. Call `handler.flush()` (or wait for
   process exit, which `atexit` covers) before reading the DB.

## "CSV has weird quotes"

Excel's dialect quotes fields containing `,` `"` or `\n`. If you're
piping the CSV to a tool that expects different quoting, switch:

```python
ulog.setup(handlers=['csv'], csv_path='./logs.csv', csv_dialect='unix')
```

## "Browser won't open"

The `ulog-web` script tries to launch the system browser via
`webbrowser.open`. On headless servers this fails. Use:

```bash
ulog-web --no-open --port 8080 ./logs.sqlite
```

Then visit `http://127.0.0.1:8080` from your local machine via SSH
tunnel: `ssh -L 8080:localhost:8080 user@host`.

## "Tailwind looks broken"

The v0.2 prototype uses the Tailwind CDN script. If it's blocked
(corporate firewall, no internet), download the standalone Tailwind
binary and pre-compile:

```bash
make web-tailwind
```

The compiled CSS is shipped under `ulog/web/static/ulog/tailwind.css`.

## "Postgres connection refused"

Connection string format:

```
postgresql://user:pass@host:5432/dbname
```

If the DB doesn't exist, create it first (`createdb dbname`). ULog's
`SQLHandler` creates the table but not the DB.

## "Django app won't start"

Check the install brought the optional deps:

```bash
pip install ulog[web]
```

If you're inside a venv, double-check `which python` matches your
expected env.

## v0.5: "`ulog-web`: command not found"

The standalone `ulog-web` script was removed in v0.5. Everything now
lives under the single `ulog` dispatcher:

```bash
ulog web ./logs.sqlite       # was: ulog-web ./logs.sqlite
ulog verify ./logs.sqlite
ulog incidents --status open --db ./logs.sqlite
```

One-shot migration:

```bash
grep -rl 'ulog-web' . | xargs sed -i 's/\bulog-web\b/ulog web/g'
```

See `RELEASE_NOTES.md` at the repo root.

## v0.5: `ulog verify` reports BROKEN

The chain is corrupt at the reported `chain_pos`. Run
`ulog repair --confirm <db>` to archive the orphaned rows to a
sidecar JSONL and truncate the chain to the last-good position.
The viewer's header pill turns red and `setup(integrity="hash-chain")`
refuses to re-open the DB until repair clears the state.

Full troubleshooting flow: [v0.5 — Forensic black box](v0.5-forensic-archive).
