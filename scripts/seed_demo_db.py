"""Seed a realistic demo log DB simulating a multi-tenant SaaS platform.

Run:
    python3 scripts/seed_demo_db.py /tmp/ulog-demo

Produces:
    /tmp/ulog-demo/                # git repo with 30 source files, 8 committers
    /tmp/ulog-demo/logs.sqlite     # ~50k log records spanning ~7 days
    /tmp/ulog-demo/logs.sqlite     # also contains the populated `authors` cache

Then:
    ulog-web --repo /tmp/ulog-demo /tmp/ulog-demo/logs.sqlite
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

# ---- Synthetic team -----------------------------------------------------

AUTHORS = [
    ("Alice Chen",      "alice@globex.io"),
    ("Bob Martin",      "bob@globex.io"),
    ("Charlie Patel",   "charlie@globex.io"),
    ("Dana Wong",       "dana@globex.io"),
    ("Erwin Schmidt",   "erwin@globex.io"),
    ("Fatima Khouri",   "fatima@globex.io"),
    ("Gao Li",          "gao@globex.io"),
    ("Hiroshi Sato",    "hiroshi@globex.io"),
]

# ---- Synthetic codebase: 30 files across 8 services --------------------
# Distribution: a few hot files (payments/checkout), many cooler files.

SERVICES = {
    "payments":       ["checkout.py", "stripe_adapter.py", "refund.py", "webhook.py", "tax.py"],
    "billing":        ["invoice.py", "subscription.py", "trial.py", "dunning.py"],
    "auth":           ["login.py", "session.py", "oauth.py", "rbac.py"],
    "search":         ["index.py", "ranker.py", "facets.py"],
    "notifications":  ["email.py", "sms.py", "push.py"],
    "analytics":      ["events.py", "funnel.py", "rollup.py"],
    "recommendations":["model.py", "features.py"],
    "shared":         ["config.py", "db.py", "cache.py", "metrics.py"],
}

# logger / sector for each service (3-letter prefix for visual grouping)
LOGGER_PREFIXES = {svc: f"globex.{svc}" for svc in SERVICES}

# ---- Distributions -----------------------------------------------------

LEVEL_WEIGHTS = [
    ("DEBUG",    25),
    ("INFO",     58),
    ("WARNING",  10),
    ("ERROR",     6),
    ("CRITICAL",  1),
]

OUTCOME_WEIGHTS = [
    ("passed",    85),
    ("failed",     8),
    ("skipped",    4),
    ("errored",    3),
]

# Sample messages per level (real-feeling, not lorem ipsum)
MESSAGES_BY_LEVEL = {
    "DEBUG":    [
        "cache miss for key=%s",
        "issuing query: %s",
        "decoding payload (%d bytes)",
        "rotating buffer at watermark",
        "connection acquired from pool",
        "scheduled retry in %dms",
    ],
    "INFO":     [
        "user %s authenticated",
        "checkout session %s started",
        "invoice %s issued",
        "webhook %s delivered",
        "search served %d hits in %dms",
        "notification queued for %s",
        "subscription renewed for tenant %s",
        "campaign %s computed reach=%d",
    ],
    "WARNING":  [
        "rate limit reached for tenant %s",
        "stripe retry triggered (attempt %d)",
        "slow query: %dms",
        "cache pool saturation %.1f%%",
        "deprecated endpoint %s used",
        "low free credits for tenant %s",
    ],
    "ERROR":    [
        "checkout failed: %s",
        "webhook signature mismatch from %s",
        "invoice generation failed: %s",
        "rbac denied: %s on %s",
        "search backend unreachable",
        "feature flag fetch failed",
    ],
    "CRITICAL": [
        "DB primary unreachable",
        "payment processor down",
        "auth provider returning 5xx",
    ],
}

# ---- Repo bootstrap -----------------------------------------------------

def _git(*args, cwd: Path, capture: bool = True) -> str:
    """Run a git command, optionally capturing output."""
    if capture:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
        return out.stdout
    subprocess.run(["git", *args], cwd=cwd, check=True)
    return ""


def _commit(cwd: Path, msg: str, name: str, email: str) -> None:
    env = {**os.environ,
           "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    subprocess.run(
        ["git", "commit", "-q", "-m", msg],
        cwd=cwd, env=env, check=True, capture_output=True,
    )


def build_repo(repo_path: Path) -> dict[str, str]:
    """Build a git repo with the synthetic codebase. Returns {file_basename: ...}.

    Each file is 200-500 lines of fake code so blame line ranges have headroom.
    Each file is committed by 1-2 authors (some files get a "later" change).
    """
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True)

    _git("init", "-q", "-b", "main", cwd=repo_path)
    _git("config", "user.name", "init", cwd=repo_path)
    _git("config", "user.email", "init@globex.io", cwd=repo_path)
    _git("config", "commit.gpgsign", "false", cwd=repo_path)

    file_to_lines: dict[str, int] = {}
    files_total: list[Path] = []

    # First pass: create all files with random length, by random initial author.
    for service, files in SERVICES.items():
        svc_dir = repo_path / service
        svc_dir.mkdir(exist_ok=True)
        for fname in files:
            n_lines = random.randint(200, 500)
            content = "\n".join([
                f"# {fname} — synthetic source line {i}"
                for i in range(1, n_lines + 1)
            ]) + "\n"
            (svc_dir / fname).write_text(content, encoding="utf-8")
            files_total.append(svc_dir / fname)
            # Use BASENAME to match record.file convention (Python logging's filename).
            file_to_lines[fname] = n_lines

    _git("add", ".", cwd=repo_path)
    initial_author = random.choice(AUTHORS)
    _commit(repo_path, "feat: initial scaffold", *initial_author)

    # Second pass: each author touches a subset of files (later commits).
    # Distributes blame so multiple authors share files.
    files_by_author: dict[tuple[str, str], list[Path]] = {a: [] for a in AUTHORS}
    for f in files_total:
        # 1 to 2 additional authors will modify this file
        modifiers = random.sample(AUTHORS, random.randint(1, 2))
        for m in modifiers:
            files_by_author[m].append(f)

    for author, owned in files_by_author.items():
        if not owned:
            continue
        # Pick a random subset to modify in this author's commit.
        to_modify = random.sample(owned, max(1, len(owned) // 2))
        for f in to_modify:
            content = f.read_text(encoding="utf-8").splitlines()
            # Modify a random middle range to simulate evolution.
            target = random.randint(50, max(50, len(content) - 50))
            content[target] = f"# CHANGED by {author[0]}: {f.name}"
            f.write_text("\n".join(content) + "\n", encoding="utf-8")
        _git("add", ".", cwd=repo_path)
        _commit(repo_path, f"fix: tweaks in {len(to_modify)} files", *author)

    return file_to_lines


# ---- Log generation -----------------------------------------------------

def generate_log_db(
    db_path: Path,
    *,
    n_records: int,
    file_to_lines: dict[str, int],
    n_test_files: int = 10,
    tests_per_file: int = 50,
) -> None:
    """Bulk-insert n_records into a freshly created SQLite DB matching the
    ULog schema (ulog/handlers/sql.py)."""
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE logs (
            id INTEGER NOT NULL PRIMARY KEY,
            ts DATETIME NOT NULL,
            level VARCHAR(10) NOT NULL,
            logger VARCHAR(255) NOT NULL,
            msg TEXT NOT NULL,
            file VARCHAR(255) NOT NULL,
            line INTEGER NOT NULL,
            exc JSON,
            context JSON
        )
    """)
    conn.execute("CREATE INDEX ix_logs_ts ON logs(ts)")
    conn.execute("CREATE INDEX ix_logs_level ON logs(level)")
    conn.execute("CREATE INDEX ix_logs_logger ON logs(logger)")
    conn.execute("CREATE INDEX ix_logs_file ON logs(file)")

    levels = [lv for lv, _ in LEVEL_WEIGHTS]
    level_w = [w for _, w in LEVEL_WEIGHTS]
    outcomes = [o for o, _ in OUTCOME_WEIGHTS]
    outcome_w = [w for _, w in OUTCOME_WEIGHTS]

    files = list(file_to_lines.keys())
    services = list(SERVICES.keys())
    file_to_service = {fn: svc for svc, fns in SERVICES.items() for fn in fns}

    # Time window: last 7 days.
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    span_seconds = (end - start).total_seconds()

    # Bias: 80% of records hit 20% hot files (Pareto)
    hot_files = random.sample(files, max(1, len(files) // 5))

    # Tenants/users for context
    tenants = [f"tenant_{i:03d}" for i in range(50)]
    users   = [f"user_{i:04d}"   for i in range(500)]

    rows: list[tuple] = []

    # ---- App records (FR-style logs) ---------------------------------
    n_app = int(n_records * 0.85)  # 85% app records, 15% test events
    for i in range(n_app):
        # File pick (Pareto-ish)
        if random.random() < 0.8:
            fname = random.choice(hot_files)
        else:
            fname = random.choice(files)
        max_line = file_to_lines[fname]
        line = random.randint(1, max_line)
        svc = file_to_service[fname]
        logger = LOGGER_PREFIXES[svc]
        # Add a sub-logger sometimes
        if random.random() < 0.3:
            logger = f"{logger}.{random.choice(['handler', 'worker', 'scheduler', 'admin'])}"

        level = random.choices(levels, weights=level_w, k=1)[0]
        msg_template = random.choice(MESSAGES_BY_LEVEL[level])
        # Fill placeholders with plausible values
        try:
            if "%s" in msg_template and "%d" in msg_template:
                msg = msg_template % (random.choice(users), random.randint(10, 500))
            elif "%d" in msg_template:
                msg = msg_template % (random.randint(1, 9999),)
            elif "%s" in msg_template:
                msg = msg_template % (random.choice(users),)
            elif "%.1f" in msg_template:
                msg = msg_template % (random.uniform(60, 99),)
            else:
                msg = msg_template
        except TypeError:
            msg = msg_template

        ts_offset = random.uniform(0, span_seconds)
        ts = (start + timedelta(seconds=ts_offset)).isoformat()

        # Bound context — most records carry tenant + request_id
        ctx: dict = {}
        if random.random() < 0.7:
            ctx["tenant_id"] = random.choice(tenants)
        if random.random() < 0.85:
            ctx["request_id"] = f"req_{random.randint(10**8, 10**9 - 1):x}"
        if random.random() < 0.4:
            ctx["user_id"] = random.choice(users)
        if random.random() < 0.1:
            ctx["region"] = random.choice(["us-east-1", "eu-west-1", "ap-southeast-1"])

        # Synthetic operation duration — Pareto-ish: 80% fast (1-50ms),
        # 18% medium (50-200ms), 2% slow (200ms-2s). Lets the viewer
        # "Time" column show realistic variance.
        r = random.random()
        if r < 0.80:
            duration_s = random.uniform(0.001, 0.05)
        elif r < 0.98:
            duration_s = random.uniform(0.05, 0.2)
        else:
            duration_s = random.uniform(0.2, 2.0)
        ctx["duration_s"] = round(duration_s, 6)

        # Some ERROR records carry an exception
        exc = None
        if level == "ERROR" and random.random() < 0.5:
            exc_types = ["ValueError", "RuntimeError", "ConnectionError", "TimeoutError", "KeyError"]
            exc_type = random.choice(exc_types)
            exc = {
                "type": exc_type,
                "msg": f"{exc_type.lower()}: synthetic failure {random.randint(1000, 9999)}",
                "tb": [
                    f'  File "{svc}/{fname}", line {line}, in handler',
                    f'    raise {exc_type}("synthetic failure")',
                    f"{exc_type}: synthetic failure",
                ],
            }

        rows.append((
            ts, level, logger, msg, fname, line,
            json.dumps(exc) if exc else None,
            json.dumps(ctx) if ctx else None,
        ))

    # ---- Test events (Story 1.2/1.5 shape) --------------------------
    # Mimic the pytest plugin's records: started + outcome (+ optional ERROR).
    test_files = random.sample(files, min(n_test_files, len(files)))
    test_logger = "ulog.test"
    for tf in test_files:
        for ti in range(tests_per_file):
            test_id = f"tests/{tf}::test_{tf.replace('.py','')}_{ti:03d}"
            outcome = random.choices(outcomes, weights=outcome_w, k=1)[0]
            duration = round(random.uniform(0.0001, 4.5), 6)

            ts_offset = random.uniform(0, span_seconds)
            base_ts = start + timedelta(seconds=ts_offset)

            # `test started` record (line 183 to match real plugin source)
            started_ctx = {"test_id": test_id, "phase": "setup"}
            rows.append((
                base_ts.isoformat(), "INFO", test_logger, "test started",
                "pytest_plugin.py", 183,
                None, json.dumps(started_ctx),
            ))

            # outcome record (line 281 for passed, line 211 for traceback)
            outcome_ts = (base_ts + timedelta(seconds=duration)).isoformat()
            outcome_ctx = {
                "test_id": test_id,
                "outcome": outcome,
                "duration_s": duration,
                "phase": "call",
            }
            rows.append((
                outcome_ts,
                "INFO" if outcome in ("passed", "skipped") else "ERROR",
                test_logger,
                f"test {outcome}",
                "pytest_plugin.py", 281 if outcome == "passed" else 211,
                None, json.dumps(outcome_ctx),
            ))

            # Optional traceback record for failed/errored
            if outcome in ("failed", "errored"):
                exc_types = ["AssertionError", "ValueError", "RuntimeError"]
                exc_type = random.choice(exc_types)
                exc = {
                    "type": exc_type,
                    "msg": f"test {outcome}: {random.choice(['expected 42, got 41', 'broken precondition', 'mock not called'])}",
                    "tb": [
                        f'  File "tests/{tf}", line {random.randint(10, 80)}, in test_body',
                        f'    assert result == expected',
                        f"{exc_type}: synthetic test failure",
                    ],
                }
                rows.append((
                    outcome_ts, "ERROR", test_logger, "traceback",
                    "pytest_plugin.py", 211,
                    json.dumps(exc), json.dumps({"test_id": test_id}),
                ))

    # Sort by timestamp before insert so id ordering ≈ chronological.
    rows.sort(key=lambda r: r[0])

    print(f"inserting {len(rows)} records...", file=sys.stderr)
    conn.executemany(
        "INSERT INTO logs (ts, level, logger, msg, file, line, exc, context) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    print(f"wrote {db_path}", file=sys.stderr)


# ---- Entrypoint ---------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "out_dir", type=Path,
        help="Output directory (will be CLEARED). Recommended: /tmp/ulog-demo",
    )
    parser.add_argument(
        "--records", type=int, default=50_000,
        help="Number of app records to generate (default: 50000)",
    )
    parser.add_argument(
        "--test-files", type=int, default=10, help="Number of test files (default: 10)",
    )
    parser.add_argument(
        "--tests-per-file", type=int, default=50,
        help="Number of tests per file (default: 50). Total test events = files × tests × ~2.2 records.",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Building synthetic git repo at {out_dir} ===", file=sys.stderr)
    file_to_lines = build_repo(out_dir)
    print(f"  {len(file_to_lines)} source files, "
          f"{len(AUTHORS)} authors, "
          f"{sum(file_to_lines.values())} total lines",
          file=sys.stderr)

    db = out_dir / "logs.sqlite"
    print(f"=== Generating log DB at {db} ===", file=sys.stderr)
    generate_log_db(
        db,
        n_records=args.records,
        file_to_lines=file_to_lines,
        n_test_files=args.test_files,
        tests_per_file=args.tests_per_file,
    )

    print("\n=== Done. Run the viewer with: ===", file=sys.stderr)
    print(f"  ulog-web --repo {out_dir} {db}", file=sys.stderr)
    print("\nFirst launch will run the author indexer (≤5s budget for ~30 files).", file=sys.stderr)
    print("Subsequent launches reuse the cached `authors` table for instant startup.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
