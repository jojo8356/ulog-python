"""Importer driver — `ulog import` (PRD-v0.17 / Story 17.x)."""

from __future__ import annotations

import bz2
import csv as _csv
import gzip
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .parsers import (
    PARSER_REGISTRY,
    ParsedRecord,
    ParseError,
    Parser,
    make_regex_parser,
)


@dataclass
class ImportOptions:
    """Parsed CLI options for `ulog import`."""

    output_db: Path
    format: str = "auto"  # "jsonl" / "csv" / "nginx-combined" / ... / "raw" / "regex:<pat>"
    strict: bool = False
    encoding: str = "utf-8"
    source_tag: str = ""  # added to context.import_source
    batch_size: int = 500


@dataclass
class ImportResult:
    imported: int
    skipped: int
    files: list[Path]


def auto_detect_format(path: Path, sample_lines: int = 100) -> str:
    """Sniff the format from extension + content (PRD-v0.17 FR3)."""
    ext = path.suffix.lower()
    if ext in (".jsonl", ".ndjson"):
        return "jsonl"
    if ext == ".csv":
        return "csv"
    # Content sniff.
    with _open_text(path, "utf-8") as fh:
        head = [next(fh, "") for _ in range(sample_lines)]
    if any('"__REALTIME_TIMESTAMP"' in line or '"__CURSOR"' in line for line in head):
        return "journald-json"
    if any(line.startswith("{") and '"ts"' in line and '"level"' in line for line in head):
        return "jsonl"
    if any('"GET ' in line or '"POST ' in line for line in head if " - " in line):
        # nginx/apache common pattern: `IP - USER [TS]`
        return "nginx-combined"
    if any(_looks_syslog(line) for line in head if line.strip()):
        return "syslog"
    return "raw"


def _looks_syslog(line: str) -> bool:
    # Very crude — three letters month + day + HH:MM:SS pattern.
    import re

    return bool(re.match(r"^(?:<\d+>)?\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s", line))


def _open_text(path: Path, encoding: str) -> Any:
    """Open a file with transparent .gz / .bz2 decoding."""
    if path.suffix == ".gz":
        return gzip.open(path, mode="rt", encoding=encoding, errors="replace")
    if path.suffix == ".bz2":
        return bz2.open(path, mode="rt", encoding=encoding, errors="replace")
    return path.open(encoding=encoding, errors="replace")


def import_files(inputs: list[Path], opts: ImportOptions) -> ImportResult:
    """Stream-parse `inputs`, insert into `opts.output_db`."""
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{opts.output_db}", future=True)
    _ensure_schema(engine)

    total_ok = 0
    total_skip = 0
    files_done: list[Path] = []
    batch: list[tuple[Any, ...]] = []

    for inp in inputs:
        if not inp.exists():
            print(f"ulog import: file not found: {inp}", file=sys.stderr)
            continue
        fmt = opts.format
        if fmt == "auto":
            fmt = auto_detect_format(inp)
            print(f"detected format: {fmt} ({inp})", file=sys.stderr)
        parser = _resolve_parser(fmt)
        ok, skip = _ingest_one(inp, parser, opts, engine, batch, fmt)
        total_ok += ok
        total_skip += skip
        files_done.append(inp)

    if batch:
        _flush(engine, batch)

    engine.dispose()
    print(
        f"\nulog import: {total_ok:,} lines imported, "
        f"{total_skip:,} skipped (parse errors).",
        file=sys.stderr,
    )
    return ImportResult(imported=total_ok, skipped=total_skip, files=files_done)


def _resolve_parser(fmt: str) -> Parser:
    if fmt.startswith("regex:"):
        return make_regex_parser(fmt[len("regex:") :])
    if fmt not in PARSER_REGISTRY:
        raise SystemExit(
            f"ulog import: unknown format {fmt!r}; "
            f"recognised: {sorted(PARSER_REGISTRY)} or regex:<pattern>"
        )
    return PARSER_REGISTRY[fmt]


def _ingest_one(
    path: Path,
    parser: Parser,
    opts: ImportOptions,
    engine: Any,
    batch: list[tuple[Any, ...]],
    fmt: str,
) -> tuple[int, int]:
    if fmt == "csv":
        return _ingest_csv(path, opts, engine, batch)
    ok = 0
    skip = 0
    with _open_text(path, opts.encoding) as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n").rstrip("\r")
            if not line:
                continue
            try:
                rec = parser(line, path.name, line_no)
            except ParseError as e:
                skip += 1
                msg = f"  line {line_no}: {e}"
                if opts.strict:
                    print(msg, file=sys.stderr)
                    raise SystemExit(f"ulog import: --strict abort at {path}:{line_no}") from e
                continue
            _maybe_tag(rec, opts.source_tag)
            batch.append(_record_to_row(rec))
            ok += 1
            if len(batch) >= opts.batch_size:
                _flush(engine, batch)
    return ok, skip


def _ingest_csv(path: Path, opts: ImportOptions, engine: Any, batch: list[tuple[Any, ...]]) -> tuple[int, int]:
    ok = 0
    skip = 0
    with _open_text(path, opts.encoding) as fh:
        reader = _csv.DictReader(fh)
        for line_no, row in enumerate(reader, start=2):  # line 1 = header
            try:
                rec = ParsedRecord(
                    ts=row.get("ts", ""),
                    level=row.get("level", "INFO").upper(),
                    logger=row.get("logger", "imported.csv"),
                    msg=row.get("msg", row.get("message", "")),
                    file=row.get("file", path.name),
                    line=int(row.get("line", line_no)),
                    context={k: v for k, v in row.items() if k not in {"ts", "level", "logger", "msg", "file", "line"}},
                )
            except Exception as e:
                skip += 1
                if opts.strict:
                    raise SystemExit(f"ulog import: --strict abort at {path}:{line_no}: {e}") from e
                continue
            _maybe_tag(rec, opts.source_tag)
            batch.append(_record_to_row(rec))
            ok += 1
            if len(batch) >= opts.batch_size:
                _flush(engine, batch)
    return ok, skip


def _maybe_tag(rec: ParsedRecord, tag: str) -> None:
    if tag:
        rec.context["import_source"] = tag


def _record_to_row(rec: ParsedRecord) -> tuple[Any, ...]:
    return (rec.ts, rec.level, rec.logger, rec.msg, rec.file, rec.line, json.dumps(rec.context) if rec.context else None)


_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts DATETIME NOT NULL,
    level VARCHAR(10) NOT NULL,
    logger VARCHAR(255) NOT NULL,
    msg TEXT NOT NULL,
    file VARCHAR(255) NOT NULL,
    line INTEGER NOT NULL,
    exc JSON,
    context JSON,
    chain_pos INTEGER NOT NULL DEFAULT 0,
    record_hash BLOB,
    prev_hash BLOB,
    immutable INTEGER NOT NULL DEFAULT 0,
    is_replay INTEGER NOT NULL DEFAULT 0,
    is_imported INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_logs_ts ON logs(ts);
CREATE INDEX IF NOT EXISTS ix_logs_level ON logs(level);
CREATE INDEX IF NOT EXISTS ix_logs_logger ON logs(logger);
CREATE INDEX IF NOT EXISTS ix_logs_is_imported ON logs(is_imported);
"""


def _ensure_schema(engine: Any) -> None:
    """Create v0.5+is_imported schema; ALTER existing tables to add the column."""
    from sqlalchemy import text

    with engine.begin() as conn:
        for stmt in _SCHEMA_DDL.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        # If an existing table predates is_imported, ALTER it.
        cols = conn.execute(text("PRAGMA table_info(logs)")).fetchall()
        names = {c[1] for c in cols}
        if "is_imported" not in names:
            conn.execute(text("ALTER TABLE logs ADD COLUMN is_imported INTEGER NOT NULL DEFAULT 0"))


def _flush(engine: Any, batch: list[tuple[Any, ...]]) -> None:
    if not batch:
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO logs (ts, level, logger, msg, file, line, context, is_imported) "
                "VALUES (:ts, :level, :logger, :msg, :file, :line, :context, 1)"
            ),
            [
                {
                    "ts": r[0],
                    "level": r[1],
                    "logger": r[2],
                    "msg": r[3],
                    "file": r[4],
                    "line": r[5],
                    "context": r[6],
                }
                for r in batch
            ],
        )
    batch.clear()
