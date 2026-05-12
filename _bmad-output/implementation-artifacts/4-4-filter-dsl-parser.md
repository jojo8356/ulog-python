# Story 4.4: Filter DSL parser

Status: done

**Epic:** 4 — v0.5 Queryability
**Story key:** `4-4-filter-dsl-parser`
**Implements:** Decision C5 (parsed, NEVER eval'd), NFR-SEC-50 (no shell injection), Gap G7 (AND > OR precedence).
**Built on:** Story 4.1 (`replay()` accepts `where` SQL or `where_fn` predicate).
**Foundation for:** Story 4.5 (`correlate()` uses the SQL compile path for `GROUP BY`), Story 4.8 (CLI subcommands take `--filter "..."` strings).

## Story

As a **CLI user composing filters**,
I want **a small grammar (`level=ERROR AND date>-30min`, `key~regex`, parentheses, etc.) parsed (NEVER `eval`'d) and compiled to either a parameterised SQL expression OR a Python predicate**,
so that **I can express queries without shell-injection risk** and the same filter works in `replay()`, `correlate()`, and the CLI.

## Acceptance Criteria

1. **`ulog._filter_dsl.parse(dsl: str) -> FilterExpr`** returns a typed AST. Calls NEVER reach `eval()` / `exec()` / SQLAlchemy `text()` with interpolated user data.
2. **AST node types**: `And`, `Or`, `Cmp` (key, op, value), `Paren` (transparent wrapper). All frozen dataclasses.
3. **Operators supported**: `=`, `!=`, `>`, `>=`, `<`, `<=`, `~` (regex match).
4. **Identifier syntax**: `[a-zA-Z_][a-zA-Z0-9_.]*` (dots for nested context fields like `context.tenant_id`).
5. **Value syntax**: integer literal (`-?\d+`), float (`-?\d+\.\d+`), single-quoted or double-quoted string, identifier (e.g. `level=ERROR`), relative date (`-30min`, `-1h`, `-7d`, `-3600s`).
6. **Precedence**: AND > OR. Parentheses override (Gap G7). `level=ERROR OR level=WARN AND service=payment` parses as `level=ERROR OR (level=WARN AND service=payment)`.
7. **`FilterExpr.to_sql() -> tuple[str, dict[str, Any]]`** returns `(where_clause, params)` — the `where_clause` uses named bind params (`:p0`, `:p1`, …), `params` maps them to values. No string-interpolation of user values into SQL.
8. **`FilterExpr.to_predicate() -> Callable[[Mapping[str, Any]], bool]`** returns a closure that evaluates the AST against a record dict. Supports nested keys (`context.tenant_id` → `record["context"]["tenant_id"]`).
9. **Regex op `~`** uses `re.search(pattern, str(value))`. Empty match → False. Predicate side runs `re.search`; SQL side compiles to `<col> REGEXP <pattern>` (SQLite has a hook; needs the registered REGEXP function — Story 4.4 ships a tiny `_register_regexp(engine)` helper).
10. **Relative dates** evaluate against `datetime.now()` at COMPILE time (`date>-30min` becomes a fixed timestamp captured at compile, not re-evaluated each row). Documented.
11. **Parse errors raise `FilterParseError`** with a clear message (`"expected operator at column 14"`). Injection attempts (`level=ERROR; DROP TABLE logs`) → ParseError; never reach SQL.
12. **Whitespace tolerant** — `level = ERROR AND  service=p` parses identically to `level=ERROR AND service=p`.
13. **Public API surface**: `from ulog._filter_dsl import parse, FilterExpr, FilterParseError`. Module is private (`_` prefix) but the symbols are stable per Story 4.8 (CLI uses them).
14. **`ulog.replay()` gains `where_dsl=` kwarg** — when set, parses + compiles to `where_fn` (predicate path; safest, no need for replay-side params plumbing). Mutually exclusive with `where` AND `where_fn` (extend Story 4.1's `at most one` check).
15. **Tests** — `tests/test_filter_dsl.py` (NEW):
    - Tokenizer: identifiers, integers, floats, strings (both quote styles), keywords (AND/OR/and/or — case-insensitive), operators, relative dates.
    - Parser: each operator, precedence (AND > OR), parentheses, nested.
    - `to_sql()`: parameterised output for each op, named-bind consistency.
    - `to_predicate()`: each op, nested-key resolution, regex.
    - Injection: `level=ERROR; DROP TABLE` raises ParseError. `level="x' OR '1'='1"` parses as a literal value (NOT broken out into SQL).
    - Replay integration: `ulog.replay(db, where_dsl='level=ERROR', on=cb)` works end-to-end on a seeded DB.
    - Edge cases: empty string → ParseError. Just whitespace → ParseError. Unbalanced paren → ParseError.

## Tasks / Subtasks

- [ ] **Task 1 — `ulog/_filter_dsl.py` (NEW)** — tokenizer + parser + 2 compilers, ~ 350 LOC. Stdlib only.
- [ ] **Task 2 — Replay integration** — add `where_dsl=` to `replay()` + extend mutex check + auto-compile to `where_fn`.
- [ ] **Task 3 — Tests** — `tests/test_filter_dsl.py` with ~ 35 tests.
- [ ] **Task 4 — Validation** — pytest / mypy / ruff / deptry clean.

## Dev Notes

### Snippet — tokenizer + parser (skeleton)

```python
# ulog/_filter_dsl.py
"""Filter DSL parser + 2 compilers (SQL paramétré + Python predicate).

Grammar (EBNF):
    filter      ::= or_expr
    or_expr     ::= and_expr ( "OR" and_expr )*
    and_expr    ::= term ( "AND" term )*
    term        ::= "(" filter ")" | comparison
    comparison  ::= identifier op value
    op          ::= "=" | "!=" | ">" | ">=" | "<" | "<=" | "~"
    identifier  ::= LETTER ( LETTER | DIGIT | "_" | "." )*
    value       ::= STRING | NUMBER | IDENT | REL_DATE
    REL_DATE    ::= "-" NUMBER ( "s" | "min" | "h" | "d" )

NEVER calls eval()/exec(). SQL compilation produces parameterised
bind-vars only. Decision C5 + Gap G7.
"""

from __future__ import annotations
import datetime
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

# ... tokenizer + parser + AST + compile_to_sql + compile_to_predicate
```

(Full impl ~350 LOC; this snippet is illustrative.)

### Architecture compliance

- **Decision C5 (no eval):** [Source: architecture.md] — DSL parser never invokes Python eval().
- **Gap G7 (AND > OR):** [Source: architecture.md, line 1263] — documented + tested.
- **NFR-SEC-50:** parameterised SQL only. String values are bind vars, NEVER interpolated.
- **Stdlib only:** `re`, `datetime`, `dataclasses`, `typing`.

### References

- [Source: epics.md, lines 1369-1395] — Story 4.4 AC
- [Source: architecture.md, line 1263] — Gap G7
- [SQLite REGEXP hook] — `connection.create_function("REGEXP", 2, lambda r, s: bool(re.search(r, s)))`

## Dev Agent Record

### Completion Notes List

- New module `ulog/_filter_dsl.py` (~ 300 LOC) — tokenizer
  (regex-based, 14 token kinds) + recursive-descent parser +
  frozen-dataclass AST (`Cmp`, `And`, `Or`) + 2 compilers
  (`to_sql() -> (clause, params)` named binds; `to_predicate() ->
  Callable`).
- Decision C5 honoured: NEVER calls `eval()` or `exec()`. SQL
  output uses named bind params (`:p0`, `:p1`, …) only.
- Gap G7 (AND > OR) implemented via grammar — `or_expr` calls
  `and_expr` repeatedly; parentheses override via `term`.
- Operators: `=`, `!=`, `>`, `>=`, `<`, `<=`, `~` (regex via
  `re.search`).
- Values: integer / float / quoted string (both quote styles) /
  bare identifier / relative date (`-30min` → `datetime.now() -
  timedelta(...)` captured at compile time).
- Dotted-key resolution for predicate: `context.tenant_id` →
  `record["context"]["tenant_id"]`.
- `ulog.replay()` gained `where_dsl=` kwarg. Auto-parses + compiles
  to `where_fn` (predicate path, safest). Mutex check extended:
  at most one of `where` / `where_fn` / `where_dsl`.
- 25 / 25 tests in `tests/test_filter_dsl.py` green: each operator,
  precedence (AND > OR), parentheses, case-insensitive AND/OR,
  whitespace tolerance, dotted-key nested resolution, SQL named-
  binds (3 tests including the injection-as-bind-param test),
  regex predicate, relative date → datetime, 5 error-path tests
  (empty / whitespace / unbalanced-paren / missing-value /
  trailing-garbage), injection-with-semicolon raises ParseError,
  3 replay-integration tests.
- 2 pre-existing tests in `test_test_event.py` updated: stub
  regression checks (`replay_records` raising NotImplementedError,
  `__all__` length 3) replaced with real-impl checks (CM works +
  `__all__` length 5 with `CapturedRecord` + `ReplaySession`).
- 580 / 580 tests green on full suite (excl. slow + qa_perf).
- mypy --strict / ruff check / ruff format / deptry all clean.

### File List

- `ulog/_filter_dsl.py` (NEW) — tokenizer + parser + AST + 2
  compilers + `FilterParseError`.
- `ulog/replay.py` — `replay()` gained `where_dsl=` kwarg with
  mutex-check extension.
- `tests/test_filter_dsl.py` (NEW) — 25 tests.
- `tests/test_test_event.py` — 2 stub-regression tests updated
  for the post-Story-4.9 reality.
