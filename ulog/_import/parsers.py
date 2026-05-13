"""Parser registry for `ulog import` (PRD-v0.17 / Decision D1).

Each parser maps a source line to ulog's canonical record schema:
    (ts, level, logger, msg, file, line, context)

`file` and `line` are best-effort — for sources without source-line
metadata (nginx, syslog, etc.), they're filled with the source filename
+ the line number within the input.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Reserved context names (Story 6.3 / FR108) — parser-captured groups
# named these collide with chain fields and are rejected.
RESERVED_CONTEXT_NAMES: frozenset[str] = frozenset(
    {"record_hash", "chain_pos", "prev_hash", "immutable", "is_replay", "is_imported"}
)


class ParseError(Exception):
    """Raised when a line can't be parsed by the active parser."""


@dataclass
class ParsedRecord:
    """One record after parsing, before insert."""

    ts: str
    level: str
    logger: str
    msg: str
    file: str
    line: int
    context: dict[str, Any] = field(default_factory=dict)


Parser = Callable[[str, str, int], ParsedRecord]


# ---- Built-in parsers ----------------------------------------------------


def parse_jsonl(line: str, source_filename: str, line_no: int) -> ParsedRecord:
    """Parser for JSON-lines (ulog v0.1+ shape)."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON: {e}") from e
    if not isinstance(payload, dict):
        raise ParseError("JSON value is not an object")
    ts = str(payload.pop("ts", _now_iso()))
    level = str(payload.pop("level", "INFO")).upper()
    logger = str(payload.pop("logger", payload.pop("service", "imported")))
    msg = str(payload.pop("msg", payload.pop("message", "")))
    file_ = str(payload.pop("file", source_filename))
    line_n = int(payload.pop("line", line_no))
    return ParsedRecord(
        ts=ts, level=level, logger=logger, msg=msg, file=file_, line=line_n, context=payload
    )


def parse_csv(line: str, source_filename: str, line_no: int) -> ParsedRecord:
    """Parser for CSV — expects header line; line_no==1 is detected as header
    elsewhere via the streaming reader. Here we treat each call as one row."""
    raise ParseError("csv must be parsed at file level — use parse_csv_file()")


def parse_nginx_combined(line: str, source_filename: str, line_no: int) -> ParsedRecord:
    """Common nginx access log line:
       remote_addr - remote_user [time_local] "request" status body_bytes_sent
       "http_referer" "http_user_agent"
    """
    m = _NGINX_RE.match(line)
    if m is None:
        raise ParseError("doesn't match nginx-combined regex")
    g = m.groupdict()
    status = int(g["status"])
    return ParsedRecord(
        ts=_parse_clf_ts(g["time_local"]),
        level=_status_to_level(status),
        logger="nginx.access",
        msg=f"{g['method']} {g['path']} {status}",
        file=source_filename,
        line=line_no,
        context={
            "client_ip": g["client_ip"],
            "remote_user": g.get("remote_user") or "",
            "bytes_sent": int(g["bytes_sent"]) if g["bytes_sent"].isdigit() else 0,
            "referer": g.get("referer") or "",
            "user_agent": g.get("user_agent") or "",
        },
    )


def parse_apache_combined(line: str, source_filename: str, line_no: int) -> ParsedRecord:
    """Apache combined log format — same shape as nginx-combined for our purposes."""
    rec = parse_nginx_combined(line, source_filename, line_no)
    rec.logger = "apache.access"
    return rec


def parse_syslog(line: str, source_filename: str, line_no: int) -> ParsedRecord:
    """Syslog RFC3164 dual: <PRI>MMM DD HH:MM:SS host tag: msg"""
    m = _SYSLOG_RE.match(line)
    if m is None:
        raise ParseError("doesn't match syslog regex")
    g = m.groupdict()
    pri = int(g["pri"]) if g["pri"] else 6  # default info
    facility = pri // 8
    severity = pri % 8
    return ParsedRecord(
        ts=_parse_syslog_ts(g["timestamp"]),
        level=_severity_to_level(severity),
        logger=g.get("appname") or "syslog",
        msg=g["body"],
        file=source_filename,
        line=line_no,
        context={
            "facility": facility,
            "hostname": g.get("hostname") or "",
        },
    )


def parse_journald_json(line: str, source_filename: str, line_no: int) -> ParsedRecord:
    """`journalctl -o json` emits one JSON object per line, no newlines inside."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON: {e}") from e
    ts_us = obj.pop("__REALTIME_TIMESTAMP", None)
    if ts_us is not None:
        ts = datetime.fromtimestamp(int(ts_us) / 1_000_000, tz=timezone.utc).replace(tzinfo=None).isoformat()
    else:
        ts = _now_iso()
    priority = int(obj.pop("PRIORITY", "6"))
    return ParsedRecord(
        ts=ts,
        level=_severity_to_level(priority),
        logger=str(obj.pop("_SYSTEMD_UNIT", obj.pop("SYSLOG_IDENTIFIER", "journald"))),
        msg=str(obj.pop("MESSAGE", "")),
        file=source_filename,
        line=line_no,
        context={k: v for k, v in obj.items() if not k.startswith("__CURSOR")},
    )


def parse_raw(line: str, source_filename: str, line_no: int) -> ParsedRecord:
    """Plain text — one record per line, level=INFO, msg=full line."""
    return ParsedRecord(
        ts=_now_iso(),
        level="INFO",
        logger="imported.raw",
        msg=line.rstrip("\n"),
        file=source_filename,
        line=line_no,
        context={},
    )


# ---- Regex escape hatch -------------------------------------------------


def make_regex_parser(pattern: str) -> Parser:
    """Build a parser from a regex with named groups: ts/level/logger/msg/file/line."""
    try:
        re_obj = re.compile(pattern)
    except re.error as e:
        raise ParseError(f"invalid regex: {e}") from e
    if "msg" not in re_obj.groupindex:
        raise ParseError("regex must include named group 'msg'")
    reserved = set(re_obj.groupindex) & RESERVED_CONTEXT_NAMES
    if reserved:
        raise ParseError(f"reserved group name(s): {sorted(reserved)}")

    def _parser(line: str, source_filename: str, line_no: int) -> ParsedRecord:
        m = re_obj.match(line)
        if m is None:
            raise ParseError("regex did not match")
        g = m.groupdict()
        ctx = {k: v for k, v in g.items() if k not in {"ts", "level", "logger", "msg", "file", "line"} and v is not None}
        return ParsedRecord(
            ts=str(g.get("ts") or _now_iso()),
            level=str(g.get("level") or "INFO").upper(),
            logger=str(g.get("logger") or "imported.regex"),
            msg=str(g["msg"]),
            file=str(g.get("file") or source_filename),
            line=int(g["line"]) if (g.get("line") or "").isdigit() else line_no,
            context=ctx,
        )

    return _parser


# ---- Registry -----------------------------------------------------------


PARSER_REGISTRY: dict[str, Parser] = {
    "jsonl": parse_jsonl,
    "nginx-combined": parse_nginx_combined,
    "apache-combined": parse_apache_combined,
    "syslog": parse_syslog,
    "journald-json": parse_journald_json,
    "raw": parse_raw,
}


# ---- Helpers ------------------------------------------------------------

_NGINX_RE = re.compile(
    r'^(?P<client_ip>\S+)\s+\S+\s+(?P<remote_user>\S+)\s+'
    r'\[(?P<time_local>[^\]]+)\]\s+'
    r'"(?P<method>\S+)\s+(?P<path>\S+)\s+\S+"\s+'
    r'(?P<status>\d{3})\s+(?P<bytes_sent>\d+|-)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<user_agent>[^"]*)")?'
)

_SYSLOG_RE = re.compile(
    r'^(?:<(?P<pri>\d+)>)?'
    r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'
    r'(?P<hostname>\S+)\s+'
    r'(?P<appname>\S+?)(?:\[\d+\])?:\s+'
    r'(?P<body>.*)$'
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _parse_clf_ts(s: str) -> str:
    """Parse Common Log Format timestamp '14/May/2026:07:30:01 +0000'."""
    try:
        dt = datetime.strptime(s, "%d/%b/%Y:%H:%M:%S %z")
        return dt.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
    except ValueError:
        return _now_iso()


def _parse_syslog_ts(s: str) -> str:
    """Parse syslog RFC3164 timestamp 'May 14 07:30:01' (year inferred = current)."""
    try:
        year = datetime.now(timezone.utc).year
        dt = datetime.strptime(f"{year} {s}", "%Y %b %d %H:%M:%S")
        return dt.isoformat()
    except ValueError:
        return _now_iso()


def _status_to_level(status: int) -> str:
    if status >= 500:
        return "ERROR"
    if status >= 400:
        return "WARNING"
    return "INFO"


# Syslog severity codes per RFC5424.
_SEVERITY_NAMES = [
    "CRITICAL",  # 0 emergency
    "CRITICAL",  # 1 alert
    "CRITICAL",  # 2 critical
    "ERROR",     # 3 error
    "WARNING",   # 4 warning
    "INFO",      # 5 notice
    "INFO",      # 6 informational
    "DEBUG",     # 7 debug
]


def _severity_to_level(s: int) -> str:
    return _SEVERITY_NAMES[s] if 0 <= s < len(_SEVERITY_NAMES) else "INFO"
