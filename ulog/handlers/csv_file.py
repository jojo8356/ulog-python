"""CSV handler — RFC 4180 rows for spreadsheet-importable logs.

Columns: ts, level, logger, msg, file, line, context_json, exc_json
(FR29). The bound context dict and exception info are JSON-stringified
into single columns to keep CSV's flat-row contract.
"""

from __future__ import annotations

import csv
import json
import logging
import time
import traceback
from pathlib import Path
from typing import Any

from ..context import get_bound

_COLUMNS = (
    "ts",
    "level",
    "logger",
    "msg",
    "file",
    "line",
    "context_json",
    "exc_json",
)


class CSVHandler(logging.Handler):
    """Appends rows to a CSV file. First write installs the header.

    Example:

        ulog.setup(handlers=['csv'], csv_path='./logs.csv')

    Then post-render:

        $ python -c "import csv; print(*csv.DictReader(open('logs.csv')))"

    Or import into pandas/Excel — every row is a flat record.
    """

    def __init__(self, path: str | Path, *, dialect: str = "excel") -> None:
        super().__init__()
        self._path = Path(path)
        self._dialect = dialect
        # Open in append mode; we'll write the header lazily on first
        # emit if the file is empty/new. delayed-open is intentional:
        # users that pass a non-existent dir get a clean error on
        # first emit, not at handler construction.
        self._fh: Any = None
        self._writer: Any = None
        self._header_written: bool | None = None  # tri-state: unknown/yes/no

    def _ensure_open(self) -> None:
        if self._fh is not None:
            return
        # `newline=""` per stdlib csv docs — prevents extra \r on Windows
        is_new = not self._path.exists() or self._path.stat().st_size == 0
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Long-lived handle owned by the logging handler; closed in
        # self.close(). Reopening per emit would tank perf.
        self._fh = open(self._path, "a", newline="", encoding="utf-8")  # noqa: SIM115
        self._writer = csv.writer(self._fh, dialect=self._dialect)
        if is_new:
            self._writer.writerow(_COLUMNS)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_open()
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created))
            bound = get_bound()
            # Merge `extra=...` fields too (anything on the record we
            # don't reserve), matching the JSON formatter's behavior.
            context = dict(bound)
            for k, v in record.__dict__.items():
                if k not in _RESERVED and k not in context and not k.startswith("_"):
                    context[k] = v
            context_json = json.dumps(context, ensure_ascii=False) if context else ""
            exc_json = ""
            if record.exc_info:
                etype, evalue, etb = record.exc_info
                exc_json = json.dumps(
                    {
                        "type": etype.__name__ if etype else None,
                        "msg": str(evalue) if evalue else None,
                        "tb": [
                            line.rstrip("\n") for line in (traceback.format_tb(etb) if etb else [])
                        ],
                    },
                    ensure_ascii=False,
                )
            self._writer.writerow(
                (
                    ts,
                    record.levelname,
                    record.name,
                    record.getMessage(),
                    record.filename,
                    record.lineno,
                    context_json,
                    exc_json,
                )
            )
            self._fh.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None
                self._writer = None
        super().close()


# Reserved keys on LogRecord that are NOT real `extra=` payload (kept
# in sync with formatters.JsonFormatter._RESERVED).
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)
