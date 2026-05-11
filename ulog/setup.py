"""ULog setup + helpers (FR1-FR3, FR15-FR20).

`setup()` is the only function 99% of users need. It:
  - resolves the color decision via `_color.resolve_color`
  - builds a formatter via `formatters._resolve_formatter`
  - removes any previously-installed ULog handler (idempotency, FR2)
  - installs a fresh StreamHandler tagged `_ulog_managed=True`
  - applies the requested level

`get_logger()` and `set_level()` are thin stdlib passthroughs so users
keep the standard `logging.Logger` API.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from pathlib import Path
from typing import IO, Any, Literal

from ._color import ColorMode, resolve_color
from .formatters import _resolve_formatter

LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

PROFILES: tuple[str, ...] = ("prod", "test")
ProfileChoice: tuple[str, ...] = ("prod", "test", "auto")
Profile = Literal["prod", "test", "auto"]


def default_db_path(profile: str = "prod") -> Path:
    """Return the canonical SQLite path for a profile.

    `~/.cache/ulog/<profile>.sqlite` by default. Honors the `XDG_CACHE_HOME`
    env var on Linux/macOS systems that follow the spec.

    The `prod` profile is for the application's regular runs; the `test`
    profile is for pytest sessions (auto-selected when ULog detects
    pytest). Both can be opened independently in `ulog-web`.
    """
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; valid: {', '.join(PROFILES)}")
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return cache_dir / "ulog" / f"{profile}.sqlite"


def _auto_profile() -> Profile:
    """Detect the default profile based on the running interpreter.

    Returns `'test'` when pytest is in charge (we look for the
    `PYTEST_CURRENT_TEST` env var pytest sets per-test, OR `pytest`
    in `sys.modules` — covers `pytest` invocations and direct
    pytest-internal calls). Otherwise `'prod'`.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return "test"
    if "pytest" in sys.modules:
        return "test"
    return "prod"


def setup(
    *,
    level: LogLevel | str = "INFO",
    format: str = "qlnes",
    color: ColorMode = "auto",
    stream: IO[str] | None = None,
    name: str | None = None,
    propagate: bool = False,
    handlers: list[str] | None = None,
    profile: Profile | str | None = None,
    sql_url: str | None = None,
    sql_table: str = "logs",
    sql_batch_size: int = 100,
    json_path: str | None = None,
    csv_path: str | None = None,
    **formatter_kwargs: Any,
) -> logging.Logger:
    """Configure a ulog-managed handler on the named (or root) logger.

    Args:
      level: minimum level to emit. Accepts a string ('INFO') or stdlib
        int constant (`logging.INFO`).
      format: name of a registered formatter — built-ins are 'qlnes',
        'simple', 'verbose', 'json'. Custom names register via
        `register_formatter()`.
      color: 'auto' (default — TTY-detect), 'always', or 'never'. The
        `NO_COLOR` env var hard-clamps to 'never' regardless.
      stream: defaults to `sys.stderr`. Tests inject `io.StringIO`.
      name: target logger name; `None` means the root logger.
      propagate: bubble records to parent loggers (default False for
        named setup, True for root).
      handlers: list of handler kinds to install. Default depends on
        `profile`:
          - `profile='prod'` (or auto-detected) → `['stream', 'sql']`
            with sql_url defaulting to `~/.cache/ulog/prod.sqlite`.
          - `profile='test'` → `['stream', 'sql']` with sql_url
            defaulting to `~/.cache/ulog/test.sqlite`. ULog
            auto-selects 'test' when pytest is in charge.
          - `profile=None` AND no auto-detect → `['stream']` only
            (preserves the v0.1 zero-storage default).
        Recognized:
          - 'stream' — standard formatted output to `stream`.
          - 'sql'    — SQLAlchemy persistence (needs `sql_url=...`).
          - 'json'   — JSONLineHandler (needs `json_path=...`).
          - 'csv'    — CSVHandler (needs `csv_path=...`).
      profile: high-level shortcut — 'prod' or 'test'. Resolves to a
        default `sql_url` under `~/.cache/ulog/<profile>.sqlite`. If
        an explicit `sql_url=` is also passed, that wins. Auto-detected
        as 'test' when pytest is running, otherwise 'prod'. Pass
        `profile='prod'` explicitly inside fixtures to opt out.
      sql_url, sql_table, sql_batch_size: forwarded to SQLHandler.
        Explicit `sql_url=` overrides the profile's default path.
      json_path: forwarded to JSONLineHandler.
      csv_path: forwarded to CSVHandler.
      **formatter_kwargs: passed to the stream formatter — e.g.
        `prefix='myapp'` for QlnesFormatter.

    Returns the configured `logging.Logger`.
    """
    if level not in LOG_LEVELS and not isinstance(level, int):
        raise ValueError(f"unknown log level {level!r}; valid: {', '.join(LOG_LEVELS)}")
    if color not in ("auto", "always", "never"):
        raise ValueError(f"unknown color mode {color!r}; valid: 'auto', 'always', 'never'")

    use_stream = stream if stream is not None else sys.stderr
    color_on = resolve_color(color, use_stream)

    # Profile resolution.
    #   - profile=None (default) → preserves v0.1 stream-only behavior;
    #     no SQL side effect.
    #   - profile='prod' → ['stream', 'sql'] + ~/.cache/ulog/prod.sqlite
    #   - profile='test' → ['stream', 'sql'] + ~/.cache/ulog/test.sqlite
    #   - profile='auto' → 'test' if pytest is running, else 'prod'.
    #     Pick this for run scripts / demos that want the right thing
    #     to happen in both environments without thinking about it.
    if profile is not None and profile not in ProfileChoice:
        raise ValueError(f"unknown profile {profile!r}; valid: {', '.join(ProfileChoice)}")
    if profile == "auto":
        profile = _auto_profile()
    if profile is not None:
        if handlers is None:
            handlers = ["stream", "sql"]
        if sql_url is None and "sql" in handlers:
            db_path = default_db_path(profile)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            sql_url = f"sqlite:///{db_path}"

    handler_kinds = handlers if handlers is not None else ["stream"]

    logger = logging.getLogger(name)

    # FR2 idempotency: drop only handlers WE installed; preserve user
    # handlers (e.g. file handlers attached separately). Closing each
    # handler we drop releases its file/DB connection cleanly.
    for h in list(logger.handlers):
        if getattr(h, "_ulog_managed", False):
            with contextlib.suppress(Exception):
                h.close()
            logger.removeHandler(h)

    for kind in handler_kinds:
        handler = _build_handler(
            kind,
            stream=use_stream,
            color_on=color_on,
            format=format,
            sql_url=sql_url,
            sql_table=sql_table,
            sql_batch_size=sql_batch_size,
            json_path=json_path,
            csv_path=csv_path,
            **formatter_kwargs,
        )
        handler._ulog_managed = True  # type: ignore[attr-defined]
        logger.addHandler(handler)

    logger.setLevel(level)
    if name is not None:
        logger.propagate = propagate

    return logger


def _build_handler(
    kind: str,
    *,
    stream: IO[str],
    color_on: bool,
    format: str,
    sql_url: str | None,
    sql_table: str,
    sql_batch_size: int,
    json_path: str | None,
    csv_path: str | None,
    **formatter_kwargs: Any,
) -> logging.Handler:
    """Internal: instantiate one handler from a kind name."""
    if kind == "stream":
        formatter = _resolve_formatter(format, color_on=color_on, **formatter_kwargs)
        h: logging.Handler = logging.StreamHandler(stream)
        h.setFormatter(formatter)
        return h
    if kind == "sql":
        from .handlers.sql import SQLHandler

        return SQLHandler(sql_url, table=sql_table, batch_size=sql_batch_size)
    if kind == "json":
        if json_path is None:
            raise ValueError("handlers=['json'] requires a `json_path=` argument.")
        from .handlers.json_line import JSONLineHandler

        return JSONLineHandler(json_path)
    if kind == "csv":
        if csv_path is None:
            raise ValueError("handlers=['csv'] requires a `csv_path=` argument.")
        from .handlers.csv_file import CSVHandler

        return CSVHandler(csv_path)
    raise ValueError(f"unknown handler kind {kind!r}; valid: 'stream', 'sql', 'json', 'csv'")


def get_logger(name: str | None = None) -> logging.Logger:
    """Return `logging.getLogger(name)` — a normal stdlib logger.

    Works whether or not `setup()` has been called. In a library use
    pattern, callers do `log = ulog.get_logger(__name__)` and the
    application decides logging policy via `setup()` (or doesn't, in
    which case Python's defaults apply).
    """
    return logging.getLogger(name)


def set_level(level: LogLevel | str | int, name: str | None = None) -> None:
    """Adjust an existing logger's level without re-running setup.

    Convenience for CLI tools that want to flip levels mid-run (e.g.
    `--debug` raising the level after argument parsing).
    """
    logging.getLogger(name).setLevel(level)


def is_configured(name: str | None = None) -> bool:
    """Return True if `setup()` has been called for that logger name.

    Detects ulog-managed handlers specifically — user-installed
    handlers (or other logging configurations) do not count.
    """
    logger = logging.getLogger(name)
    return any(getattr(h, "_ulog_managed", False) for h in logger.handlers)
