"""`ulog validate-resources` — scan + parse resource files (PRD-v0.9).

Walks a directory and parses every *.json / *.toml / *.csv / *.ini
(YAML opt-in via PyYAML when installed). Exit code = number of files
that failed to parse — drop-in CI gate against malformed configs.
"""

from __future__ import annotations

import argparse
import configparser
import csv as _csv
import json
import sys
from pathlib import Path
from typing import Any

# Stdlib `tomllib` is available 3.11+; we require 3.10+, fall back to None.
try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]

DEFAULT_TYPES = ("json", "toml", "csv", "ini")
SUPPORTED_TYPES = ("json", "toml", "csv", "ini", "yaml")

# Default-skipped directories (vendored deps, build artefacts).
DEFAULT_EXCLUDES = (
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".git",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "vendor",
    ".tailwind",
    ".benchmarks",
)


def register(subparsers: Any) -> None:
    sp = subparsers.add_parser(
        "validate-resources",
        help="Parse every JSON/TOML/CSV/INI file under a path; exit = failure count.",
    )
    sp.add_argument("--path", type=Path, default=Path("."), help="Root directory.")
    sp.add_argument(
        "--types",
        default=",".join(DEFAULT_TYPES),
        help=(
            f"Comma-separated file types (default: {','.join(DEFAULT_TYPES)}). "
            f"Recognised: {','.join(SUPPORTED_TYPES)}. `yaml` requires PyYAML."
        ),
    )
    sp.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Directory name to skip (repeatable). "
            f"Always skips: {','.join(DEFAULT_EXCLUDES)}"
        ),
    )
    sp.add_argument(
        "-v", "--verbose", action="store_true", help="Print every file scanned, not just failures."
    )
    sp.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    if not args.path.exists():
        print(f"ulog validate-resources: path not found: {args.path}", file=sys.stderr)
        return 2

    types = tuple(t.strip().lower() for t in args.types.split(",") if t.strip())
    unknown = set(types) - set(SUPPORTED_TYPES)
    if unknown:
        print(
            f"ulog validate-resources: unknown types {sorted(unknown)}; "
            f"recognised: {','.join(SUPPORTED_TYPES)}",
            file=sys.stderr,
        )
        return 2

    excludes = set(DEFAULT_EXCLUDES) | set(args.exclude)
    extensions = {f".{t}" for t in types}
    # YAML matches both .yml and .yaml
    if "yaml" in types:
        extensions |= {".yml", ".yaml"}

    failures: list[tuple[Path, str]] = []
    ok = 0

    for path in sorted(args.path.rglob("*")):
        if not path.is_file():
            continue
        if any(part in excludes for part in path.parts):
            continue
        ext = path.suffix.lower()
        if ext not in extensions:
            continue
        err = _validate_one(path, ext)
        if err is None:
            ok += 1
            if args.verbose:
                print(f"  ✓ {path}")
        else:
            failures.append((path, err))
            print(f"  ✗ {path}: {err}", file=sys.stderr)

    total = ok + len(failures)
    print(
        f"\nscanned {total} files: {ok} OK, {len(failures)} broken",
        file=sys.stderr,
    )
    return len(failures)


def _validate_one(path: Path, ext: str) -> str | None:
    """Parse one file; return None on success, error message on failure."""
    try:
        if ext == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif ext == ".toml":
            if tomllib is None:
                return "tomllib unavailable (Python < 3.11)"
            with path.open("rb") as fh:
                tomllib.load(fh)
        elif ext == ".csv":
            with path.open(encoding="utf-8", newline="") as fh:
                reader = _csv.reader(fh)
                for _ in reader:
                    pass
        elif ext == ".ini":
            cp = configparser.ConfigParser()
            cp.read(path, encoding="utf-8")
        elif ext in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                return "PyYAML not installed (skip with --types or pip install pyyaml)"
            with path.open(encoding="utf-8") as fh:
                yaml.safe_load(fh)
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    return None
