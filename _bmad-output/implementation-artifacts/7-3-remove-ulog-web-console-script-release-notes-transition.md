# Story 7.3: Remove `ulog-web` console_script + RELEASE_NOTES.md transition entry

Status: done

**Epic:** 7 — v0.5 release consolidation
**Implements:** Decision C1, Gap G6.

## Completion Notes

- `pyproject.toml` `[project.scripts]` now contains only `ulog =
  "ulog._cli:main"`.
- New `RELEASE_NOTES.md` at repo root with prominent v0.5
  "Breaking: `ulog-web` is now `ulog web`" section + one-shot sed
  migration command.

## File List

- `pyproject.toml` — `ulog-web` entry removed
- `RELEASE_NOTES.md` (NEW)
