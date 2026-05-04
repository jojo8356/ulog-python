"""Storage adapters — read SQLite / JSONL / CSV into a uniform shape.

The Django views are storage-agnostic: they call
`get_adapter(path).query(filters, page)` and receive `(records,
total_count, sectors, files)`. Each adapter handles its own filtering
without loading the whole dataset where possible.

For SQLite, filtering happens at SQL level (FR47, FR50, NFR-PERF-11).
For JSONL/CSV, the adapter loads the full file once into memory; for
million-record files this gets slow — v0.3 may add streaming
filtering. v0.2 ships the simple "load and filter in memory" path.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Record:
    """Uniform shape consumed by Django views, regardless of storage."""

    id: int  # 1-based row index for jsonl/csv; PK for sqlite
    ts: str  # ISO-8601 UTC string
    level: str
    logger: str
    msg: str
    file: str
    line: int
    context: dict[str, Any] = field(default_factory=dict)
    exc: dict[str, Any] | None = None


@dataclass
class Filters:
    """Subset of FR35 filter parameters we resolve per-page query."""

    levels: list[str] = field(default_factory=list)  # empty == all
    loggers: list[str] = field(default_factory=list)  # logger-name prefixes (sectors)
    files: list[str] = field(default_factory=list)
    search: str = ""  # full-text in msg
    bound: dict[str, str] = field(default_factory=dict)  # context key=value
    ts_from: str = ""  # ISO-8601
    ts_to: str = ""

    def is_empty(self) -> bool:
        return (
            not self.levels and not self.loggers and not self.files
            and not self.search and not self.bound
            and not self.ts_from and not self.ts_to
        )


@dataclass
class QueryResult:
    """What `Adapter.query` returns to the views."""

    records: list[Record]
    total: int
    page: int
    page_size: int
    sector_counts: dict[str, int]  # logger-prefix → count, all data
    file_counts: dict[str, int]    # file → count, all data
    level_counts: dict[str, int]   # level → count, all data
    bound_keys: list[str]          # auto-detected bound-context keys


def detect_kind(path: Path) -> str:
    """Sniff the storage type from the file extension. FR33."""
    suf = path.suffix.lower()
    if suf in (".sqlite", ".sqlite3", ".db"):
        return "sqlite"
    if suf in (".jsonl", ".ndjson"):
        return "jsonl"
    if suf == ".csv":
        return "csv"
    raise ValueError(
        f"unknown log file extension {suf!r}; expected "
        ".sqlite/.sqlite3/.db, .jsonl/.ndjson, or .csv"
    )


def get_adapter(path: str | Path) -> "Adapter":
    """Build an adapter from a file path. Auto-detects storage kind."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"log file not found: {p}")
    kind = detect_kind(p)
    if kind == "sqlite":
        return SQLiteAdapter(p)
    if kind == "jsonl":
        return JSONLAdapter(p)
    return CSVAdapter(p)


class Adapter:
    """Common interface every storage adapter implements."""

    def query(self, filters: Filters, page: int = 1, page_size: int = 100) -> QueryResult:  # noqa: D401
        raise NotImplementedError

    def get(self, record_id: int) -> Record | None:
        raise NotImplementedError


# ---- SQLite (SQL via SQLAlchemy core) ------------------------------------


class SQLiteAdapter(Adapter):
    """SQLite-backed adapter — filter pushed down as SQL WHERE clauses."""

    def __init__(self, path: Path) -> None:
        from sqlalchemy import MetaData, Table, create_engine

        self._engine = create_engine(f"sqlite:///{path}", future=True)
        self._md = MetaData()
        # Reflect the existing schema so users with custom column adds work too.
        self._table = Table("logs", self._md, autoload_with=self._engine)

    def _base_filters(self, filters: Filters):
        from sqlalchemy import and_, or_

        t = self._table
        clauses = []
        if filters.levels:
            clauses.append(t.c.level.in_(filters.levels))
        if filters.loggers:
            # OR across logger-prefixes
            clauses.append(or_(*[t.c.logger.like(f"{p}%") for p in filters.loggers]))
        if filters.files:
            clauses.append(t.c.file.in_(filters.files))
        if filters.search:
            clauses.append(t.c.msg.like(f"%{filters.search}%"))
        if filters.ts_from:
            clauses.append(t.c.ts >= filters.ts_from)
        if filters.ts_to:
            clauses.append(t.c.ts <= filters.ts_to)
        # bound key=value: use SQLite's json_extract for an exact match
        # on the path. SQLAlchemy 2 exposes it via `func.json_extract`,
        # which is idiomatic across SQLite, MySQL 5.7+ and Postgres
        # (Postgres uses `->`, but the function call form works on the
        # SQLite + MySQL backends ULog targets in v0.2).
        from sqlalchemy import func

        for k, v in filters.bound.items():
            clauses.append(func.json_extract(t.c.context, f"$.{k}") == v)
        return and_(*clauses) if clauses else None

    def query(self, filters: Filters, page: int = 1, page_size: int = 100) -> QueryResult:
        from sqlalchemy import select, func

        t = self._table
        where = self._base_filters(filters)

        with self._engine.begin() as conn:
            # Total count
            stmt = select(func.count()).select_from(t)
            if where is not None:
                stmt = stmt.where(where)
            total = conn.execute(stmt).scalar() or 0

            # Page rows
            stmt = (
                select(t)
                .order_by(t.c.id.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
            if where is not None:
                stmt = stmt.where(where)
            rows = list(conn.execute(stmt))

            # Aggregates over the FULL filtered dataset (so the sidebar
            # counts reflect the active query, not just the page).
            level_counts = self._count_by(conn, t.c.level, where)
            file_counts = self._count_by(conn, t.c.file, where)
            logger_counts = self._count_by(conn, t.c.logger, where)
            bound_keys = self._distinct_bound_keys(conn, where)

        records = [self._row_to_record(r) for r in rows]
        sector_counts = _build_sector_counts(logger_counts)
        return QueryResult(
            records=records, total=total, page=page, page_size=page_size,
            sector_counts=sector_counts, file_counts=file_counts,
            level_counts=level_counts, bound_keys=bound_keys,
        )

    def _count_by(self, conn, col, where) -> dict[str, int]:
        from sqlalchemy import select, func
        stmt = select(col, func.count()).group_by(col).order_by(func.count().desc())
        if where is not None:
            stmt = stmt.where(where)
        return {row[0]: row[1] for row in conn.execute(stmt)}

    def _distinct_bound_keys(self, conn, where) -> list[str]:
        # Heuristic: pull a sample of context blobs, gather their top-level keys.
        # SQLite v0.2 keeps this in app-space rather than JSON path.
        from sqlalchemy import select
        t = self._table
        stmt = select(t.c.context).where(t.c.context.is_not(None)).limit(500)
        if where is not None:
            stmt = stmt.where(where)
        keys: set[str] = set()
        for (ctx,) in conn.execute(stmt):
            if not ctx:
                continue
            payload = json.loads(ctx) if isinstance(ctx, str) else ctx
            if isinstance(payload, dict):
                keys.update(payload.keys())
        return sorted(keys)

    def _row_to_record(self, row) -> Record:
        ts = row.ts.isoformat(timespec="seconds") + "Z" if row.ts else ""
        ctx = row.context
        if isinstance(ctx, str):
            ctx = json.loads(ctx) if ctx else {}
        exc = row.exc
        if isinstance(exc, str):
            exc = json.loads(exc) if exc else None
        return Record(
            id=row.id, ts=ts, level=row.level, logger=row.logger,
            msg=row.msg, file=row.file, line=row.line,
            context=ctx or {}, exc=exc,
        )

    def get(self, record_id: int) -> Record | None:
        from sqlalchemy import select

        with self._engine.begin() as conn:
            row = conn.execute(
                select(self._table).where(self._table.c.id == record_id)
            ).first()
        if row is None:
            return None
        return self._row_to_record(row)


# ---- JSONL ---------------------------------------------------------------


class JSONLAdapter(Adapter):
    """JSON-Line file adapter — loads the whole file into memory, filters in-process."""

    def __init__(self, path: Path) -> None:
        self._records: list[Record] = []
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip malformed lines silently
            self._records.append(_payload_to_record(payload, i))

    def query(self, filters: Filters, page: int = 1, page_size: int = 100) -> QueryResult:
        return _filter_and_paginate(self._records, filters, page, page_size)

    def get(self, record_id: int) -> Record | None:
        for r in self._records:
            if r.id == record_id:
                return r
        return None


# ---- CSV -----------------------------------------------------------------


class CSVAdapter(Adapter):
    def __init__(self, path: Path) -> None:
        self._records: list[Record] = []
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader, start=1):
                ctx_str = row.get("context_json") or ""
                exc_str = row.get("exc_json") or ""
                ctx = json.loads(ctx_str) if ctx_str else {}
                exc = json.loads(exc_str) if exc_str else None
                self._records.append(
                    Record(
                        id=i,
                        ts=row.get("ts", ""),
                        level=row.get("level", ""),
                        logger=row.get("logger", ""),
                        msg=row.get("msg", ""),
                        file=row.get("file", ""),
                        line=int(row.get("line", "0") or 0),
                        context=ctx if isinstance(ctx, dict) else {},
                        exc=exc if isinstance(exc, dict) else None,
                    )
                )

    def query(self, filters: Filters, page: int = 1, page_size: int = 100) -> QueryResult:
        return _filter_and_paginate(self._records, filters, page, page_size)

    def get(self, record_id: int) -> Record | None:
        for r in self._records:
            if r.id == record_id:
                return r
        return None


# ---- Shared helpers ------------------------------------------------------


def _payload_to_record(payload: dict[str, Any], idx: int) -> Record:
    """Convert a JSON Line payload (qlnes/ulog v0.1 schema) to a Record."""
    return Record(
        id=idx,
        ts=str(payload.get("ts", "")),
        level=str(payload.get("level", "INFO")),
        logger=str(payload.get("logger", "")),
        msg=str(payload.get("msg", "")),
        file=str(payload.get("file", "")),
        line=int(payload.get("line", 0) or 0),
        context={
            k: v for k, v in payload.items()
            if k not in {"ts", "level", "logger", "msg", "file", "line", "exc"}
        },
        exc=payload.get("exc"),
    )


def _filter_and_paginate(
    records: list[Record], f: Filters, page: int, page_size: int
) -> QueryResult:
    """In-memory filtering for JSONL/CSV adapters."""
    def keep(r: Record) -> bool:
        if f.levels and r.level not in f.levels:
            return False
        if f.loggers and not any(
            r.logger == p or r.logger.startswith(p + ".") or r.logger.startswith(p)
            for p in f.loggers
        ):
            return False
        if f.files and r.file not in f.files:
            return False
        if f.search and f.search.lower() not in r.msg.lower():
            return False
        if f.ts_from and r.ts < f.ts_from:
            return False
        if f.ts_to and r.ts > f.ts_to:
            return False
        for k, v in f.bound.items():
            if str(r.context.get(k, "")) != v:
                return False
        return True

    filtered = [r for r in records if keep(r)]
    total = len(filtered)
    start = (page - 1) * page_size
    page_records = list(reversed(filtered))[start:start + page_size]

    level_counts = Counter(r.level for r in filtered)
    file_counts = Counter(r.file for r in filtered)
    logger_counts = Counter(r.logger for r in filtered)
    sector_counts = _build_sector_counts(logger_counts)
    bound_keys: set[str] = set()
    for r in filtered[:500]:
        bound_keys.update(r.context.keys())

    return QueryResult(
        records=page_records, total=total, page=page, page_size=page_size,
        sector_counts=sector_counts, file_counts=dict(file_counts),
        level_counts=dict(level_counts), bound_keys=sorted(bound_keys),
    )


def _build_sector_counts(logger_counts: dict[str, int]) -> dict[str, int]:
    """Roll up logger-name `.`-split prefixes into a sector-count dict.

    `qlnes.audio.renderer:5` becomes
    `qlnes:5, qlnes.audio:5, qlnes.audio.renderer:5`. The UI uses
    these to render the sector tree (FR44).
    """
    sectors: Counter[str] = Counter()
    for logger, count in logger_counts.items():
        parts = logger.split(".")
        for i in range(1, len(parts) + 1):
            sectors[".".join(parts[:i])] += count
    return dict(sectors)
