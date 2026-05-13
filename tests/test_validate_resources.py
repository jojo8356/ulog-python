"""Tests for `ulog validate-resources` (PRD-v0.9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ulog._cli import main as cli_main


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_clean_tree_exits_0(tmp_path, capsys):
    _write(tmp_path / "good.json", '{"a": 1}')
    _write(tmp_path / "good.toml", '[section]\nx = 1')
    _write(tmp_path / "good.csv", "a,b\n1,2\n")
    _write(tmp_path / "good.ini", "[s]\nk = v\n")
    rc = cli_main(["validate-resources", "--path", str(tmp_path)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "4 OK" in err
    assert "0 broken" in err


def test_broken_json_exits_nonzero(tmp_path, capsys):
    _write(tmp_path / "bad.json", '{"a": ')
    rc = cli_main(["validate-resources", "--path", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "bad.json" in err
    assert "JSONDecodeError" in err


def test_broken_toml_exits_nonzero(tmp_path, capsys):
    _write(tmp_path / "bad.toml", "k = ")
    rc = cli_main(["validate-resources", "--path", str(tmp_path)])
    assert rc >= 1


def test_types_filter_skips_others(tmp_path, capsys):
    _write(tmp_path / "bad.toml", "k = ")
    _write(tmp_path / "good.json", '{"a": 1}')
    rc = cli_main(["validate-resources", "--path", str(tmp_path), "--types", "json"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "1 OK" in err


def test_skips_default_excludes(tmp_path, capsys):
    _write(tmp_path / "good.json", '{"a": 1}')
    _write(tmp_path / "node_modules" / "bad.json", "garbage")
    _write(tmp_path / ".venv" / "lib" / "bad.json", "{")
    rc = cli_main(["validate-resources", "--path", str(tmp_path)])
    assert rc == 0


def test_custom_exclude(tmp_path):
    _write(tmp_path / "good.json", '{"a": 1}')
    _write(tmp_path / "skipme" / "bad.json", "{")
    rc = cli_main(
        ["validate-resources", "--path", str(tmp_path), "--exclude", "skipme"]
    )
    assert rc == 0


def test_missing_path_exits_2(tmp_path, capsys):
    rc = cli_main(["validate-resources", "--path", str(tmp_path / "missing")])
    assert rc == 2


def test_multiple_failures_reported(tmp_path):
    _write(tmp_path / "a.json", "{")
    _write(tmp_path / "b.json", "}")
    _write(tmp_path / "c.json", "garbage")
    rc = cli_main(["validate-resources", "--path", str(tmp_path)])
    assert rc == 3


def test_verbose_lists_ok_files(tmp_path, capsys):
    _write(tmp_path / "good.json", '{"a": 1}')
    rc = cli_main(["validate-resources", "--path", str(tmp_path), "-v"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "good.json" in out
