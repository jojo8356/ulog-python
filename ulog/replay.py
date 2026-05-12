"""Replay records from a chain DB through a callback (Story 4.1).

`replay(db_path, where=..., on=callback)` walks records in chain
order (default) and yields each as a `types.MappingProxyType`
frozen view to the callback. Mutating the view raises `TypeError`,
which protects against accidental modification during forensic
analysis (Decision C3).

The Protocol shape feeds Story 4.3 (replay_to_pytest generator)
and Story 4.9 (replay_records test context manager). The DSL
parser (Story 4.4) will produce the `where` arg from
human-readable strings like `resolves="abc"`.

Out of v4.1 scope:
- `_REPLAY_ACTIVE` contextvar (Story 4.2).
- Deep-freeze of nested dicts — the contract is shallow read-only.
- Replay write protection (Story 4.10 edge case).
"""

from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import json as _json
import pprint as _pprint
import re as _re
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from pathlib import Path
from types import MappingProxyType
from typing import Any

_VALID_ORDERS = frozenset({"chain", "ts"})

# Story 4.2 / Gap G2 — set to True while inside `replay()`. The SQL
# handler reads it via `is_replaying()` and stamps `is_replay=1` on
# any record emitted from within a replay callback. ContextVar is
# the right primitive (not thread-local or global) so asyncio tasks
# inheriting the context see the flag correctly. Threads spawned
# from inside the callback DO NOT inherit (documented limitation).
_REPLAY_ACTIVE: ContextVar[bool] = ContextVar("_ulog_replay_active", default=False)


def is_replaying() -> bool:
    """Return True iff the current context is inside a `replay()` body."""
    return _REPLAY_ACTIVE.get(False)


def replay(
    db_path: str | Path,
    *,
    where: str | None = None,
    where_fn: Callable[[Mapping[str, Any]], bool] | None = None,
    where_dsl: str | None = None,
    on: Callable[[Mapping[str, Any]], None],
    order: str = "chain",
) -> int:
    """Iterate records from a ULog SQL DB and pass each to `on(...)`
    wrapped in `MappingProxyType`.

    Args:
        db_path: SQLite path (Path / str) OR `sqlite:///...` URL.
        where: raw SQL WHERE fragment. Mutually exclusive with the
            other filter args.
        where_fn: Python predicate over the record dict (filter applied
            after SQL fetch).
        where_dsl: filter DSL string (Story 4.4) — parsed + compiled
            to a Python predicate. Mutex with `where` / `where_fn`.
        on: callback receiving the frozen-view record.
        order: 'chain' (default; ORDER BY chain_pos ASC) or 'ts'.

    Returns:
        Number of records passed to the callback.

    Raises:
        ValueError: more than one of `where` / `where_fn` / `where_dsl`
            provided, or unknown `order`.
        FileNotFoundError: db_path doesn't point at an existing file.
        FilterParseError: bad `where_dsl` syntax.
    """
    provided = sum(x is not None for x in (where, where_fn, where_dsl))
    if provided > 1:
        raise ValueError("replay() accepts at most one of `where` / `where_fn` / `where_dsl`")
    if where_dsl is not None:
        from ._filter_dsl import parse as _parse_filter

        where_fn = _parse_filter(where_dsl).to_predicate()
    if order not in _VALID_ORDERS:
        raise ValueError(f"unknown order {order!r}; valid: {', '.join(sorted(_VALID_ORDERS))}")

    url = _resolve_db_url(db_path)

    from sqlalchemy import create_engine, text

    from ._chain import parse_stored_ts

    engine = create_engine(url, future=True)
    order_clause = "chain_pos" if order == "chain" else "ts"
    where_clause = f" WHERE {where}" if where else ""
    sql = (
        "SELECT id, chain_pos, ts, level, logger, msg, file, line, "
        "exc, context, immutable, record_hash, prev_hash "
        f"FROM logs{where_clause} ORDER BY {order_clause} ASC"
    )

    # Story 4.2 / Gap G2 — flag the context so records emitted from
    # the callback get is_replay=1 stamped by the SQL handler. Token
    # reset in `finally` so nested replays + early returns / raises
    # restore the prior state correctly.
    token = _REPLAY_ACTIVE.set(True)
    try:
        count = 0
        with engine.begin() as conn:
            for row in conn.execute(text(sql)):
                record: dict[str, Any] = {
                    "id": row[0],
                    "chain_pos": row[1],
                    "ts": parse_stored_ts(row[2]),
                    "level": row[3],
                    "logger": row[4],
                    "msg": row[5],
                    "file": row[6],
                    "line": row[7],
                    "exc": _json.loads(row[8]) if isinstance(row[8], str) else row[8],
                    "context": _json.loads(row[9]) if isinstance(row[9], str) else row[9],
                    "immutable": row[10],
                    "record_hash": bytes(row[11]) if row[11] is not None else None,
                    "prev_hash": bytes(row[12]) if row[12] is not None else None,
                }
                if where_fn is not None and not where_fn(record):
                    continue
                on(MappingProxyType(record))
                count += 1
    finally:
        _REPLAY_ACTIVE.reset(token)
        engine.dispose()
    return count


def _resolve_db_url(db_path: str | Path) -> str:
    if isinstance(db_path, str) and db_path.startswith("sqlite:///"):
        return db_path
    path = Path(db_path) if not isinstance(db_path, Path) else db_path
    if not path.exists():
        raise FileNotFoundError(f"replay(): DB not found at {path}")
    return f"sqlite:///{path}"


# ---- Story 4.3 — replay_to_pytest generator -----------------------------


def replay_to_pytest(
    db_path: str | Path,
    *,
    where: str | None = None,
    where_fn: Callable[[Mapping[str, Any]], bool] | None = None,
    output_path: str | Path,
    incident_hash: str = "",
    topic: str = "incident",
    force: bool = False,
) -> int:
    """Generate a pytest regression test from records matching the filter.

    Writes a self-contained Python file at `output_path` that, when run
    via pytest, imports `replay_records` from `ulog.testing` and replays
    the captured records. The user fills in the regression assertion in
    the stubbed test function body.

    Args:
        db_path: source DB (SQLite path / str / `sqlite:///...` URL).
        where / where_fn: filter (same semantics as `replay()`; pass at
            most one).
        output_path: target `.py` file.
        incident_hash: hex string (any case, with separators OK). Slugified
            to lowercase hex, max 12 chars. Empty → auto-derived from
            sha256 of `(db_path, where, where_fn name)`.
        topic: short slug appended to the test function name. Default
            `"incident"`.
        force: overwrite an existing file. Default `False` (raises
            `FileExistsError`).

    Returns:
        Number of records snapshotted into the file.

    Raises:
        FileExistsError: target file exists and `force=False`.
        ValueError / FileNotFoundError: propagated from `replay()`.
    """
    out = Path(output_path)
    if out.exists() and not force:
        raise FileExistsError(f"replay_to_pytest(): refused to overwrite {out}; pass force=True")

    snapshot: list[Mapping[str, Any]] = []
    replay(db_path, where=where, where_fn=where_fn, on=snapshot.append)

    slim_records = [_slim_record(r) for r in snapshot]
    h_slug = _slugify_hash(incident_hash) or _auto_hash(db_path, where, where_fn)
    t_slug = _re.sub(r"[^a-z0-9_]", "_", topic.lower()) or "incident"
    test_fn_name = f"test_incident_{h_slug}_{t_slug}"

    body = f'''"""Auto-generated regression test (ulog.replay_to_pytest).

incident_hash: {h_slug}
topic:         {t_slug}
generated:     {_dt.date.today().isoformat()}
source_db:     {db_path}
filter:        {where!r}
"""

import pytest  # noqa: F401  (imported for users who add fixtures / marks)
from ulog.testing import replay_records

INCIDENT_RECORDS = {_pprint.pformat(slim_records, sort_dicts=True, width=88)}


def {test_fn_name}():
    """TODO: replace `pass` with your regression assertion. Example:

        assert not session.matches(lambda r: r.extras.get("db_timeout"))
    """
    with replay_records(INCIDENT_RECORDS) as session:
        # TODO: add your regression assertion (e.g. session.matches(...)).
        assert session is not None  # placeholder so pytest reports a real check
'''
    out.write_text(body, encoding="utf-8")
    return len(slim_records)


def _slim_record(r: Mapping[str, Any]) -> dict[str, Any]:
    """Strip chain-internal columns + serialise datetime → ISO string.

    Replay only needs `ts/level/logger/msg/file/line/context`; bytes
    columns (`record_hash`, `prev_hash`), `chain_pos`, `id`,
    `immutable`, `is_replay` are NOT serialised into the generated
    file (no need + would require importing `datetime` etc.).
    """
    ts = r["ts"]
    return {
        "ts": ts.isoformat() if isinstance(ts, _dt.datetime) else ts,
        "level": r["level"],
        "logger": r["logger"],
        "msg": r["msg"],
        "file": r["file"],
        "line": r["line"],
        "context": dict(r["context"]) if r.get("context") else None,
    }


def _slugify_hash(h: str) -> str:
    """Keep hex only, lowercase, truncate to 12 chars."""
    return "".join(c for c in h.lower() if c in "0123456789abcdef")[:12]


def _auto_hash(
    db_path: str | Path,
    where: str | None,
    where_fn: Callable[[Mapping[str, Any]], bool] | None,
) -> str:
    seed = repr((str(db_path), where, getattr(where_fn, "__name__", None)))
    return _hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
