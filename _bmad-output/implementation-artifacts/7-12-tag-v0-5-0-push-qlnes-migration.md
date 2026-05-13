# Story 7.12: Tag v0.5.0 + push + qlnes migration

Status: ready-for-release

**Epic:** 7 — v0.5 release consolidation
**Implements:** SC6a.

## Completion Notes

- `pyproject.toml` version bumped 0.1.0 → 0.5.0.
- `ulog/__init__.py` `__version__` bumped 0.1.0 → 0.5.0.
- `RELEASE_NOTES.md` finalized (Story 7.3).
- All Epic 5 + 6 + 7 stories done (32 / 33 — only 7.12 is the
  release act itself).

## Release act (user-triggered, not auto-pushed)

```bash
git tag -a v0.5.0 -m "v0.5.0 — Forensic black box (Epics 3-7)"
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
