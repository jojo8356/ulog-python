# Sectors and files explained

Two filters in the sidebar drill into your codebase: **Sectors**
(logger names) and **Files** (`record.filename`). They look similar
but answer different questions.

## Sector tree

A "sector" is a hierarchical prefix of `record.name` (the logger
name). When your code does `logging.getLogger("qlnes.audio.renderer")`,
ULog records the full string. The UI splits it on `.` and rolls up:

```
qlnes (147)
├── audio (89)
│   ├── renderer (56)
│   ├── engine (24)
│   └── in_process (9)
├── cli (43)
└── io.errors (15)
```

Click `audio` to filter to all records whose logger starts with
`qlnes.audio`. Click `audio.renderer` for just that subtree.

**When to use sectors:** "where in the codebase did this happen?" —
logger names map to *modules* (the `__name__` convention) so they
follow your package hierarchy.

## File filter

`record.filename` is the source file the log call lives in. e.g.
`renderer.py` instead of `qlnes.audio.renderer`. If your code uses
the standard `log = logging.getLogger(__name__)` pattern then files
and sectors map 1-to-1 — but the UI shows both because:

1. **Different code in the same module** — `qlnes.cli` (logger) might
   call functions in `qlnes.audio.renderer` (file), so a single record
   has logger `qlnes.cli` but file `renderer.py`.
2. **Inherited loggers** — a child class inheriting from a base in
   another file logs with the base's `__name__`. The file filter
   surfaces where the actual call site is.

**When to use files:** "which line of code did this come from?" —
faster to triage than reading logger names if you're already familiar
with the source layout.

## Worked example: "find every error in the audio renderer in the last hour"

1. Tick **ERROR** under Level (left sidebar, top).
2. Click `qlnes.audio.renderer` under Sectors.
3. In Time range, type `from = 2026-05-04T13:00:00Z` (or the last hour
   in UTC).
4. Hit **Apply**.

The list shows only matching records. Click any row to open the full
detail view with the traceback.

## Worked example: "did the bug come from the cli command or from inside the renderer?"

The log line you saw says `qlnes: error: ROM not found`. You want
to know if the error originated from the CLI argument-parsing code
or from inside `render_rom_audio_v2`.

1. Search `q = "ROM not found"`.
2. Look at the **File** column for the matching row. If it's
   `cli.py:85`, the CLI's pre-flight raised; if it's
   `renderer.py:280`, the renderer raised mid-render.

Sectors alone wouldn't tell you — the same `qlnes.cli` logger could
be writing both messages. The file filter pinpoints the source.

## Ghost counts (v0.2.1)

The numbers shown next to each filter value (level, sector, file)
are **ghost counts** — they reflect what you'd get if you added
that value to the current filter, NOT the count for the currently
active query. So:

- If you tick `ERROR`, the `INFO` row still shows `(9)` — meaning
  "if you ALSO tick INFO, you'd see 9 more records on top of the
  ERRORs". The 9 doesn't drop to 0 just because INFO isn't currently
  selected.
- Same for sectors: tick `qlnes.audio.engine`, and `qlnes.web` still
  shows its count.

Why: this is the "ghost count" UX pattern from Datadog/Sentry/Grafana.
Without it, multi-axis exploration becomes painful — you'd have to
untick a value, see the counts, then re-tick.

## "By directory" toggle (planned in v0.3)

When the file list grows past 30 entries, group files by their parent
directory: `qlnes/audio/*.py` collapses into `qlnes/audio (123)`.
Click to expand. v0.2 lists files flat with counts; v0.3 ships the
toggle.
