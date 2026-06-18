# Story 7.12: Tag v0.5.0 + push + qlnes migration

Status: done

**Epic:** 7 — v0.5 release consolidation
**Implements:** SC6a.

## Completion Notes

- `pyproject.toml` version bumped 0.1.0 → 0.5.0.
- `ulog/__init__.py` `__version__` bumped 0.1.0 → 0.5.0.
- `RELEASE_NOTES.md` finalized (Story 7.3).
- All Epic 5 + 6 + 7 stories done (32 / 33 — only 7.12 is the
  release act itself).

## Release act

Completed locally on 2026-06-18:

```bash
git tag -a v0.5.0 d40c2bb -m "v0.5.0 - Forensic black box (Epics 3-7)"
git push origin v0.5.0
gh release create v0.5.0 --repo jojo8356/ulog-python --notes-file RELEASE_NOTES.md --title "v0.5.0 - Forensic black box"
```

Tag target:

- `d40c2bb` — `feat(v0.5): Epic 7 release consolidation — v0.5.0 ready (12 stories)`

GitHub release:

- https://github.com/jojo8356/ulog-python/releases/tag/v0.5.0

qlnes SC6a migration completed on 2026-06-18:

- Repo: `jojo8356/qlnes`
- Commit: `32d4143` — `chore(deps): pin ulog v0.5`
- Change: `requirements.txt` now pins `ulog[storage,web] ~= 0.5.0` and uses the `ulog web` command name in dependency comments.

Original release-ops commands:

```bash
git push origin v0.5.0
gh release create v0.5.0 --notes-file RELEASE_NOTES.md
```

Then within 30 days (per SC6a):

```bash
# In the qlnes repo
sed -i 's/ulog ~= 0\.[0-9.]\+/ulog ~= 0.5.0/' pyproject.toml
```

## File List

- `pyproject.toml` — version
- `ulog/__init__.py` — `__version__`
