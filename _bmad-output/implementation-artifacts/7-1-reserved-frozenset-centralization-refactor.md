# Story 7.1: `_RESERVED` frozenset centralization refactor

Status: done

**Epic:** 7 — v0.5 release consolidation
**Implements:** Decision C4.

## Completion Notes

- New `ulog/_reserved.py` exporting canonical `RESERVED: frozenset[str]`.
- `ulog/formatters.py`, `ulog/handlers/sql.py`, `ulog/handlers/csv_file.py`
  now import `RESERVED as _RESERVED` from the shared module.
- 3 duplicated inline frozensets removed.

## File List

- `ulog/_reserved.py` (NEW)
- `ulog/formatters.py`, `ulog/handlers/sql.py`, `ulog/handlers/csv_file.py` — refactored imports
