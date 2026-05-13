"""Tests for `ulog import` (PRD-v0.17)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from ulog._cli import main as cli_main


def _run(args: list[str]) -> int:
    return cli_main(["import", *args])


def _count(db: Path, where: str = "1=1") -> int:
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        n = conn.execute(text(f"SELECT count(*) FROM logs WHERE {where}")).scalar()
    engine.dispose()
    return int(n or 0)


def _rows(db: Path) -> list[dict]:
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.connect() as conn:
        rs = conn.execute(text("SELECT ts, level, logger, msg, context, is_imported FROM logs")).all()
    engine.dispose()
    return [dict(zip(["ts", "level", "logger", "msg", "context", "is_imported"], r)) for r in rs]


# ---- JSONL --------------------------------------------------------------


def test_jsonl_import(tmp_path):
    src = tmp_path / "a.jsonl"
    src.write_text(
        "\n".join(
            json.dumps({"ts": "2026-05-13T07:00:00", "level": "INFO", "logger": "x", "msg": f"r{i}"})
            for i in range(5)
        ),
        encoding="utf-8",
    )
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", "jsonl"])
    assert rc == 0
    assert _count(db) == 5
    assert _count(db, "is_imported=1") == 5


# ---- nginx-combined -----------------------------------------------------


def test_nginx_combined_import(tmp_path):
    src = tmp_path / "access.log"
    src.write_text(
        '192.168.1.1 - - [13/May/2026:07:00:01 +0000] "GET /api/foo HTTP/1.1" 200 1234 "-" "Mozilla/5.0"\n'
        '10.0.0.2 - alice [13/May/2026:07:00:02 +0000] "POST /api/bar HTTP/1.1" 503 0 "-" "curl/7"\n',
        encoding="utf-8",
    )
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", "nginx-combined"])
    assert rc == 0
    rows = _rows(db)
    assert len(rows) == 2
    assert rows[0]["level"] == "INFO"  # 200
    assert rows[1]["level"] == "ERROR"  # 503
    ctx = json.loads(rows[0]["context"])
    assert ctx["client_ip"] == "192.168.1.1"


# ---- syslog -------------------------------------------------------------


def test_syslog_import(tmp_path):
    src = tmp_path / "syslog.log"
    src.write_text(
        "<13>May 13 07:00:01 myhost myapp[1234]: started ok\n"
        "<11>May 13 07:00:02 myhost myapp: connection lost\n",
        encoding="utf-8",
    )
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", "syslog"])
    assert rc == 0
    rows = _rows(db)
    assert len(rows) == 2
    # severity 5 (notice) -> INFO, severity 3 (error) -> ERROR.
    assert "INFO" in {r["level"] for r in rows}
    assert "ERROR" in {r["level"] for r in rows}


# ---- journald-json ------------------------------------------------------


def test_journald_json_import(tmp_path):
    src = tmp_path / "journal.json"
    src.write_text(
        json.dumps(
            {
                "__REALTIME_TIMESTAMP": "1747120800000000",
                "PRIORITY": "3",
                "_SYSTEMD_UNIT": "myservice.service",
                "MESSAGE": "boom",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", "journald-json"])
    assert rc == 0
    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0]["level"] == "ERROR"
    assert rows[0]["msg"] == "boom"


# ---- raw ----------------------------------------------------------------


def test_raw_import(tmp_path):
    src = tmp_path / "plain.log"
    src.write_text("line one\nline two\nline three\n", encoding="utf-8")
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", "raw"])
    assert rc == 0
    assert _count(db) == 3
    rows = _rows(db)
    assert rows[0]["msg"] == "line one"
    assert rows[0]["level"] == "INFO"


# ---- regex escape hatch -------------------------------------------------


def test_regex_parser(tmp_path):
    src = tmp_path / "custom.log"
    src.write_text(
        "2026-05-13 ERROR auth checkout failure\n"
        "2026-05-13 INFO auth login ok\n",
        encoding="utf-8",
    )
    db = tmp_path / "out.sqlite"
    rc = _run(
        [
            str(src),
            "--db",
            str(db),
            "--format",
            r"regex:(?P<ts>\S+)\s+(?P<level>\S+)\s+(?P<logger>\S+)\s+(?P<msg>.+)",
        ]
    )
    assert rc == 0
    rows = _rows(db)
    assert len(rows) == 2
    assert rows[0]["msg"] == "checkout failure"
    assert rows[0]["logger"] == "auth"


def test_regex_without_msg_group_rejected(tmp_path):
    src = tmp_path / "x.log"
    src.write_text("hi\n", encoding="utf-8")
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", r"regex:(?P<level>\S+)"])
    assert rc == 2


# ---- compression --------------------------------------------------------


def test_gz_transparent_decode(tmp_path):
    src = tmp_path / "logs.jsonl.gz"
    with gzip.open(src, "wt", encoding="utf-8") as fh:
        for i in range(3):
            fh.write(json.dumps({"ts": "2026", "level": "INFO", "msg": f"r{i}"}) + "\n")
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", "jsonl"])
    assert rc == 0
    assert _count(db) == 3


# ---- strict mode --------------------------------------------------------


def test_strict_aborts_on_first_error(tmp_path):
    src = tmp_path / "mixed.jsonl"
    src.write_text(
        '{"ts": "2026", "level": "INFO", "msg": "ok"}\n'
        "garbage line not json\n"
        '{"ts": "2026", "level": "INFO", "msg": "after"}\n',
        encoding="utf-8",
    )
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", "jsonl", "--strict"])
    assert rc == 2


def test_non_strict_skips_bad_lines(tmp_path):
    src = tmp_path / "mixed.jsonl"
    src.write_text(
        '{"ts": "2026", "level": "INFO", "msg": "ok"}\n'
        "garbage line not json\n"
        '{"ts": "2026", "level": "INFO", "msg": "after"}\n',
        encoding="utf-8",
    )
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db), "--format", "jsonl"])
    assert rc == 0
    assert _count(db) == 2


# ---- is_imported marker -------------------------------------------------


def test_imported_rows_marked_out_of_chain(tmp_path):
    src = tmp_path / "a.jsonl"
    src.write_text(json.dumps({"ts": "2026", "level": "INFO", "msg": "r"}) + "\n", encoding="utf-8")
    db = tmp_path / "out.sqlite"
    _run([str(src), "--db", str(db), "--format", "jsonl"])
    assert _count(db, "is_imported=1 AND chain_pos=0") == 1


# ---- source-tag ---------------------------------------------------------


def test_source_tag_added_to_context(tmp_path):
    src = tmp_path / "a.jsonl"
    src.write_text(json.dumps({"ts": "2026", "level": "INFO", "msg": "r"}) + "\n", encoding="utf-8")
    db = tmp_path / "out.sqlite"
    _run([str(src), "--db", str(db), "--format", "jsonl", "--source-tag", "prod-nginx"])
    rows = _rows(db)
    ctx = json.loads(rows[0]["context"])
    assert ctx["import_source"] == "prod-nginx"


# ---- auto-detect --------------------------------------------------------


def test_auto_detect_jsonl(tmp_path):
    src = tmp_path / "a.jsonl"
    src.write_text(json.dumps({"ts": "2026", "level": "INFO", "msg": "r"}) + "\n", encoding="utf-8")
    db = tmp_path / "out.sqlite"
    rc = _run([str(src), "--db", str(db)])  # no --format
    assert rc == 0
    assert _count(db) == 1


def test_missing_input_exits_2(tmp_path):
    rc = _run([str(tmp_path / "missing.log"), "--db", str(tmp_path / "out.sqlite")])
    assert rc == 2
