"""JSON Line handler — one JSON object per record, appended to a file.

Schema matches the v0.1 `JsonFormatter` byte-for-byte (FR26): the
emitted lines are jq-compatible and re-readable by the Django UI's
JSON adapter.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..formatters import JsonFormatter


class JSONLineHandler(logging.FileHandler):
    """Appends one JSON object per record to a file (RFC 7464-ish).

    Example:

        ulog.setup(handlers=['json'], json_path='./logs.jsonl')

    Or directly:

        h = JSONLineHandler('./logs.jsonl')
        log = ulog.get_logger()
        log.addHandler(h)
    """

    def __init__(self, path: str | Path, *, append: bool = True) -> None:
        mode = "a" if append else "w"
        # encoding='utf-8' handles non-ASCII messages (e.g. accented
        # letters in the qlnes French strings).
        super().__init__(str(path), mode=mode, encoding="utf-8", delay=False)
        # Always use the JSON formatter — overrides whatever stream
        # formatter the host setup() chose.
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        # logging.FileHandler.emit calls format() then writes the line
        # plus the terminator. We inherit that — just keeping a hook
        # here for future schema validation or compression.
        super().emit(record)
