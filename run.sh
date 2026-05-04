#!/usr/bin/env bash
# ULog launcher — start the Django inspection UI on the prod or test
# log DB, run the test suite, generate demo logs, or wipe the cache.
#
# Usage:
#   ./run.sh                  # show menu
#   ./run.sh setup            # create .venv & install deps (uses uv if available)
#   ./run.sh prod             # ulog-web on ~/.cache/ulog/prod.sqlite
#   ./run.sh test             # ulog-web on ~/.cache/ulog/test.sqlite
#   ./run.sh dev              # run pytest (writes to test profile)
#   ./run.sh demo             # generate sample prod logs
#   ./run.sh clean            # rm -f the prod + test DBs
#   ./run.sh help             # this message
#
# Pass extra args after the subcommand — forwarded to the underlying
# tool (ulog-web/pytest/etc.):
#   ./run.sh prod --port 9000 --no-open
#   ./run.sh dev -k profile

set -euo pipefail

# ---- Resolve paths -------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/ulog"
PROD_DB="$CACHE_DIR/prod.sqlite"
TEST_DB="$CACHE_DIR/test.sqlite"

# Pick a python: prefer a project venv. We sniff a few common
# locations (`.venv` next to this script, or under a parent project
# that vendored ulog as a submodule). The system python3 is the last
# resort and may lack sqlalchemy/django — see the deps check below.
PY=""
for cand in \
    "$SCRIPT_DIR/.venv/bin/python" \
    "$SCRIPT_DIR/.venv-spike/bin/python" \
    "$SCRIPT_DIR/../.venv/bin/python" \
    "$SCRIPT_DIR/../../.venv/bin/python" \
    "$SCRIPT_DIR/../../.venv-spike/bin/python" \
    "$(command -v python3 || true)"; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
    echo "ulog-run: no python interpreter found" >&2
    exit 127
fi

# Sanity-check the picked python has the deps the subcommand needs.
# Strategy: ONE python invocation that tries to import every required
# module and prints the missing names. O(1) startup, ~34ms total — beats
# pip list (~165ms) and per-dep `python -c` calls (~240ms for three).
# Respects PYTHONPATH/cwd, so a source-tree `ulog` (not pip-installed)
# is correctly seen as present.
declare -A REQUIRED_MODULES=()
declare -A REQUIRE_HINTS=()

require_module() {
    local mod="$1" hint="$2"
    REQUIRED_MODULES["$mod"]=1
    REQUIRE_HINTS["$mod"]="$hint"
}

check_required_modules() {
    [ ${#REQUIRED_MODULES[@]} -eq 0 ] && return
    local mods="${!REQUIRED_MODULES[*]}"
    local missing
    missing="$("$PY" - <<PYEOF
import sys
missing = []
for m in "$mods".split():
    try:
        __import__(m)
    except ImportError:
        missing.append(m)
print(" ".join(missing))
PYEOF
)"
    [ -z "$missing" ] && return
    local m
    for m in $missing; do
        echo "ulog-run: $(c_r "missing dependency"): $m" >&2
        echo "  ${REQUIRE_HINTS[$m]}" >&2
    done
    echo "  Or set up a project venv:" >&2
    echo "    python3 -m venv .venv && .venv/bin/pip install -e \".[storage,web,dev]\"" >&2
    echo "    pip install -e ./vendor/ucolor-python  # if cloned --recursive" >&2
    exit 127
}

# Resolve `ulog-web` and `pytest` from the same env as $PY when possible.
PY_BIN_DIR="$(dirname "$PY")"
ULOG_WEB="$PY_BIN_DIR/ulog-web"
[ -x "$ULOG_WEB" ] || ULOG_WEB="$(command -v ulog-web || true)"
PYTEST="$PY_BIN_DIR/pytest"
[ -x "$PYTEST" ] || PYTEST="$(command -v pytest || true)"

# ---- Helpers -------------------------------------------------------------

c_b()  { printf '\033[1m%s\033[0m'   "$*"; }
c_g()  { printf '\033[32m%s\033[0m'  "$*"; }
c_y()  { printf '\033[33m%s\033[0m'  "$*"; }
c_r()  { printf '\033[31m%s\033[0m'  "$*"; }

usage() {
    cat <<EOF
$(c_b "ULog launcher")

  $(c_b "./run.sh setup")      Create $(c_g ".venv") and install ULog + extras (uv-aware)
  $(c_b "./run.sh prod")       Open the Django UI on $(c_g "~/.cache/ulog/prod.sqlite")
  $(c_b "./run.sh test")       Open the Django UI on $(c_y "~/.cache/ulog/test.sqlite")
  $(c_b "./run.sh dev")        Run the test suite (logs land in the test profile)
  $(c_b "./run.sh demo")       Generate sample prod logs
  $(c_b "./run.sh clean")      Wipe the prod + test SQLite DBs
  $(c_b "./run.sh help")       Show this message

Profiles are baked into ulog.setup(profile=...). 'auto' resolves
to 'test' when pytest is running, 'prod' otherwise — used by the
demo subcommand.

Pass extra args after the subcommand — they're forwarded to the
underlying tool (ulog-web / pytest / python).

Examples:
  ./run.sh prod --port 9000 --no-open
  ./run.sh test --port 9001
  ./run.sh dev -k profile -v
EOF
}

ensure_db_or_warn() {
    local db="$1"
    local profile="$2"
    if [ ! -f "$db" ]; then
        echo "ulog-run: $(c_y "$db not found")" >&2
        echo "  Generate one first:" >&2
        echo "    ./run.sh demo               # creates a prod fixture" >&2
        echo "    ./run.sh dev                # populates the test fixture" >&2
        echo "  Or point your app's ulog.setup(profile='$profile') at the same path." >&2
        exit 1
    fi
}

# ---- Subcommands ---------------------------------------------------------

cmd_prod() {
    require_module "ulog" "pip install -e ."
    require_module "django" "pip install -e \".[web]\""
    require_module "sqlalchemy" "pip install -e \".[storage]\""
    check_required_modules
    [ -x "$ULOG_WEB" ] || { echo "ulog-run: ulog-web not on PATH (install with pip install -e \".[web]\")" >&2; exit 127; }
    ensure_db_or_warn "$PROD_DB" "prod"
    echo "$(c_g '→ serving prod logs') $(c_b "$PROD_DB")"
    exec "$ULOG_WEB" "$PROD_DB" "$@"
}

cmd_test() {
    require_module "ulog" "pip install -e ."
    require_module "django" "pip install -e \".[web]\""
    require_module "sqlalchemy" "pip install -e \".[storage]\""
    check_required_modules
    [ -x "$ULOG_WEB" ] || { echo "ulog-run: ulog-web not on PATH (install with pip install -e \".[web]\")" >&2; exit 127; }
    ensure_db_or_warn "$TEST_DB" "test"
    echo "$(c_y '→ serving test logs') $(c_b "$TEST_DB")"
    exec "$ULOG_WEB" "$TEST_DB" "$@"
}

cmd_dev() {
    require_module "pytest" "pip install -e \".[dev]\""
    check_required_modules
    [ -x "$PYTEST" ] || { echo "ulog-run: pytest not on PATH (install with pip install -e \".[dev]\")" >&2; exit 127; }
    echo "$(c_y '→ running pytest') (tests writing to the test profile when they opt in)"
    cd "$SCRIPT_DIR"
    exec "$PYTEST" "$@"
}

cmd_demo() {
    require_module "ulog" "pip install -e ."
    require_module "sqlalchemy" "pip install -e \".[storage]\""
    check_required_modules
    mkdir -p "$CACHE_DIR"
    echo "$(c_g '→ generating sample logs in') $(c_b "$PROD_DB")"
    "$PY" - <<'PYEOF'
import logging
import ulog

ulog.setup(profile="prod", color="never")

ulog.bind(session_id="demo", user="developer")

ulog.get_logger("demo.boot").info("application starting up")
ulog.get_logger("demo.api").info("user landed on /home")

with ulog.context(request_id="abc-001"):
    ulog.get_logger("demo.api").info("processing request")
    ulog.get_logger("demo.db").info("query executed in 4ms")

ulog.get_logger("demo.api").warning(
    "rate limit approaching",
    extra={"remaining": 12, "window_s": 60},
)

try:
    raise ValueError("simulated upstream timeout")
except ValueError:
    ulog.get_logger("demo.upstream").exception(
        "upstream call failed",
        extra={"endpoint": "/v1/widgets", "retry": 3},
    )

ulog.get_logger("demo.audit").error(
    "permission denied",
    extra={"user_id": 42, "resource": "/admin"},
)

# Force flush the SQLHandler so the file is visible.
for h in logging.getLogger().handlers:
    h.flush()
print("ulog-run: 7 demo records written")
PYEOF
    echo "$(c_g '✓ done') — open the UI with $(c_b './run.sh prod')"
}

cmd_setup() {
    cd "$SCRIPT_DIR"
    local has_uv=0
    command -v uv >/dev/null 2>&1 && has_uv=1

    if [ -d .venv ]; then
        echo "$(c_y '→ .venv already exists') (skipping creation; pass --force to recreate)"
        if [ "${1:-}" = "--force" ]; then
            echo "$(c_y '  removing existing .venv')"
            rm -rf .venv
        fi
    fi

    if [ ! -d .venv ]; then
        if [ "$has_uv" -eq 1 ]; then
            echo "$(c_g '→ creating venv with') $(c_b uv) ($(uv --version))"
            uv venv .venv
        else
            echo "$(c_y '→ uv not found, using stdlib') $(c_b 'python3 -m venv')"
            python3 -m venv .venv
            .venv/bin/pip install --upgrade --quiet pip
        fi
    fi

    echo "$(c_g '→ installing') ulog$(c_b '[storage,web,dev]')"
    if [ "$has_uv" -eq 1 ]; then
        VIRTUAL_ENV="$SCRIPT_DIR/.venv" uv pip install -e ".[storage,web,dev]"
    else
        .venv/bin/pip install -e ".[storage,web,dev]"
    fi

    # Install vendored ucolor if the submodule was checked out — keeps
    # CLI colour formatting working out of the box.
    if [ -f vendor/ucolor-python/pyproject.toml ]; then
        echo "$(c_g '→ installing') $(c_b 'vendored ucolor')"
        if [ "$has_uv" -eq 1 ]; then
            VIRTUAL_ENV="$SCRIPT_DIR/.venv" uv pip install -e vendor/ucolor-python
        else
            .venv/bin/pip install -e vendor/ucolor-python
        fi
    fi

    echo "$(c_g '✓ setup complete') — try: $(c_b './run.sh demo') then $(c_b './run.sh prod')"
}

cmd_clean() {
    if [ -d "$CACHE_DIR" ]; then
        rm -f "$PROD_DB" "$TEST_DB"
        echo "$(c_g '✓ removed') $PROD_DB $TEST_DB"
    else
        echo "ulog-run: nothing to clean ($CACHE_DIR doesn't exist)"
    fi
}

# ---- Dispatch ------------------------------------------------------------

if [ $# -eq 0 ]; then
    usage
    exit 0
fi

cmd="$1"; shift
case "$cmd" in
    setup)      cmd_setup "$@" ;;
    prod)       cmd_prod  "$@" ;;
    test)       cmd_test  "$@" ;;
    dev|pytest) cmd_dev   "$@" ;;
    demo)       cmd_demo ;;
    clean)      cmd_clean ;;
    help|--help|-h) usage ;;
    *)          echo "ulog-run: unknown subcommand '$cmd'" >&2; usage; exit 64 ;;
esac
