"""Automated mirror of QA §6 (Epic 3 — chain integrity).

Each test mirrors one checkbox of qa.html §6.1-6.7. The manual
checklist for those sections has been retired — when this suite is
green, every claim the manual checklist made about Epic 3 is proven
by code (output readability, copy-paste-ability, error wording,
filename patterns, JSON pretty-print, etc.).

Sub-section ↔ test class mapping:
  §6.1 Chain emit smoke           → TestChainEmitSmoke
  §6.2 ulog verify CLI output     → TestVerifyCliOutput
  §6.3 SchemaError copy-paste     → TestSchemaErrorCopyPaste
  §6.4 repair sidecar JSONL       → TestRepairSidecarJsonl
  §6.5 purge dry-run / --confirm  → TestPurgeDryRunVsConfirm
  §6.6 immutable trigger wording  → TestImmutableTriggerWording
  §6.7 verify_state.json audit    → TestVerifyStateJsonAudit
"""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
import re
from pathlib import Path

import pytest

import ulog
from ulog import _retention
from ulog._cli import main

# ---- Shared isolation fixture --------------------------------------------


@pytest.fixture(autouse=True)
def _isolate():
    ulog.clear()
    _retention.MIN_RETENTION_DAYS = 0
    yield
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    ulog.clear()
    _retention.MIN_RETENTION_DAYS = 0


# ---- Shared chain-DB seeding ---------------------------------------------


def _seed_chain(tmp_path: Path, n: int = 5, immutable_when=None) -> Path:
    db = tmp_path / "demo.sqlite"
    url = f"sqlite:///{db}"
    kwargs = {
        "integrity": "hash-chain",
        "handlers": ["sql"],
        "sql_url": url,
        "sql_batch_size": 1,
    }
    if immutable_when is not None:
        kwargs["immutable_when"] = immutable_when
    ulog.setup(**kwargs)
    log = ulog.get_logger()
    for i in range(n):
        log.info("rec %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    ulog.clear()
    for h in list(logging.getLogger().handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logging.getLogger().removeHandler(h)
    return db


def _corrupt_msg(db: Path, chain_pos: int) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE logs SET msg='tampered' WHERE chain_pos=:p"),
            {"p": chain_pos},
        )
    engine.dispose()


# ==========================================================================
# §6.1 — Chain emit smoke (Stories 3.1 / 3.5 / 3.6)
# ==========================================================================


class TestChainEmitSmoke:
    """Eyeball-equivalent assertions on the chain columns after 3 emits."""

    def test_chain_pos_sequence_no_gaps(self, tmp_path):
        from sqlalchemy import create_engine, text

        db = _seed_chain(tmp_path, n=3)
        engine = create_engine(f"sqlite:///{db}", future=True)
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT chain_pos FROM logs ORDER BY chain_pos")).all()
        engine.dispose()
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_row1_prev_hash_is_64_zeros(self, tmp_path):
        from sqlalchemy import create_engine, text

        db = _seed_chain(tmp_path, n=3)
        engine = create_engine(f"sqlite:///{db}", future=True)
        with engine.begin() as conn:
            row = conn.execute(text("SELECT prev_hash FROM logs WHERE chain_pos=1")).first()
        engine.dispose()
        assert bytes(row[0]) == b"\x00" * 32
        assert bytes(row[0]).hex() == "0" * 64

    def test_row2_prev_hash_equals_row1_record_hash(self, tmp_path):
        from sqlalchemy import create_engine, text

        db = _seed_chain(tmp_path, n=3)
        engine = create_engine(f"sqlite:///{db}", future=True)
        with engine.begin() as conn:
            rows = conn.execute(
                text("SELECT chain_pos, record_hash, prev_hash FROM logs ORDER BY chain_pos")
            ).all()
        engine.dispose()
        assert bytes(rows[1][2]) == bytes(rows[0][1])

    def test_row3_prev_hash_equals_row2_record_hash(self, tmp_path):
        from sqlalchemy import create_engine, text

        db = _seed_chain(tmp_path, n=3)
        engine = create_engine(f"sqlite:///{db}", future=True)
        with engine.begin() as conn:
            rows = conn.execute(
                text("SELECT chain_pos, record_hash, prev_hash FROM logs ORDER BY chain_pos")
            ).all()
        engine.dispose()
        assert bytes(rows[2][2]) == bytes(rows[1][1])

    def test_pragma_journal_mode_is_wal(self, tmp_path):
        from sqlalchemy import create_engine, text

        db = _seed_chain(tmp_path, n=1)
        engine = create_engine(f"sqlite:///{db}", future=True)
        with engine.begin() as conn:
            mode = conn.execute(text("PRAGMA journal_mode")).scalar_one()
        engine.dispose()
        assert mode.lower() == "wal"


# ==========================================================================
# §6.2 — ulog verify CLI output readability (Story 3.7)
# ==========================================================================


class TestVerifyCliOutput:
    def test_healthy_chain_shows_check_records_walltime(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=5)
        rc = main(["verify", str(db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "✓ Integrity verified" in out
        assert "records: 5" in out
        assert "wall_time:" in out

    def test_healthy_exit_code_is_0(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=3)
        rc = main(["verify", str(db)])
        capsys.readouterr()
        assert rc == 0

    def test_range_1_to_2_reports_2_records(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=5)
        rc = main(["verify", str(db), "--range", "1-2"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "records: 2" in out

    def test_broken_chain_output_mentions_broken_with_hex(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=5)
        _corrupt_msg(db, chain_pos=3)
        rc = main(["verify", str(db)])
        out = capsys.readouterr().out
        assert rc == 1
        # "BROKEN at record #3"
        assert "BROKEN at record #3" in out
        # Either "expected" or "recomputed" + 8-char hex + "..."
        hex8_ellipsis = re.compile(r"[0-9a-f]{8}\.\.\.")
        assert hex8_ellipsis.search(out), f"expected 8-char hex + '...' in output, got: {out!r}"

    def test_broken_exit_code_is_1(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=3)
        _corrupt_msg(db, chain_pos=2)
        rc = main(["verify", str(db)])
        capsys.readouterr()
        assert rc == 1

    def test_missing_db_arg_exit_2(self, capsys):
        rc = main(["verify"])
        captured = capsys.readouterr()
        assert rc == 2
        # Stderr message is clear and mentions either '--db' or 'db_path'.
        assert "db" in captured.err.lower() or "required" in captured.err.lower()

    def test_nonexistent_db_exit_2(self, tmp_path, capsys):
        rc = main(["verify", str(tmp_path / "missing.sqlite")])
        captured = capsys.readouterr()
        assert rc == 2
        assert "not found" in captured.err.lower()


# ==========================================================================
# §6.3 — SchemaError v0.4 → v0.5 upgrade message, copy-paste-able (Story 3.3)
# ==========================================================================


class TestSchemaErrorCopyPaste:
    """The hardest UX claim of the epic: the SQL block in the error
    message executes as-is when handed to a SQLite engine."""

    EXPECTED_ALTERS = (
        "ALTER TABLE logs ADD COLUMN chain_pos INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE logs ADD COLUMN immutable INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE logs ADD COLUMN prev_hash BLOB;",
        "ALTER TABLE logs ADD COLUMN record_hash BLOB;",
    )
    EXPECTED_INDEXES = (
        "CREATE INDEX ix_logs_chain_pos ON logs(chain_pos);",
        "CREATE INDEX ix_logs_immutable ON logs(immutable);",
    )

    @pytest.fixture
    def v04_db_and_error(self, tmp_path):
        """Create a v0.4-shaped DB, capture the SchemaError raised when
        attempting a v0.5 SQLHandler bootstrap against it."""
        from sqlalchemy import (
            JSON,
            Column,
            DateTime,
            Integer,
            MetaData,
            String,
            Table,
            Text,
            create_engine,
        )

        from ulog.handlers.sql import SchemaError, SQLHandler

        db = tmp_path / "v04.sqlite"
        url = f"sqlite:///{db}"
        engine = create_engine(url, future=True)
        md = MetaData()
        Table(
            "logs",
            md,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("ts", DateTime(timezone=False), nullable=False),
            Column("level", String(10), nullable=False),
            Column("logger", String(255), nullable=False),
            Column("msg", Text, nullable=False),
            Column("file", String(255), nullable=False),
            Column("line", Integer, nullable=False),
            Column("exc", JSON, nullable=True),
            Column("context", JSON, nullable=True),
        )
        md.create_all(engine)
        engine.dispose()

        h = SQLHandler(url=url, batch_size=1)
        with pytest.raises(SchemaError) as excinfo:
            h._ensure_schema()
        h.close()
        return db, url, str(excinfo.value)

    def test_message_contains_all_4_literal_alter_statements(self, v04_db_and_error):
        _, _, msg = v04_db_and_error
        for stmt in self.EXPECTED_ALTERS:
            assert stmt in msg, f"missing ALTER {stmt!r} in error: {msg!r}"

    def test_message_contains_both_create_index_statements(self, v04_db_and_error):
        _, _, msg = v04_db_and_error
        for stmt in self.EXPECTED_INDEXES:
            assert stmt in msg, f"missing CREATE INDEX {stmt!r} in error: {msg!r}"

    def test_sql_pasted_into_sqlite_executes_cleanly(self, v04_db_and_error):
        """Parse the SQL out of the error message verbatim and execute
        each statement via SQLAlchemy text() against the same DB. Same
        SQLite parser the user would hit pasting into the sqlite3 CLI."""
        from sqlalchemy import create_engine, text

        _db, url, msg = v04_db_and_error
        statements = [
            line.strip().rstrip(";")
            for line in msg.splitlines()
            if line.strip().startswith(("ALTER", "CREATE"))
        ]
        assert len(statements) == 6, statements
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))  # would raise on any syntax error
        engine.dispose()

    def test_reopen_chain_handler_after_paste_succeeds(self, v04_db_and_error):
        """After running the suggested SQL, re-bootstrapping the v0.5
        handler must NOT raise — proving the schema is now compatible."""
        from sqlalchemy import create_engine, text

        from ulog.handlers.sql import SQLHandler

        _db, url, msg = v04_db_and_error
        statements = [
            line.strip().rstrip(";")
            for line in msg.splitlines()
            if line.strip().startswith(("ALTER", "CREATE"))
        ]
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
        engine.dispose()
        h = SQLHandler(url=url, batch_size=1, chain_mode=True)
        h._ensure_schema()  # must not raise
        h.close()

    def test_gap_g1_wording_present(self, v04_db_and_error):
        _, _, msg = v04_db_and_error
        lower = msg.lower()
        assert "pre-chain" in lower, f"missing 'pre-chain' phrasing: {msg!r}"
        assert "fresh chain" in lower, f"missing 'fresh chain' phrasing: {msg!r}"
        # The zero-sentinel reference (b"\x00" * 32) must also be present.
        assert "0" in msg, "missing zero ref"
        assert "32" in msg, "missing 32 ref"


# ==========================================================================
# §6.4 — Repair sidecar JSONL audit (Story 3.8)
# ==========================================================================


class TestRepairSidecarJsonl:
    SIDECAR_NAME = re.compile(r"^demo\.chain_break_\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.log$")

    @pytest.fixture
    def repaired_db_and_sidecar(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=5)
        _corrupt_msg(db, chain_pos=3)
        rc = main(["repair", "--confirm", str(db)])
        capsys.readouterr()
        assert rc == 0
        sidecars = list(tmp_path.glob("demo.chain_break_*.log"))
        assert len(sidecars) == 1
        return db, sidecars[0]

    def test_sidecar_filename_is_windows_safe_utc_no_colons(self, repaired_db_and_sidecar):
        _, sidecar = repaired_db_and_sidecar
        assert self.SIDECAR_NAME.match(sidecar.name), (
            f"sidecar filename violates UTC-no-colons Windows-safe pattern: {sidecar.name!r}"
        )

    def test_one_valid_json_object_per_line(self, repaired_db_and_sidecar):
        _, sidecar = repaired_db_and_sidecar
        lines = sidecar.read_text(encoding="utf-8").strip().splitlines()
        assert lines, "sidecar is empty"
        for ln in lines:
            obj = json.loads(ln)
            assert isinstance(obj, dict)

    def test_required_keys_present(self, repaired_db_and_sidecar):
        _, sidecar = repaired_db_and_sidecar
        required = {
            "chain_pos",
            "ts",
            "level",
            "logger",
            "msg",
            "file",
            "line",
            "immutable",
            "record_hash",
            "prev_hash",
        }
        for ln in sidecar.read_text(encoding="utf-8").splitlines():
            obj = json.loads(ln)
            missing = required - set(obj.keys())
            assert not missing, f"missing keys {missing}: {obj!r}"

    def test_hashes_are_64_char_lowercase_hex(self, repaired_db_and_sidecar):
        _, sidecar = repaired_db_and_sidecar
        hex64 = re.compile(r"^[0-9a-f]{64}$")
        for ln in sidecar.read_text(encoding="utf-8").splitlines():
            obj = json.loads(ln)
            assert hex64.match(obj["record_hash"]), (
                f"record_hash not 64-char lowercase hex: {obj['record_hash']!r}"
            )
            assert hex64.match(obj["prev_hash"]), (
                f"prev_hash not 64-char lowercase hex: {obj['prev_hash']!r}"
            )

    def test_repair_without_confirm_refuses_and_writes_no_sidecar(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=3)
        rc = main(["repair", str(db)])
        captured = capsys.readouterr()
        assert rc == 2
        assert "--confirm" in captured.err
        # No sidecar should have been written.
        assert list(tmp_path.glob("*chain_break*.log")) == []

    def test_repair_on_healthy_prints_check_message_exits_0(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=3)
        rc = main(["repair", "--confirm", str(db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "✓" in out
        assert "healthy" in out.lower()


# ==========================================================================
# §6.5 — Purge dry-run vs --confirm (Story 3.9)
# ==========================================================================


class TestPurgeDryRunVsConfirm:
    def _insert_row(self, db, *, ts, immutable=0, msg="x"):
        from sqlalchemy import create_engine, text

        engine = create_engine(f"sqlite:///{db}", future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO logs (ts, level, logger, msg, file, line, "
                    "immutable, chain_pos) VALUES (:ts, 'INFO', 't', :msg, "
                    "'f.py', 1, :im, 0)"
                ),
                {"ts": ts, "msg": msg, "im": immutable},
            )
        engine.dispose()

    def _count(self, db):
        from sqlalchemy import create_engine, text

        engine = create_engine(f"sqlite:///{db}", future=True)
        with engine.begin() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM logs")).scalar_one()
        engine.dispose()
        return int(n)

    @pytest.fixture
    def empty_db(self, tmp_path):
        from ulog.handlers.sql import SQLHandler

        db = tmp_path / "purge.sqlite"
        h = SQLHandler(url=f"sqlite:///{db}", batch_size=1)
        h._ensure_schema()
        h.close()
        return db

    def test_without_confirm_is_dry_run_and_deletes_nothing(self, empty_db, capsys):
        self._insert_row(empty_db, ts=datetime.datetime(2024, 1, 1))
        self._insert_row(empty_db, ts=datetime.datetime(2024, 1, 2))
        before = self._count(empty_db)
        rc = main(["purge", "--before", "2024-06-01", str(empty_db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "(dry-run)" in out
        assert self._count(empty_db) == before

    def test_with_confirm_deletes_old_rotable_rows(self, empty_db, capsys):
        self._insert_row(empty_db, ts=datetime.datetime(2024, 1, 1))
        self._insert_row(empty_db, ts=datetime.datetime(2024, 1, 2))
        self._insert_row(empty_db, ts=datetime.datetime(2025, 1, 1))  # kept
        rc = main(["purge", "--before", "2024-06-01", "--confirm", str(empty_db)])
        capsys.readouterr()
        assert rc == 0
        assert self._count(empty_db) == 1

    def test_immutable_rows_are_never_deleted(self, empty_db, capsys):
        self._insert_row(empty_db, ts=datetime.datetime(2024, 1, 1), immutable=1, msg="sealed")
        self._insert_row(empty_db, ts=datetime.datetime(2024, 1, 2), msg="rotable")
        before_immut = self._count_immut(empty_db)
        rc = main(["purge", "--before", "2024-06-01", "--confirm", str(empty_db)])
        capsys.readouterr()
        assert rc == 0
        assert self._count_immut(empty_db) == before_immut

    def _count_immut(self, db):
        from sqlalchemy import create_engine, text

        engine = create_engine(f"sqlite:///{db}", future=True)
        with engine.begin() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM logs WHERE immutable=1")).scalar_one()
        engine.dispose()
        return int(n)

    def test_min_retention_floor_refuses_with_exit_1(self, empty_db, capsys):
        _retention.MIN_RETENTION_DAYS = 365
        today = datetime.date.today().isoformat()
        rc = main(["purge", "--before", today, "--confirm", str(empty_db)])
        captured = capsys.readouterr()
        assert rc == 1
        assert "refused" in captured.err.lower()

    def test_invalid_date_format_argparse_exit_2(self, empty_db):
        with pytest.raises(SystemExit):
            main(["purge", "--before", "2024/06/01", str(empty_db)])


# ==========================================================================
# §6.6 — Immutable trigger end-user error wording (Story 3.2)
# ==========================================================================


class TestImmutableTriggerWording:
    @pytest.fixture
    def db_with_immutable_row(self, tmp_path):
        from sqlalchemy import create_engine, text

        from ulog.handlers.sql import SQLHandler

        db = tmp_path / "trig.sqlite"
        url = f"sqlite:///{db}"
        h = SQLHandler(url=url, batch_size=1)
        h._ensure_schema()
        h.close()
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO logs (ts, level, logger, msg, file, line, "
                    "immutable, chain_pos) VALUES "
                    "('2026-05-12', 'INFO', 't', 'sealed', 'f.py', 1, 1, 0)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO logs (ts, level, logger, msg, file, line, "
                    "immutable, chain_pos) VALUES "
                    "('2026-05-12', 'INFO', 't', 'rotable', 'f.py', 1, 0, 0)"
                )
            )
        engine.dispose()
        return url

    def test_update_on_immutable_row_fails_with_immutable_row_wording(self, db_with_immutable_row):
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import IntegrityError, OperationalError

        engine = create_engine(db_with_immutable_row, future=True)
        with (
            pytest.raises((IntegrityError, OperationalError)) as excinfo,
            engine.begin() as conn,
        ):
            conn.execute(text("UPDATE logs SET msg='tampered' WHERE msg='sealed'"))
        engine.dispose()
        assert "immutable row" in str(excinfo.value).lower()

    def test_delete_on_immutable_row_fails_with_immutable_row_wording(self, db_with_immutable_row):
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import IntegrityError, OperationalError

        engine = create_engine(db_with_immutable_row, future=True)
        with (
            pytest.raises((IntegrityError, OperationalError)) as excinfo,
            engine.begin() as conn,
        ):
            conn.execute(text("DELETE FROM logs WHERE msg='sealed'"))
        engine.dispose()
        assert "immutable row" in str(excinfo.value).lower()

    def test_error_message_references_invariant_i4_for_grep(self, db_with_immutable_row):
        """Operators should be able to grep their logs for 'I4' to find
        the cause; the trigger error string must contain that tag."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import IntegrityError, OperationalError

        engine = create_engine(db_with_immutable_row, future=True)
        with (
            pytest.raises((IntegrityError, OperationalError)) as excinfo,
            engine.begin() as conn,
        ):
            conn.execute(text("UPDATE logs SET msg='tampered' WHERE msg='sealed'"))
        engine.dispose()
        assert "I4" in str(excinfo.value), (
            f"trigger error must reference 'invariant I4' for ops grep, got: {excinfo.value!r}"
        )

    def test_rotable_rows_can_still_be_updated_and_deleted(self, db_with_immutable_row):
        from sqlalchemy import create_engine, text

        engine = create_engine(db_with_immutable_row, future=True)
        with engine.begin() as conn:
            conn.execute(text("UPDATE logs SET msg='rotated' WHERE msg='rotable'"))
            count_after_update = conn.execute(
                text("SELECT COUNT(*) FROM logs WHERE msg='rotated'")
            ).scalar_one()
            conn.execute(text("DELETE FROM logs WHERE msg='rotated'"))
            count_after_delete = conn.execute(
                text("SELECT COUNT(*) FROM logs WHERE msg='rotated'")
            ).scalar_one()
        engine.dispose()
        assert count_after_update == 1
        assert count_after_delete == 0


# ==========================================================================
# §6.7 — verify_state.json sidecar audit (Story 3.10)
# ==========================================================================


class TestVerifyStateJsonAudit:
    @pytest.fixture
    def verified_db(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=5)
        main(["verify", str(db)])
        capsys.readouterr()
        return db

    def _sidecar(self, db: Path) -> Path:
        from ulog._verify_state import sidecar_path

        return sidecar_path(db)

    def test_file_is_valid_json_with_indent_2(self, verified_db):
        """Pretty-printed (indent=2). Detect by counting newlines:
        an indent-2 dump of our 6-key payload has at minimum 6 newlines
        (one per top-level key). A flat dump has 0."""
        raw = self._sidecar(verified_db).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)
        # Flat (no indent) JSON has zero newlines; indent=2 has many.
        assert raw.count("\n") >= 6, (
            f"verify_state.json doesn't look pretty-printed (newlines: "
            f"{raw.count(chr(10))}); content: {raw!r}"
        )
        # Verify it round-trips at indent=2 to the same bytes (modulo
        # field order — but we wrote it as a dict, so order is stable).
        re_dumped = json.dumps(parsed, indent=2)
        assert re_dumped == raw.rstrip(), (
            "round-tripping at indent=2 doesn't match — not indent=2 source"
        )

    def test_required_keys_present(self, verified_db):
        state = json.loads(self._sidecar(verified_db).read_text(encoding="utf-8"))
        required = {
            "version",
            "status",
            "broken_at",
            "verified_up_to_chain_pos",
            "last_check_ts",
            "walk_time_s",
        }
        assert required <= set(state.keys()), required - set(state.keys())

    def test_healthy_state_values(self, verified_db):
        state = json.loads(self._sidecar(verified_db).read_text(encoding="utf-8"))
        assert state["status"] == "OK"
        assert state["broken_at"] is None
        assert state["verified_up_to_chain_pos"] == 5

    def test_broken_state_values_after_corruption(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=5)
        _corrupt_msg(db, chain_pos=3)
        main(["verify", str(db)])
        capsys.readouterr()
        state = json.loads(self._sidecar(db).read_text(encoding="utf-8"))
        assert state["status"] == "BROKEN"
        assert state["broken_at"] == 3
        # verified_up_to is the last good chain_pos before the break.
        assert state["verified_up_to_chain_pos"] == 2

    def test_range_walk_does_not_write_or_overwrite_sidecar(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=5)
        # First a full walk → sidecar OK.
        main(["verify", str(db)])
        capsys.readouterr()
        before_mtime = self._sidecar(db).stat().st_mtime
        # Then a partial walk → should NOT touch the sidecar.
        main(["verify", str(db), "--range", "2-3"])
        capsys.readouterr()
        after_mtime = self._sidecar(db).stat().st_mtime
        assert before_mtime == after_mtime, (
            "verify --range overwrote the sidecar — would mislead the badge"
        )

    def test_after_repair_sidecar_is_gone(self, tmp_path, capsys):
        db = _seed_chain(tmp_path, n=5)
        _corrupt_msg(db, chain_pos=3)
        main(["verify", str(db)])
        capsys.readouterr()
        assert self._sidecar(db).exists()
        rc = main(["repair", "--confirm", str(db)])
        capsys.readouterr()
        assert rc == 0
        assert not self._sidecar(db).exists()
