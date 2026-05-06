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
    # Story 1.6 (FR63 / FR64) — quick-filter checkboxes from the Tests sidebar.
    failed_only: bool = False
    slowest_only: bool = False
    # Story 1.7 (FR65) — when non-empty, restrict records to those whose
    # context.test_id equals this value. Covers BOTH plugin records
    # (`logger='ulog.test'`) AND propagated app records (any logger that
    # inherited `test_id` via Story 1.4's bound-context mechanism).
    test_id: str = ""

    def is_empty(self) -> bool:
        return (
            not self.levels and not self.loggers and not self.files
            and not self.search and not self.bound
            and not self.ts_from and not self.ts_to
            and not self.failed_only and not self.slowest_only
            and not self.test_id
        )


@dataclass(frozen=True)
class TestSummaryRow:
    """One row in the TESTS sidebar (Story 1.6, FR62).

    Aggregated by ``SQLiteAdapter._build_test_summary`` from records where
    ``logger='ulog.test'`` AND ``context.outcome IS NOT NULL`` (the body
    verdict records, NOT ``test started`` or traceback ERRORs)."""
    test_id: str         # e.g. "tests/test_audio.py::test_render[44100]"
    file: str            # the part before `::` — e.g. "tests/test_audio.py"
    name: str            # the part after the first `::` — e.g. "test_render[44100]"
    outcome: str         # "passed" / "failed" / "skipped" / "errored"
    duration_s: float    # raw seconds; template formats to ms/s


# FR64 — "Slowest top N" cap. Module-level constant so the WHERE / ORDER BY
# logic in `query()` and the test assertions in test_web.py share one source.
SLOWEST_TOP_N = 10


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
    test_summary: list[TestSummaryRow] = field(default_factory=list)  # Story 1.6 — empty when no test records


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

    def unique_file_line_pairs(self) -> Iterable[tuple[str, int]]:
        """Yield distinct (file, line) pairs across all records.

        Story 2.3 (FR71) — used by the author indexer at startup. Each
        adapter gets to use the most efficient extraction path
        (SQL DISTINCT, in-memory dedup, etc.).
        """
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

        # Story 1.6 — quick filters from the Tests sidebar. ORDER BY override
        # for `slowest_only` lives in `query()` (search "FR64 ORDER BY override"
        # there) — this method only adds WHERE clauses.
        # The structurally identical `clauses.append(...)` patterns above
        # already trigger SQLAlchemy stub `ColumnElement[bool]` vs
        # `BinaryExpression[bool]` mypy noise — pre-existing project pattern,
        # see Story 1.1's debug log. Wrapping each filter's WHERE in `and_(...)`
        # keeps the noise to one line per quick-filter rather than 2-3.
        if filters.failed_only:
            # FR63: limit to plugin outcome records flagged failed/errored.
            clauses.append(and_(  # type: ignore[arg-type]
                t.c.logger == "ulog.test",
                func.json_extract(t.c.context, "$.outcome").in_(
                    ("failed", "errored")
                ),
            ))
        if filters.slowest_only:
            # FR64: only plugin outcome records with a measurable duration —
            # skipped tests have `duration_s=0` by pytest convention.
            clauses.append(and_(  # type: ignore[arg-type]
                t.c.logger == "ulog.test",
                func.json_extract(t.c.context, "$.duration_s").is_not(None),
                func.json_extract(t.c.context, "$.outcome").in_(
                    ("passed", "failed", "errored")
                ),
            ))
        if filters.test_id:
            # FR65 (Story 1.7): restrict to records carrying this test_id in
            # context. Single equality matches both plugin records
            # (`logger='ulog.test'`) AND app records that inherited test_id
            # via Story 1.4's bound-context propagation — same column path.
            clauses.append(
                func.json_extract(t.c.context, "$.test_id") == filters.test_id  # type: ignore[arg-type]
            )

        return and_(*clauses) if clauses else None

    def query(self, filters: Filters, page: int = 1, page_size: int = 100) -> QueryResult:
        """Run the filtered query.

        Per PRD-v0.2.1 ("ghost counts"): each axis's per-value counts
        are computed with a `where` clause that EXCLUDES that axis's
        own filter. So when the user has DEBUG ticked, the INFO/WARNING
        rows still show what they'd get if they ALSO ticked those —
        not 0 just because they're not currently in the filter.

        The main record list keeps the full filter set (correct).
        """
        from dataclasses import replace as _replace
        from sqlalchemy import select, func

        t = self._table
        full_where = self._base_filters(filters)
        # Build per-axis "all filters except this one" where-clauses.
        # Story 1.7 review patch P1: each per-axis ghost-count must strip
        # ``test_id`` too — otherwise an active test_id filter scopes the
        # level/logger/file ghost counts to that test only, breaking the
        # PRD-v0.2.1 UX contract ("what would I get with this still active").
        # The base axes (levels/loggers/files) are stripped per their own
        # purpose; test_id leaks across all three without this extra strip.
        where_no_levels = self._base_filters(_replace(filters, levels=[], test_id=""))
        where_no_loggers = self._base_filters(_replace(filters, loggers=[], test_id=""))
        where_no_files = self._base_filters(_replace(filters, files=[], test_id=""))

        with self._engine.begin() as conn:
            # Total count uses the FULL filter (matches the records list).
            stmt = select(func.count()).select_from(t)
            if full_where is not None:
                stmt = stmt.where(full_where)
            total = conn.execute(stmt).scalar() or 0

            # Page rows use the FULL filter.
            # Story 1.6 — FR64 ORDER BY override: when `slowest_only` is on,
            # the records list becomes a bounded top-N by duration_s DESC.
            # Pagination is conceptually disabled (page=1, no offset) and
            # `total` is clamped at SLOWEST_TOP_N.
            if filters.slowest_only:
                stmt = (
                    select(t)
                    .order_by(
                        func.json_extract(t.c.context, "$.duration_s").desc()
                    )
                    .limit(SLOWEST_TOP_N)
                )
                if full_where is not None:
                    stmt = stmt.where(full_where)
                # Force single-page UI: no offset, total clamps at the cap.
                page = 1
                total = min(total, SLOWEST_TOP_N)
            else:
                stmt = (
                    select(t)
                    .order_by(t.c.id.desc())
                    .limit(page_size)
                    .offset((page - 1) * page_size)
                )
                if full_where is not None:
                    stmt = stmt.where(full_where)
            rows = list(conn.execute(stmt))

            # Per-axis counts use the "all filters except this axis" where-clause.
            # This is the ghost-count UX pattern (Datadog/Sentry/Grafana):
            # the user always sees what they'd get by ticking another value
            # on this axis, regardless of what's currently ticked on it.
            level_counts = self._count_by(conn, t.c.level, where_no_levels)
            file_counts = self._count_by(conn, t.c.file, where_no_files)
            logger_counts = self._count_by(conn, t.c.logger, where_no_loggers)
            # `bound_keys` is just an auto-detected list, not a count axis;
            # it can use the full filter (we want it to reflect what's
            # actually in scope).
            bound_keys = self._distinct_bound_keys(conn, full_where)

            # Story 1.6 — FR62: build the per-test summary unconditionally
            # (it's empty when no `ulog.test` records exist, which makes the
            # template hide the section entirely).
            test_summary = self._build_test_summary(conn)

        records = [self._row_to_record(r) for r in rows]
        sector_counts = _build_sector_counts(logger_counts)
        return QueryResult(
            records=records, total=total, page=page, page_size=page_size,
            sector_counts=sector_counts, file_counts=file_counts,
            level_counts=level_counts, bound_keys=bound_keys,
            test_summary=test_summary,
        )

    def _build_test_summary(self, conn: Any) -> list[TestSummaryRow]:
        """Aggregate one row per distinct test_id from plugin outcome records.

        We pick records where ``logger='ulog.test'`` AND ``context.outcome IS
        NOT NULL`` — that selects the body-verdict records (Story 1.2's
        ``_emit_outcome_records`` output) and excludes ``test started`` and
        traceback ERROR records (which lack the `outcome` key).

        For tests that ran multiple times under a rerun plugin, we keep the
        LAST seen outcome (highest id) — that's what the user cares about
        ("did it eventually pass?"). Sort by id ASC and let Python's dict
        overwrite-on-duplicate-key give us that behavior cheaply.

        Returned rows are sorted by `(file, name)` so the template's
        `{% regroup ... by file %}` sees contiguous file blocks (AC7).
        """
        # Use the SQLAlchemy `select()` builder rather than raw `text()` —
        # keeps the query injection-safe by construction and consistent with
        # the rest of this file's pattern (review patch P1).
        from sqlalchemy import select, func
        t = self._table
        json_test_id = func.json_extract(t.c.context, "$.test_id")
        json_outcome = func.json_extract(t.c.context, "$.outcome")
        json_duration_s = func.json_extract(t.c.context, "$.duration_s")
        stmt = (
            select(
                json_test_id.label("test_id"),
                json_outcome.label("outcome"),
                json_duration_s.label("duration_s"),
            )
            .where(t.c.logger == "ulog.test")
            .where(json_outcome.is_not(None))
            .order_by(t.c.id.asc())
        )

        latest_by_test_id: dict[str, tuple[str, float]] = {}
        for row in conn.execute(stmt):
            tid = row.test_id
            if not tid:
                continue
            # Outcome is one of the four documented strings (passed/failed/
            # skipped/errored). Empty-string is a defensive defect — promote
            # to "unknown" so the template's else-branch picks it up rather
            # than silently mislabeling as "passed" (review patch P3).
            outcome = row.outcome if row.outcome else "unknown"
            try:
                duration_s = float(row.duration_s) if row.duration_s is not None else 0.0
            except (TypeError, ValueError):
                duration_s = 0.0
            latest_by_test_id[tid] = (outcome, duration_s)

        rows: list[TestSummaryRow] = []
        for tid, (outcome, duration_s) in latest_by_test_id.items():
            file_part, sep, name_part = tid.partition("::")
            if not sep or not name_part:  # malformed nodeid — skip defensively
                continue
            rows.append(TestSummaryRow(
                test_id=tid, file=file_part, name=name_part,
                outcome=outcome, duration_s=duration_s,
            ))
        # AC7: sort by file then by name (alphabetical within file). regroup
        # in the template requires file-grouped contiguity which file-first
        # sort guarantees.
        rows.sort(key=lambda r: (r.file, r.name))
        return rows

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

    def count_records_for_test_id(self, test_id: str) -> int:
        """Count records where context.test_id == test_id (Story 1.8 / FR66).

        Includes both plugin records (logger='ulog.test') and Story 1.4-
        propagated app records — same single-equality clause used by Story 1.7.
        """
        from sqlalchemy import select, func
        if not test_id:
            return 0
        t = self._table
        # Read-only path — `connect()` rather than `begin()` (review patch P1).
        with self._engine.connect() as conn:
            stmt = (
                select(func.count())
                .select_from(t)
                .where(
                    func.json_extract(t.c.context, "$.test_id") == test_id
                )
            )
            return int(conn.execute(stmt).scalar() or 0)

    def get_test_summary_row(self, test_id: str) -> "TestSummaryRow | None":
        """Find the TestSummaryRow for a given test_id (Story 1.8 / FR66).

        Returns None when no outcome record exists for this test_id (e.g. a
        crashed session that emitted app records but never wrote the outcome).
        Story 1.8's detail-view panel handles None gracefully ("outcome unknown").

        TODO(v0.4 NFR-PERF): direct SELECT WHERE json_extract(...) = ? would
        be O(1) at the SQL level; current O(N) over `_build_test_summary` is
        fine for typical sessions (100-2000 tests).
        """
        if not test_id:
            return None
        # Use `connect()` (not `begin()`) — this is a read-only path; opening
        # a write-eligible transaction would unnecessarily serialize concurrent
        # readers on SQLite (review patch P1).
        with self._engine.connect() as conn:
            for row in self._build_test_summary(conn):
                if row.test_id == test_id:
                    return row
        return None

    def unique_file_line_pairs(self) -> Iterable[tuple[str, int]]:
        """Distinct (file, line) pairs via a single `SELECT DISTINCT` (Story 2.3)."""
        from sqlalchemy import select
        t = self._table
        with self._engine.connect() as conn:
            stmt = select(t.c.file, t.c.line).distinct()
            for row in conn.execute(stmt):
                f, l = row
                if f and isinstance(l, int) and l > 0:
                    yield (str(f), int(l))


# ---- JSONL ---------------------------------------------------------------


class JSONLAdapter(Adapter):
    """JSON-Line file adapter — loads the whole file into memory, filters in-process."""

    def __init__(self, path: Path) -> None:
        self._source_path = path  # Story 2.4: cache_path_for needs this
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

    def count_records_for_test_id(self, test_id: str) -> int:
        """Count records bound to test_id (Story 1.8). Counts both plugin and
        Story 1.4-propagated app records via the shared context.test_id key."""
        if not test_id:
            return 0
        return sum(
            1 for r in self._records if r.context.get("test_id") == test_id
        )

    def unique_file_line_pairs(self) -> Iterable[tuple[str, int]]:
        """In-memory dedup of (file, line) pairs (Story 2.3)."""
        seen: set[tuple[str, int]] = set()
        for r in self._records:
            if r.file and r.line > 0:
                pair = (r.file, r.line)
                if pair not in seen:
                    seen.add(pair)
                    yield pair

    def get_test_summary_row(self, test_id: str) -> "TestSummaryRow | None":
        """JSONL adapter stub — v0.3 doesn't implement test-summary aggregation
        for non-SQLite formats (Story 1.6 deferred). Returns None so the
        detail-view panel falls back to "outcome unknown" gracefully."""
        return None


# ---- CSV -----------------------------------------------------------------


class CSVAdapter(Adapter):
    def __init__(self, path: Path) -> None:
        self._source_path = path  # Story 2.4: cache_path_for needs this
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

    def count_records_for_test_id(self, test_id: str) -> int:
        """Count records bound to test_id (Story 1.8) — same shape as JSONL."""
        if not test_id:
            return 0
        return sum(
            1 for r in self._records if r.context.get("test_id") == test_id
        )

    def unique_file_line_pairs(self) -> Iterable[tuple[str, int]]:
        """In-memory dedup (Story 2.3) — same shape as JSONL."""
        seen: set[tuple[str, int]] = set()
        for r in self._records:
            if r.file and r.line > 0:
                pair = (r.file, r.line)
                if pair not in seen:
                    seen.add(pair)
                    yield pair

    def get_test_summary_row(self, test_id: str) -> "TestSummaryRow | None":
        """CSV adapter stub — v0.3 doesn't implement test-summary aggregation
        for non-SQLite formats. Returns None; panel falls back gracefully."""
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
    """In-memory filtering for JSONL/CSV adapters.

    Per PRD-v0.2.1 ghost-count rules: each per-axis count is computed
    against the dataset filtered by "all axes except this one". The
    main record list uses the full filter.
    """
    from dataclasses import replace as _replace

    def keep(r: Record, ff: Filters) -> bool:
        if ff.levels and r.level not in ff.levels:
            return False
        if ff.loggers and not any(
            r.logger == p or r.logger.startswith(p + ".") or r.logger.startswith(p)
            for p in ff.loggers
        ):
            return False
        if ff.files and r.file not in ff.files:
            return False
        if ff.search and ff.search.lower() not in r.msg.lower():
            return False
        if ff.ts_from and r.ts < ff.ts_from:
            return False
        if ff.ts_to and r.ts > ff.ts_to:
            return False
        for k, v in ff.bound.items():
            if str(r.context.get(k, "")) != v:
                return False
        # Story 1.7 (FR65) — single-equality test_id filter applies to both
        # plugin records and propagated app records (same context.test_id key).
        if ff.test_id and r.context.get("test_id") != ff.test_id:
            return False
        return True

    # Full filter — for records list + total + bound_keys
    full_filtered = [r for r in records if keep(r, f)]
    total = len(full_filtered)
    start = (page - 1) * page_size
    page_records = list(reversed(full_filtered))[start:start + page_size]

    # Per-axis ghost-count datasets — strip test_id too (review patch P1).
    no_levels_filtered = [r for r in records if keep(r, _replace(f, levels=[], test_id=""))]
    no_loggers_filtered = [r for r in records if keep(r, _replace(f, loggers=[], test_id=""))]
    no_files_filtered = [r for r in records if keep(r, _replace(f, files=[], test_id=""))]

    level_counts = Counter(r.level for r in no_levels_filtered)
    file_counts = Counter(r.file for r in no_files_filtered)
    logger_counts = Counter(r.logger for r in no_loggers_filtered)
    sector_counts = _build_sector_counts(logger_counts)

    # bound_keys: auto-detected list (not a count axis); use full filter.
    bound_keys: set[str] = set()
    for r in full_filtered[:500]:
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
