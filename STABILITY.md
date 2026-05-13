# Stability contract

What ulog promises to never break, from v0.5 onward, with rationale.

The seven invariants below are **part of the public API contract**.
Any future change that violates one of them is a major-version bump
(`v1.0` at earliest) and ships with explicit migration notes.

---

## I1 — Auto-class

> Every record is auto-classified `level` / `logger` / `file` / `line`
> from the stdlib `LogRecord`. No manual tagging required.

**Rationale.** The stdlib `logging` module already captures these
fields. Forcing the user to re-state them on every call (à la a
proprietary structured logger) wastes keystrokes and creates drift.
ulog reads them straight off `record.__dict__` — what you log is
what gets stored.

## I2 — Local-first

> Zero network calls from the core. Everything lives in one SQLite
> file (or JSONL / CSV).

**Rationale.** Forensic log archives shouldn't depend on cloud
availability. A SQLite file is the storage primitive of choice for
single-host, single-process, and even multi-host (via shared FS) use
cases. ulog's core ships zero PyPI runtime deps; opt-in extras gate
every network-touching feature (e.g. v0.15 community solutions site
behind explicit per-record consent).

## I3 — Verify-offline

> `ulog verify <db>` works fully offline, reads only the local DB,
> exits with deterministic codes.

**Rationale.** Integrity verification that depends on a remote
attestation service is no integrity verification — it just shifts
the trust boundary. ulog's chain is verifiable from the SQLite file
alone. Exit codes are documented (0 = OK, 1 = BROKEN, 2 = error)
so CI gates are predictable.

## I4 — Immutable-hard

> Rows past `min_retention_days` cannot be UPDATE'd or DELETE'd via
> SQL — a trigger enforces it at the DB level.

**Rationale.** "Immutable" enforced only in application code is
trivially bypassable (open with `sqlite3`, run an UPDATE). Putting
the immutability constraint inside a SQL trigger makes it hold even
under direct DB access. Bypassing it requires explicitly dropping
the trigger — a visible, audited act.

## I5 — Stdlib-compat

> `logging.getLogger(__name__).info("x")` continues to work
> byte-identical to v0.1 forever.

**Rationale.** ulog never installs a parallel logger hierarchy. Code
that already uses the stdlib doesn't need rewriting — it just inherits
ulog's formatting + storage when `ulog.setup()` is called. The
byte-stable contract is enforced by `tests/test_qlnes_compat.py`
(Story 7.8): the test asserts the exact `qlnes` formatter output is
identical to the v0.1 baseline byte sequence. Any future change
breaking it fails CI immediately.

## I6 — Untagged-works

> Code that has never called `ulog.setup()` still emits cleanly via
> the stdlib defaults.

**Rationale.** ulog is opt-in. A library can `import ulog` and call
`ulog.get_logger(__name__)` without forcing its callers to configure
anything. If no caller invokes `setup()`, the standard `logging`
defaults apply (stderr, WARNING+ level, simple format). Adding a
"must call setup() first" requirement would make ulog viral instead
of additive.

## I7 — No-phone-home

> ulog itself never contacts the network. Opt-in features that
> may contact the network gate every call behind explicit consent.

**Rationale.** The library is for log archives, including audit
logs in regulated environments. Any background telemetry / version
check / signature lookup would compromise that posture for every
user including the ones who don't want it. The v0.15+ community
solutions endpoint is the only network-touching feature on the
roadmap, and it is gated behind a **per-record consent dialog**
(see PRD-v0.16). No `setup()` flag toggles "always send" without
a banner-warned mode that documents the trade-off in the UI.

---

## Contract scope

These invariants are guaranteed:

- **Core** (`ulog.setup`, `ulog.get_logger`, the 4 built-in formatters,
  contextvar binding) — all v0.5+ behaviour byte-stable.
- **Storage handlers** (`SQLHandler`, `JSONLineHandler`, `CSVHandler`)
  — schema additive only.
- **Chain integrity** (the v0.5 hash-chain) — record-hash formula is
  frozen; downstream tools relying on `record_hash` won't break.
- **`ulog` CLI** — subcommands listed in v0.5 are stable; new ones
  can be added; existing ones don't get breaking flag removals
  within a minor version.

These are **not** under the I-contract :

- **Web UI** (`ulog web`) — layout, copy, sidebar order may change
  freely between minor versions. Bookmarked URLs stay stable.
- **PRDs in `docs/prds/`** — speculative, may be merged / abandoned.
- **Pre-1.0 minor versions** can still surprise — the contract
  hardens at v1.0. Until then, RELEASE_NOTES.md flags any deviation.

---

## Where this is enforced

| Invariant | Enforced by |
|---|---|
| I1 | `_RESERVED` set + `JsonFormatter._extra_to_payload` (covered by `tests/test_formatters.py`). |
| I2 | CI gate `regression-gate-zero-deps` greps `pyproject.toml` for `dependencies = []` (Story 7.9). |
| I3 | `tests/test_cli_verify.py` — `ulog verify` works on a stale DB with no network. |
| I4 | `tests/test_chain.py` + SQL trigger fired by `setup(integrity='hash-chain', min_retention_days=N)`. |
| I5 | `tests/test_qlnes_compat.py` — byte-stable assertion (Story 7.8). |
| I6 | `tests/test_setup.py::test_stdlib_default_works_without_setup`. |
| I7 | `grep -RE 'urllib|requests|httpx' ulog/` returns nothing in core (only in opt-in extras). |
