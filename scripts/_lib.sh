#!/usr/bin/env bash
# Shared helpers for ulog dev scripts.
# Source from another script:
#   source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
#
# Provides:
#   require_cmd CMD HINT          — single command check + install hint
#   require_all_cmds ARRAY_NAME    — bulk check; iterates "cmd:hint" pairs
#   os_run LINUX MAC WIN [BSD]    — dispatch on uname -s, exec the right one
#   info / warn / err / ok  MSG    — log helpers (stderr, prefixed)
#   die MSG [EXIT]                 — print + exit
#
# All helpers return 0 on success, non-zero on failure. Scripts using
# `set -uo pipefail` (recommended) get the right behavior.

# ---- Logging ----

info() { printf '[info] %s\n' "$*" >&2; }
warn() { printf '[warn] %s\n' "$*" >&2; }
err()  { printf '[error] %s\n' "$*" >&2; }
ok()   { printf '[ok] %s\n' "$*" >&2; }

die() {
  local msg="$1" code="${2:-1}"
  err "$msg"
  exit "$code"
}

# ---- Command checks ----

# require_cmd CMD [HINT]
# Print [ok] if cmd in PATH; otherwise print [missing] + hint and return 1.
require_cmd() {
  local cmd="$1" hint="${2:-}"
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "$cmd: $(command -v "$cmd")"
    return 0
  fi
  warn "missing: $cmd"
  [ -n "$hint" ] && printf '         install: %s\n' "$hint" >&2
  return 1
}

# require_all_cmds DEP_LIST_NAME
# DEP_LIST_NAME is the name of a bash array of "cmd:hint" pairs.
# Returns the count of missing tools (0 = all present).
#
# Usage:
#   DEPS=(
#     "git:sudo apt install git"
#     "cargo:curl https://sh.rustup.rs | sh"
#   )
#   require_all_cmds DEPS || die "missing $? tool(s)"
require_all_cmds() {
  local -n _deps="$1"   # nameref (bash 4.3+)
  local missing=0 entry cmd hint
  for entry in "${_deps[@]}"; do
    cmd="${entry%%:*}"
    hint="${entry#*:}"
    require_cmd "$cmd" "$hint" || missing=$((missing + 1))
  done
  return "$missing"
}

# ---- OS dispatch ----

# os_run LINUX_CMD DARWIN_CMD WIN_CMD [BSD_CMD]
# Pick + execute the right command for the current OS.
# Each arg is a string evaluated via `eval`. Empty string = unsupported.
os_run() {
  local linux="${1:-}" darwin="${2:-}" win="${3:-}" bsd="${4:-}" cmd
  case "$(uname -s)" in
    Linux*)               cmd="$linux" ;;
    Darwin*)              cmd="$darwin" ;;
    MINGW*|CYGWIN*|MSYS*) cmd="$win" ;;
    *BSD)                 cmd="$bsd" ;;
    *)                    die "unsupported OS: $(uname -s)" ;;
  esac
  [ -z "$cmd" ] && die "no handler for $(uname -s) in this script"
  eval "$cmd"
}

# ---- Path helpers ----

# repo_root — absolute path of the project root (parent of scripts/)
repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}
