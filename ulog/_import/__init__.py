"""Log import — `ulog import` (PRD-v0.17).

Ingests external log files (.log/.txt/.jsonl/.csv/syslog/journald/
nginx/apache/regex) into a ulog SQLite DB. Out-of-chain by design
(is_imported=1, chain_pos=0, record_hash=NULL) so chain integrity
is preserved.
"""

from __future__ import annotations

from .parsers import PARSER_REGISTRY, ParseError, Parser

__all__ = ["PARSER_REGISTRY", "ParseError", "Parser"]
