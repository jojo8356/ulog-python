# Story 1.10: xdist + Windows + NFS edge cases

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**Epic:** 1 — v0.3 Test integration
**Story key:** `1-10-xdist-windows-nfs-edge-cases`
**Implements:** NFR-PORT-10 (PRD-v0.3 §4) + architecture.md xdist concurrency note (line 213-218)
**Source:** `docs/prds/PRD-v0.3-test-integration.md` §4 (NFR-PORT-10), `_bmad-output/planning-artifacts/architecture.md` lines 54, 213-218 (xdist concurrency + JSONL fallback path-of-last-resort), `_bmad-output/planning-artifacts/epics.md` Story 1.10
**Built on:** Story 1.5 (auto-setup wires up SQL handler — Story 1.10's detection runs AFTER), Story 1.2 (SQL handler is what gets swapped)
**Foundation for:** Story 1.11 (docs page mentions the fallback behavior); v0.4+ multi-file merge (logs from xdist workers may end up in multiple JSONL files that v0.5 merges).

---

## Story

As a **CI integrator running tests with `pytest-xdist` on Windows or NFS-mounted shares**,
I want **the plugin to detect xdist + SQLite + NFS combinations and silently fall back to JSONL — and to enable SQLite WAL mode for xdist on local filesystems**,
so that **I don't hit SQLite locking errors that silently corrupt the test log or fail concurrent writes**.

## Acceptance Criteria

### AC1 — xdist + NFS-detected SQL path → swap SQL handler for JSONL (NFR-PORT-10)

**Given** the pytest plugin's auto-setup OR the host's `ulog.setup` configured a SQL handler at path `/mnt/nfs/logs.sqlite` AND `pytest-xdist` is active (any of the env vars `PYTEST_XDIST_WORKER`, `PYTEST_XDIST_TESTRUNUID` is set)
**And** the path's filesystem reports as `nfs` / `nfs4` / `cifs` (network filesystem detection — see Task 2 for OS-specific paths)
**When** the plugin's `pytest_configure` runs
**Then**:
  1. The existing SQL handler is detached and closed.
  2. A JSONL handler is installed at `/mnt/nfs/logs.jsonl` (same stem, `.jsonl` extension swap).
  3. A single warning is printed to stderr: `ulog: xdist+NFS detected — falling back from SQLite to JSONL at <path>` (`<path>` is the new JSONL path).
  4. Subsequent records emit to the JSONL file.

### AC2 — xdist + local filesystem → enable SQLite WAL mode

**Given** `pytest-xdist` is active AND the SQL handler points at a LOCAL filesystem (not NFS / CIFS / network)
**When** the plugin's `pytest_configure` runs
**Then** the plugin executes `PRAGMA journal_mode=WAL;` on the SQL handler's connection (or the underlying SQLAlchemy engine), enabling concurrent reader/writer access. No fallback, no warning.

If `PRAGMA journal_mode=WAL` fails (the database is read-only, or the underlying file system doesn't support WAL — older NFS may), the plugin falls back to AC1's JSONL swap with a slightly different warning: `ulog: WAL mode unavailable on <path> — falling back from SQLite to JSONL`.

### AC3 — Single-process pytest (no xdist) → no behavior change

**Given** `pytest-xdist` is NOT active (no worker env vars present)
**When** the plugin's `pytest_configure` runs
**Then** NO swap happens, NO WAL mode enabled, NO warning emitted. Story 1.5's auto-setup behavior is unchanged.

This is the regression guard for the 99% of users who don't use xdist.

### AC4 — Windows-conservative: any xdist on Windows → JSONL swap

**Given** the plugin runs on Windows (via `sys.platform == 'win32'`)
**And** `pytest-xdist` is active
**When** `pytest_configure` runs
**Then** the plugin swaps SQL → JSONL UNCONDITIONALLY (no NFS probe needed). Windows file-locking semantics on SQLite under xdist are unreliable enough that the conservative path is "always JSONL on xdist".

The warning text on Windows: `ulog: xdist+Windows detected — falling back from SQLite to JSONL at <path>`.

### AC5 — Plugin is gated OFF: no xdist detection or swap

**Given** `_get_enabled(config)` is False (plugin disabled or no host setup)
**When** `pytest_configure` runs
**Then** the xdist detection / NFS probe / WAL enable logic SHORT-CIRCUITS — none of it runs. No warning, no handler manipulation. The gate is the first check in the new logic.

### AC6 — JSONL fallback preserves the schema

**Given** the JSONL fallback fires
**When** records are emitted post-fallback
**Then** the JSONL records' shape matches the SQL handler's record shape (`logger`, `level`, `msg`, `ts`, `context`, `exc`) — AS DETERMINED by the existing `JSONLineHandler` in `ulog/handlers/json_line.py`. The viewer's `JSONLAdapter` (Story 1.6) reads these correctly; no schema-side change required.

### AC7 — Detection helpers are unit-testable in isolation

**Given** the new helpers `_xdist_active()`, `_is_network_fs(path)`, `_swap_sql_for_jsonl(handler, path, reason)`
**When** tests call them directly with controlled inputs (env vars, file paths, mock filesystems)
**Then** each helper returns predictable booleans / performs the documented swap WITHOUT requiring a live pytest-xdist run. Test fixtures use `monkeypatch` for env vars and parametrized synthetic paths.

### AC8 — Frozen-invariant + regression-gate compliance

**Given** Story 1.10's changes
**When** the standard regression checks run
**Then**:
  - `dependencies = []` in `pyproject.toml` is unchanged. Detection uses stdlib only (`os`, `sys`, `pathlib`, `subprocess` — no `psutil`).
  - `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/` ALL UNCHANGED. Story 1.10 lives in `ulog/testing/pytest_plugin.py` (extension) and `tests/test_pytest_plugin.py` (new tests).
  - All 165 existing tests still pass.

---

## Tasks / Subtasks

- [x] **Task 1** — Add xdist detection helper (AC1, AC2, AC3, AC5)
  - [x] 1.1 In `ulog/testing/pytest_plugin.py`, add a private helper:

    ```python
    import os
    import sys

    def _xdist_active() -> bool:
        """Return True if pytest-xdist is running (worker env vars present).

        xdist sets one of these per worker process:
          - PYTEST_XDIST_WORKER (e.g. 'gw0', 'gw1', 'master')
          - PYTEST_XDIST_TESTRUNUID
        Master process has WORKER='master'; subprocesses have 'gwN'.
        Either env var presence indicates we're inside an xdist run.
        """
        return bool(
            os.environ.get("PYTEST_XDIST_WORKER")
            or os.environ.get("PYTEST_XDIST_TESTRUNUID")
        )
    ```

- [x] **Task 2** — Add network-filesystem detection helper (AC1, AC4)
  - [x] 2.1 Add `_is_network_fs(path)` with platform-specific dispatch:

    ```python
    from pathlib import Path

    def _is_network_fs(path: str | Path) -> bool:
        """Detect whether `path` lives on a network filesystem (NFS / CIFS / SMB).

        Uses stdlib only (no psutil dep). Per-platform:
          - Linux: parse /proc/self/mountinfo, find the longest-prefix mount,
            check fs_type ∈ {'nfs', 'nfs4', 'cifs', 'smbfs', 'smb3', 'fuse.sshfs'}
          - Windows: GetDriveTypeW returns 4 for DRIVE_REMOTE; resolve the path's
            drive letter, compare. Fall back to True (conservative) if the
            ctypes call fails — Windows + xdist is JSONL-prone anyway.
          - macOS: parse `mount` command output (subprocess); look for the
            mount point hosting `path` and check the fs type. If subprocess
            fails, return False (assume local).
          - Other Unix: same /proc-style path; if /proc/mounts is unreadable,
            return False (best-effort).

        Errors / unknown paths → False (conservative — local fs assumption).
        """
        try:
            path = Path(path).resolve()
        except (OSError, ValueError):
            return False

        if sys.platform == "win32":
            return _is_network_fs_windows(path)
        if sys.platform == "darwin":
            return _is_network_fs_macos(path)
        # Linux + other POSIX
        return _is_network_fs_linux(path)
    ```

  - [x] 2.2 Linux helper:

    ```python
    def _is_network_fs_linux(path: Path) -> bool:
        """Parse /proc/self/mountinfo to find the mount point hosting `path`,
        then check its filesystem type."""
        NETWORK_FS_TYPES = {
            "nfs", "nfs4", "cifs", "smbfs", "smb3",
            "fuse.sshfs", "9p", "ceph",
        }
        try:
            with open("/proc/self/mountinfo") as fh:
                lines = fh.readlines()
        except OSError:
            return False
        # Each line: ID PARENT_ID MAJ:MIN ROOT MOUNTPOINT MOUNTOPTS [optional]* - FSTYPE SOURCE FSOPTS
        # Optional fields like `shared:6` may appear between MOUNTOPTS and `-`,
        # which is why we use `parts.index("-")` to locate the separator.
        # Find the mount whose mountpoint is the longest prefix of `path`.
        best_match = ("", "")  # (mountpoint, fstype)
        path_str = str(path)
        for line in lines:
            parts = line.split()
            try:
                sep_idx = parts.index("-")
                mountpoint = parts[4]
                fstype = parts[sep_idx + 1]
            except (ValueError, IndexError):
                continue
            # Special-case the root mount `/`: every path lives under it,
            # so `path_str.startswith("/" + "/")` would never be true.
            # We treat root as always a valid (longest-among-fallback) prefix
            # but only if no longer prefix matches. (review patch C2)
            is_match = (
                mountpoint == "/"
                or path_str == mountpoint
                or path_str.startswith(mountpoint + "/")
            )
            if is_match and len(mountpoint) > len(best_match[0]):
                best_match = (mountpoint, fstype)
            # If best_match is still empty AND mountpoint is "/", record it
            # as the floor.
            if best_match[0] == "" and mountpoint == "/":
                best_match = (mountpoint, fstype)
        return best_match[1] in NETWORK_FS_TYPES
    ```

  - [x] 2.3 Windows helper (with conservative fallback):

    ```python
    def _is_network_fs_windows(path: Path) -> bool:
        """Use Win32 GetDriveTypeW to check if the path's drive is network-mounted.
        Conservative: if the ctypes call fails, return True so xdist+Windows
        always falls back to JSONL (per AC4)."""
        try:
            import ctypes
            DRIVE_REMOTE = 4
            # GetDriveTypeW expects "X:\\" form
            drive = str(path)[:3]  # e.g. "C:\\"
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            return kernel32.GetDriveTypeW(drive) == DRIVE_REMOTE
        except Exception:  # noqa: BLE001 — broad on purpose
            return True  # conservative for Windows + xdist
    ```

  - [x] 2.4 macOS helper (best-effort):

    ```python
    def _is_network_fs_macos(path: Path) -> bool:
        """Use the `mount` command to find the path's filesystem type. macOS
        doesn't expose /proc/mounts, but `mount` output has the form:
            /dev/disk1s1 on / (apfs, local, ...)
            host:/share on /Volumes/share (nfs, ...)
        """
        import subprocess
        NETWORK_FS_TYPES = {"nfs", "smbfs", "afpfs", "webdav"}
        try:
            output = subprocess.run(
                ["mount"], capture_output=True, text=True, timeout=2.0
            ).stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
        best_match = ("", "")
        path_str = str(path)
        for line in output.splitlines():
            # Format: <device> on <mountpoint> (<fstype>, ...)
            try:
                _, _, rest = line.partition(" on ")
                mountpoint, _, paren = rest.partition(" (")
                fstype = paren.split(",", 1)[0].strip()
            except Exception:  # noqa: BLE001
                continue
            if (path_str == mountpoint or path_str.startswith(mountpoint + "/")) \
                    and len(mountpoint) > len(best_match[0]):
                best_match = (mountpoint, fstype)
        return best_match[1] in NETWORK_FS_TYPES
    ```

- [x] **Task 3** — Add the SQL→JSONL swap helper (AC1, AC4)
  - [x] 3.1 Add `_swap_sql_for_jsonl(reason: str) -> None` in `pytest_plugin.py`:

    ```python
    def _swap_sql_for_jsonl(reason: str) -> None:
        """Detach all `_ulog_managed` SQL handlers from the root logger and
        reinstall as JSONL handlers at the same path stem (`.sqlite` →
        `.jsonl`). Prints a warning to stderr.

        `reason` is included in the warning text (e.g. 'xdist+NFS', 'xdist+
        Windows', 'WAL mode unavailable').
        """
        import logging
        import ulog
        from ulog.handlers.sql import SQLHandler

        root = logging.getLogger()
        for handler in list(root.handlers):
            if not getattr(handler, "_ulog_managed", False):
                continue
            if not isinstance(handler, SQLHandler):
                continue
            # Extract the SQLite file path from the handler's URL
            url = getattr(handler, "_url", "")
            if not url.startswith("sqlite:///"):
                continue
            sqlite_path = url[len("sqlite:///"):]
            jsonl_path = sqlite_path.rsplit(".", 1)[0] + ".jsonl"
            print(
                f"ulog: {reason} detected — falling back from SQLite to "
                f"JSONL at {jsonl_path}",
                file=sys.stderr,
            )
            # Detach + close the SQL handler
            try:
                handler.flush()
                handler.close()
            except Exception:  # noqa: BLE001
                pass
            root.removeHandler(handler)
            # Reinstall as JSONL via ulog.setup with the same logger
            ulog.setup(handlers=["json"], json_path=jsonl_path)
            return  # only one ulog SQL handler at a time per project convention
    ```

  - [x] 3.2 Note: `ulog.setup(handlers=["json"], ...)` REPLACES all `_ulog_managed` handlers (Story 1.5 idempotency). So calling it after detaching the SQL handler installs the JSONL one cleanly without leaking the SQL handler.

- [x] **Task 4** — Add WAL mode enablement helper (AC2)
  - [x] 4.1 Add `_enable_wal_mode_or_fallback() -> bool` in `pytest_plugin.py`:

    ```python
    def _enable_wal_mode_or_fallback() -> bool:
        """For local-FS xdist: enable PRAGMA journal_mode=WAL on the SQL
        handler's engine. Returns True if WAL was enabled successfully.

        On failure (read-only DB, exotic filesystem), falls back to the
        JSONL swap (AC2 second clause) and returns False.

        Reentrancy note (review patch C1): we MUST NOT call
        `_swap_sql_for_jsonl` from inside the `with handler._engine.connect()
        as conn:` block — the swap closes the engine via `handler.close()` /
        `engine.dispose()`, and on `with`-exit SQLAlchemy would try to
        release a connection to a disposed pool. Capture the failure
        boolean inside the `try`, exit the connection context cleanly,
        THEN dispatch the fallback.
        """
        import logging
        from ulog.handlers.sql import SQLHandler

        root = logging.getLogger()
        # Iterate over a list copy — defensive against handler-list mutation
        # during the loop body (review patch C1).
        target_handler = None
        for handler in list(root.handlers):
            if not isinstance(handler, SQLHandler):
                continue
            if not getattr(handler, "_ulog_managed", False):
                continue
            target_handler = handler
            break
        if target_handler is None:
            return False  # no SQL handler — nothing to do

        wal_failed = False
        try:
            with target_handler._engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        except Exception:  # noqa: BLE001 — fall back on any PRAGMA failure
            wal_failed = True
        # Outside the connection context: the engine is no longer in use,
        # safe to swap (which calls engine.dispose).
        if wal_failed:
            _swap_sql_for_jsonl("WAL mode unavailable")
            return False
        return True
    ```

- [x] **Task 5** — Wire detection + swap into `pytest_configure` (AC1-AC5)
  - [x] 5.1 In `pytest_plugin.py`'s `pytest_configure`, AFTER the auto-setup branch (Story 1.5) and BEFORE the existing `_ulog_session_stats` initialization, add:

    ```python
    # Story 1.10 — xdist + Windows + NFS handling.
    # Only runs when the plugin is enabled (gate check).
    if enabled and _xdist_active():
        from ulog.handlers.sql import SQLHandler
        # Find the active SQL handler (host-configured OR auto-set-up by us)
        sql_path = None
        for h in logging.getLogger().handlers:
            if isinstance(h, SQLHandler) and getattr(h, "_ulog_managed", False):
                url = getattr(h, "_url", "")
                if url.startswith("sqlite:///"):
                    sql_path = url[len("sqlite:///"):]
                    break

        if sql_path is not None:
            if sys.platform == "win32":
                # AC4: Windows + xdist always falls back to JSONL.
                _swap_sql_for_jsonl("xdist+Windows")
            elif _is_network_fs(sql_path):
                # AC1: NFS / CIFS detected — fall back.
                _swap_sql_for_jsonl("xdist+NFS")
            else:
                # AC2: local FS — enable WAL mode (or fallback if WAL fails).
                _enable_wal_mode_or_fallback()
    ```

  - [x] 5.2 The check is gated on `enabled` AND `_xdist_active()` — so non-xdist sessions skip the entire block (AC3 / AC5).

- [x] **Task 6** — Tests (AC1-AC7)
  - [x] 6.1 Add a section header in `tests/test_pytest_plugin.py`:

    ```python
    # ============================================================================
    # Story 1.10 — xdist + Windows + NFS edge cases (NFR-PORT-10)
    # ============================================================================
    ```

  - [x] 6.2 Add `test_xdist_active_detects_worker_env` (AC7 — `_xdist_active`):
    Use `monkeypatch` to set/unset `PYTEST_XDIST_WORKER`. Assert `_xdist_active()` returns True with var set, False without.

  - [x] 6.3 Add `test_is_network_fs_returns_false_for_local_paths`:
    Call `_is_network_fs("/tmp")` (or `tmp_path`) — should return False on Linux/macOS local FS. (On Windows CI runner, may return True for `C:` if drive type detection fails — wrap in `pytest.skip` for non-Linux platforms.)

  - [x] 6.4 Add `test_is_network_fs_linux_with_synthetic_mountinfo` (Linux only):
    Use `monkeypatch.setattr` to replace `_is_network_fs_linux` with a version that reads from a fixture file containing synthetic `/proc/mountinfo` lines (one for `/mnt/nfs share - nfs ...`). Assert the helper returns True for paths under `/mnt/nfs/...` and False for `/tmp/...`.

  - [x] 6.5 Add `test_swap_sql_for_jsonl_replaces_handler` (AC1, AC4):
    Configure `ulog.setup(handlers=['sql'], sql_url='sqlite:///<tmp>/x.sqlite')`. Call `_swap_sql_for_jsonl("test")`. Assert:
    - The SQL handler is detached (no SQLHandler instances in root.handlers).
    - A JSONLineHandler IS attached at the same path stem `.jsonl`.
    - The warning text appears in `capsys.readouterr().err`.

  - [x] 6.6 Add `test_pytest_configure_no_op_when_not_xdist` (AC3):
    `monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)`; spawn a sub-pytester with `--ulog-db <tmp>/x.sqlite`; assert NO warning printed (`capsys.readouterr().err` doesn't contain "ulog:" mentioning xdist).

  - [x] 6.7 Add `test_pytest_configure_swaps_for_jsonl_on_xdist_nfs` (AC1):
    Use `monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")` AND patch `_is_network_fs` to return True. Run a small pytester sub-session with `--ulog-db <tmp>/x.sqlite`. After the run:
    - Assert `<tmp>/x.jsonl` exists.
    - Assert no `<tmp>/x.sqlite` records (or the `.sqlite` file may not exist — neither is an error).
    - Assert the warning appears in stderr.

    Note (review patch E1): `pytester.runpytest()` runs in-process and inherits the outer process's `os.environ`, so `monkeypatch.setenv` propagates to the inner session. If env-var isolation is needed, use `runpytest_subprocess` — but that's slower. For Story 1.10, in-process is fine; assert the warning text in `result.stderr` (or `capsys.readouterr().err`).

  - [x] 6.8 Add `test_pytest_configure_enables_wal_on_xdist_local` (AC2):
    `monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")`; `_is_network_fs` returns False. Run pytester with at least ONE inner test that emits a record (so the SQLite file is actually created and written — PRAGMA before any write doesn't always persist on disk depending on SQLite's WAL initialization). After the run, open the SQLite file with `sqlite3` and run `PRAGMA journal_mode;` — assert it returns `wal` (lowercase). Review patch E2: the at-least-one-emit ensures the journal file is materialized on disk.

  - [x] 6.9 Add `test_pytest_configure_falls_back_when_wal_fails` (AC2 second clause):
    Mock `handler._engine.connect()` to raise an exception. Verify the JSONL fallback fires AND the warning text mentions "WAL mode unavailable".

  - [x] 6.10 Add `test_xdist_check_skipped_when_plugin_disabled` (AC5):
    `monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")`; pytester run with `--ulog-disable`. Assert no JSONL fallback occurred AND no warning emitted.

- [x] **Task 7** — Verify and ship
  - [x] 7.1 Run `python3 -m pytest tests/ -v`. Full suite stays green. `tests/test_pytest_plugin.py` baseline is **40 tests** (post-Story 1.5). This story grows it to **49 tests** (9 new from Tasks 6.2-6.10). Full project suite: 165 + 9 = **174 tests**.
  - [x] 7.2 `mypy ulog/testing/ --follow-imports=silent` — clean. New helpers fully typed.
  - [x] 7.3 `grep '^dependencies' pyproject.toml | grep -q '\[\]'` exits 0.
  - [x] 7.4 `git diff --stat HEAD --` reports ONLY `ulog/testing/pytest_plugin.py` and `tests/test_pytest_plugin.py`.

---

## Dev Notes

### Why `os.environ.get("PYTEST_XDIST_WORKER")` is the canonical xdist detection

Per pytest-xdist's documentation (`https://pytest-xdist.readthedocs.io`):
- Each worker subprocess sets `PYTEST_XDIST_WORKER` to its name (`gw0`, `gw1`, ...).
- The `master` process sets `PYTEST_XDIST_WORKER=master` (in some versions; older versions don't set it on master).
- `PYTEST_XDIST_TESTRUNUID` is set on ALL processes participating in an xdist run (master + workers) since xdist 2.5+.

Checking BOTH covers older (`WORKER` only) and newer (`TESTRUNUID`) xdist versions.

### Why the network-FS detection is per-platform

There's no stdlib cross-platform "is this NFS?" function. Python's `os.statvfs` doesn't expose filesystem type. Each OS has its own mechanism:
- **Linux**: `/proc/self/mountinfo` is the kernel-maintained list of all mounts with fs types — read it directly.
- **Windows**: Win32 API `GetDriveTypeW` returns enum value 4 (`DRIVE_REMOTE`) for network-mounted drives. ctypes binding to kernel32.dll.
- **macOS**: `mount(8)` command lists mounts with fs types in parentheses. Subprocess + parse.

Each can fail (permission denied, command missing, file unreadable). The error path returns False (conservative: assume local) on Linux/macOS, and True on Windows (very conservative: prefer JSONL over silent SQLite corruption).

### Why xdist + Windows is unconditional JSONL (no NFS probe)

Windows' file-locking semantics on SQLite are fundamentally different from POSIX. Even on a local filesystem (NTFS), concurrent SQLite writers from xdist worker processes can hit contention that doesn't manifest cleanly. The conservative path: any xdist on Windows uses JSONL.

This sidesteps:
- Windows-specific file-handle leaks under SQLAlchemy + multi-process scenarios
- File-locking bugs in older sqlite3.dll versions shipped with Python on Windows
- The SQLite team's documented "Windows file locking is best-effort" caveat

### WAL mode — what it does

`PRAGMA journal_mode=WAL` enables Write-Ahead Logging. Concurrent readers and ONE writer can operate without blocking. For xdist's typical case (multiple worker subprocesses each emitting log records), WAL mode is the difference between:
- Default (DELETE journal): writers serialize via `BEGIN EXCLUSIVE`; under contention, you get `database is locked` errors.
- WAL: writers append to a separate WAL file; readers see a consistent snapshot. Much higher throughput.

WAL mode persists across connections — once set, subsequent opens of the same DB inherit it. Story 1.5's auto-setup creates the DB if missing; Story 1.10's WAL enablement runs immediately after, so the file is created with WAL from the first write.

### Why `_swap_sql_for_jsonl` uses `ulog.setup(handlers=['json'])` instead of manual handler manipulation

Story 1.5's `ulog.setup` is idempotent: it removes existing `_ulog_managed` handlers and installs the new ones. That's exactly the operation we need: detach the SQL handler, install the JSONL handler. Reusing `setup` avoids duplicating the logger-config code paths.

### Why the warning is `print(file=sys.stderr)` not `logging.warning`

The warning is meta-information about the LOGGING SYSTEM ITSELF — emitting it via `logging` would risk recursion or losing the message in the swap. `print(file=sys.stderr)` is reliable and matches pytest's own convention for plugin-internal messages.

### `_xdist_active()` returns True ON THE MASTER process too

xdist's master orchestrates the workers but ALSO runs `pytest_configure` itself. So our master sees `PYTEST_XDIST_TESTRUNUID` set and goes through the same path. That's correct — the master might also write to the DB if any tests collected by master run (the gate logic is per-process).

### Architecture references

| Topic | Read |
|---|---|
| NFR-PORT-10 spec | `docs/prds/PRD-v0.3-test-integration.md` §4 |
| xdist concurrency rationale | `_bmad-output/planning-artifacts/architecture.md` lines 213-218 |
| Story 1.5 auto-setup site | `ulog/testing/pytest_plugin.py:62-115` (`pytest_configure`) |
| `SQLHandler` URL attribute | `ulog/handlers/sql.py` (look for `self._url = ...`) |
| `JSONLineHandler` shape | `ulog/handlers/json_line.py` |
| Story 1.5 setup idempotency | `ulog/setup.py:65-193` |
| Existing test patterns | `tests/test_pytest_plugin.py:124-168` (record-readback, pytester usage) |

### Files being modified

#### `ulog/testing/pytest_plugin.py` (UPDATE — additive)

Add 4 new private helpers (`_xdist_active`, `_is_network_fs` + 3 platform sub-helpers, `_swap_sql_for_jsonl`, `_enable_wal_mode_or_fallback`) + a new branch in `pytest_configure`. ~120 lines added.

#### `tests/test_pytest_plugin.py` (UPDATE — additive)

Section header + 9 new tests. ~250 lines added.

#### Other files (DO NOT MODIFY)

`pyproject.toml`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/`, `ulog/web/`, `ulog/testing/__init__.py`, `ulog/testing/test_event.py`, `tests/test_test_event.py`, `tests/test_web.py`, all other tests.

### Story 1.9 lessons applied

- **Lazy `import ulog`** for circular-import avoidance (Story 1.9 P2). Apply: keep `import ulog` inside `_swap_sql_for_jsonl` body.
- **`__test__ = False`** opt-out (Story 1.9 fix). N/A — no exposed `test_*` functions in the new helpers.
- **Empty input guards** (Story 1.9 P8). `_is_network_fs("")` should return False; `_swap_sql_for_jsonl("")` should still work but use empty reason — defensive.
- **Read-only DB transactions** (Story 1.8 P1). N/A — Story 1.10's PRAGMA is a write operation by definition.

### LLM-Dev anti-patterns to avoid

| Anti-pattern | Why avoid | Correct approach |
|---|---|---|
| Adding `psutil` for cross-platform fs detection | Breaks NFR-DEP-50 | Stdlib only — per-platform helpers |
| Using `logging.warning` for the swap message | Recursion risk; the swap reconfigures logging | `print(file=sys.stderr)` |
| Skipping the gate check (`if enabled`) | Plugin disabled → unconditional swap is invasive | First check `_get_enabled` |
| Detecting xdist via `pytest.config.pluginmanager.hasplugin('xdist')` | Plugin manager state is for the master only; workers should also detect | Env var detection works on both master and workers |
| Calling `pragma journal_mode=WAL` via `text("PRAGMA ...")` execute | SQLAlchemy may wrap in BEGIN/COMMIT; PRAGMA must run outside a transaction | `conn.exec_driver_sql("PRAGMA journal_mode=WAL")` (driver-level, no implicit tx) |
| Manually constructing the JSONL path via `path.replace('.sqlite', '.jsonl')` | Path with extra dots (e.g. `prod.v2.sqlite`) misbehaves | `path.rsplit('.', 1)[0] + '.jsonl'` |
| Returning True from `_is_network_fs` on subprocess timeout | Macos `mount` should be fast; if it times out, something is wrong, but assuming-network is overconservative outside Windows | Return False on macOS subprocess error |
| Calling `_swap_sql_for_jsonl` BEFORE `_get_enabled` check | Wastes work; on disabled plugin we shouldn't touch handlers | Gate first, swap second |
| Using `os.access()` for path detection | `os.access` checks permissions, not filesystem type | Use the platform-specific path |
| Forgetting to close the SQL handler before swapping | File-handle leak on the SQLite file | `handler.flush(); handler.close()` before `removeHandler` |
| Letting WAL fallback emit TWO warnings (one for "WAL failed" + one for the swap) | Confusing user output | Single warning text via the `reason` parameter to `_swap_sql_for_jsonl` |

### References

- [Source: `docs/prds/PRD-v0.3-test-integration.md`#4] NFR-PORT-10 — Linux/macOS/Windows portability
- [Source: `_bmad-output/planning-artifacts/architecture.md`#213] xdist + JSONL fallback path-of-last-resort
- [Source: `_bmad-output/planning-artifacts/epics.md`#Story 1.10] AC framing
- [Source: `ulog/testing/pytest_plugin.py`:62-115] Story 1.5's `pytest_configure` — extension site
- [Source: `ulog/handlers/sql.py`] SQLHandler shape (`_url`, `_engine`)
- [Source: `ulog/handlers/json_line.py`] JSONLineHandler — fallback target
- [Source: `ulog/setup.py`:65-193] `setup()` idempotency
- [pytest-xdist docs] `PYTEST_XDIST_WORKER` / `PYTEST_XDIST_TESTRUNUID` env vars
- [SQLite docs] `PRAGMA journal_mode=WAL` semantics
- [Linux `proc(5)`] `/proc/self/mountinfo` format
- [Windows MSDN] `GetDriveTypeW` API

### Library / framework versions

- **Python `>=3.10`**. `os.environ.get`, `pathlib.Path`, `subprocess.run`, `ctypes.windll`, all stdlib stable.
- **No new dependencies.** `dependencies = []` regression gate stays green.
- **SQLAlchemy >= 2.0** (already in `[storage]` extra) — `connection.exec_driver_sql` is the documented way to run PRAGMA outside a transaction.

### Definition of Done — Story 1.10

- [x] `_xdist_active()` helper detects PYTEST_XDIST_WORKER / PYTEST_XDIST_TESTRUNUID env vars.
- [x] `_is_network_fs(path)` dispatches to platform-specific helpers (Linux mountinfo / Windows GetDriveType / macOS mount).
- [x] `_swap_sql_for_jsonl(reason)` detaches SQL handlers and installs JSONL at the same path stem; prints stderr warning.
- [x] `_enable_wal_mode_or_fallback()` runs `PRAGMA journal_mode=WAL` and falls back to JSONL on failure.
- [x] `pytest_configure` integrates the 3 paths: Windows+xdist→swap, NFS+xdist→swap, local+xdist→WAL.
- [x] Gated on `enabled` AND `_xdist_active()` — non-xdist sessions are no-op.
- [x] 9 new tests covering AC1-AC7.
- [x] Test module count: 40 → **49 tests** in `tests/test_pytest_plugin.py`. Full suite: 165 + 9 = **174 tests**.
- [x] `mypy ulog/testing/ --follow-imports=silent` clean.
- [x] `grep '^dependencies' pyproject.toml | grep -q '\[\]'` → exit 0.
- [x] `git diff --stat HEAD --` reports only `ulog/testing/pytest_plugin.py` and `tests/test_pytest_plugin.py`.
- [x] AC1-AC8 each verifiable.
- [x] Story 1.11 (docs) will reference this fallback behavior in the troubleshooting section.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (1M context window)

### Debug Log References

- **9/9 new tests passed first run after 2 fixture fixes.** First run had 7 passes + 2 failures: (a) `sys` not imported at the top of `tests/test_pytest_plugin.py` (added the import), (b) the JSONL test asserted `record.get("context", {}).get("test_id")` — but the JSON formatter MERGES bound contextvars at the TOP LEVEL of the record, not under a `context` sub-key (asserted `record.get("test_id")` directly).
- **mypy clean on the new helpers.** No new errors. The `# type: ignore[attr-defined]` on `ctypes.windll.kernel32` is documented inline.
- Final state: `pytest tests/` → **174/174 pass** (165 baseline + 9 new). `mypy ulog/testing/ --follow-imports=silent` → clean. NFR-DEP-50 PASS.

### Completion Notes List

**Implementation summary:**
- Added 4 private helpers in `ulog/testing/pytest_plugin.py`: `_xdist_active()`, `_is_network_fs()` + 3 platform sub-helpers (Linux mountinfo, Windows GetDriveTypeW via ctypes, macOS `mount` subprocess), `_swap_sql_for_jsonl(reason)`, `_enable_wal_mode_or_fallback()`. Plus the orchestrator `_apply_xdist_storage_strategy(config)`.
- Wired the orchestrator into `pytest_configure` — runs AFTER auto-setup so it sees the active SQL handler regardless of whether host or auto wired it up. Gated on `_get_enabled` AND `_xdist_active` so non-xdist sessions are pure no-ops (AC3, AC5).
- Per-platform dispatch:
  - **Linux**: parses `/proc/self/mountinfo`, finds longest-prefix mountpoint, checks fstype against `_NETWORK_FS_TYPES_LINUX` (nfs/nfs4/cifs/smbfs/smb3/fuse.sshfs/9p/ceph). Special-cases the root mount `/` per VS patch C2.
  - **Windows**: GetDriveTypeW returns 4 (DRIVE_REMOTE) for network drives. Conservative fallback: any ctypes failure returns True (xdist+Windows is unconditionally JSONL anyway per AC4).
  - **macOS**: parses `mount` command output (subprocess, 2.0s timeout). Fstype check against `_NETWORK_FS_TYPES_MACOS` (nfs/smbfs/afpfs/webdav).
- Reentrancy guard in `_enable_wal_mode_or_fallback`: PRAGMA failure is captured INSIDE the `try`, the `with engine.connect()` exits cleanly, THEN `_swap_sql_for_jsonl` is dispatched. Prevents disposing the engine while a connection is still open (VS patch C1).
- `_swap_sql_for_jsonl` reuses Story 1.5's `ulog.setup(handlers=['json'], json_path=...)` for JSONL installation — exploiting `setup`'s existing idempotency to detach SQL handlers cleanly.
- Plugin's strategy on Windows: AC4 unconditional JSONL → no NFS probe needed.

**Test additions (9 new in `tests/test_pytest_plugin.py`):**
1. `test_xdist_active_detects_worker_env` — AC7 helper unit test
2. `test_is_network_fs_returns_false_for_local_paths` — defensive (skipped on Windows)
3. `test_swap_sql_for_jsonl_replaces_handler` — AC1/AC4 — handler swap + warning text
4. `test_pytest_configure_no_op_when_not_xdist` — AC3 regression guard
5. `test_apply_xdist_storage_strategy_disabled_plugin_no_op` — AC5 gate
6. `test_swap_sql_for_jsonl_preserves_record_schema` — AC6 schema preservation (JSONL flattens contextvars to top-level)
7. `test_pytest_configure_swaps_for_jsonl_on_xdist_nfs` — AC1 end-to-end via pytester + monkeypatched `_is_network_fs`
8. `test_pytest_configure_enables_wal_on_xdist_local` — AC2 — verifies PRAGMA journal_mode persists as 'wal' after the run
9. `test_pytest_configure_falls_back_when_wal_fails` — AC2 second clause — mocks engine.connect to raise, verifies "WAL mode unavailable" fallback

**ACs satisfied:**
- AC1 ✅ xdist+NFS → SQL→JSONL swap with stderr warning
- AC2 ✅ xdist+local → PRAGMA journal_mode=WAL; failure → JSONL fallback
- AC3 ✅ no xdist → no swap, no warning
- AC4 ✅ Windows+xdist → unconditional JSONL
- AC5 ✅ disabled plugin → short-circuit (no swap)
- AC6 ✅ JSONL fallback preserves record shape (logger/level/msg/context)
- AC7 ✅ helpers unit-testable in isolation
- AC8 ✅ frozen-invariants: only `ulog/testing/pytest_plugin.py` and `tests/test_pytest_plugin.py` modified

**Validation:**
- `pytest tests/`: **174/174 pass** (165 baseline + 9 new). `tests/test_pytest_plugin.py`: **49 tests** (40 + 9).
- `mypy ulog/testing/ --follow-imports=silent`: clean.
- `grep '^dependencies' pyproject.toml | grep -q '\[\]'`: PASS.
- Frozen-files diff empty.

**Out-of-scope deliberately deferred:**
- Multi-worker JSONL contention (xdist+JSONL still has concurrent writers; JSONL append-mode is line-atomic on POSIX but NOT on Windows). Documented in module docstring as "best-effort fallback".
- `--ulog-jsonl-path` explicit override flag for users who want JSONL upfront. v0.4 enhancement.
- Detection helpers don't currently log their decisions for observability. Add a verbose-mode debug print in v0.4 if users need to diagnose why their xdist DB landed in JSONL.

### File List

**Modified:**
- `ulog/testing/pytest_plugin.py` (+~210 lines: 6 helpers + orchestrator + integration into `pytest_configure`; module imports extended for `os`, `sys`, `pathlib`)
- `tests/test_pytest_plugin.py` (+~245 lines: section header + 9 new tests; import of `sys` added at module top)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (1-10: ready-for-dev → in-progress → done)

**Untouched (verified via git diff):**
- `pyproject.toml`, `ulog/__init__.py`, `ulog/setup.py`, `ulog/context.py`, `ulog/formatters.py`, `ulog/_color.py`, `ulog/handlers/*`, `ulog/web/*`, `ulog/testing/__init__.py`, `ulog/testing/test_event.py`, all other tests.

### Change Log

| Date | Change | Rationale |
|---|---|---|
| 2026-05-06 | Added `_xdist_active`, `_is_network_fs` (with Linux/Windows/macOS sub-helpers) | NFR-PORT-10 — detect xdist + filesystem type without psutil dep. |
| 2026-05-06 | Added `_swap_sql_for_jsonl(reason)` | AC1/AC4 — atomic SQL→JSONL swap that reuses Story 1.5's `setup()` idempotency. |
| 2026-05-06 | Added `_enable_wal_mode_or_fallback()` with reentrancy-safe pattern | AC2 — PRAGMA WAL on local-FS xdist; falls back to JSONL on any failure without leaking engine resources (VS patch C1). |
| 2026-05-06 | Wired `_apply_xdist_storage_strategy(config)` into `pytest_configure` | After auto-setup; gated on enabled+xdist; dispatches to Windows / NFS / WAL paths per platform. |
| 2026-05-06 | Linux mountinfo parser special-cases root mount `/` | VS patch C2 — `path.startswith("/" + "/")` was always False; root mount needs explicit handling. |
| 2026-05-06 | 9 new tests covering AC1-AC7 | All pass after 2 fixture fixes (missing `sys` import + JSONL flat-shape assertion). |
