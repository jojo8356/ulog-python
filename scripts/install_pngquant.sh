#!/usr/bin/env bash
# Ensure pngquant is available, cross-platform, no sudo required.
#
# Strategy:
#   1. If pngquant is already in PATH         → done
#   2. If tools/bin/pngquant already exists   → done
#   3. Build from source via Cargo (Linux/Mac) or download prebuilt (Windows)
#
# pngquant >= 3.0 uses Cargo. Cargo must be installed (https://rustup.rs).
# The compiled binary lands in tools/bin/pngquant (gitignored).

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_ROOT/scripts/_lib.sh"

TOOLS_BIN="$PROJECT_ROOT/tools/bin"
LOCAL_PNGQUANT="$TOOLS_BIN/pngquant"

# 1. Already in PATH
if command -v pngquant >/dev/null 2>&1; then
  ok "pngquant already in PATH: $(command -v pngquant) ($(pngquant --version 2>&1 | head -1))"
  exit 0
fi

# 2. Already in tools/bin
if [ -x "$LOCAL_PNGQUANT" ] || [ -x "$LOCAL_PNGQUANT.exe" ]; then
  ok "pngquant already in tools/bin/"
  info "Add to PATH: export PATH=\"$TOOLS_BIN:\$PATH\""
  exit 0
fi

mkdir -p "$TOOLS_BIN"
info "pngquant not found. Building locally to $LOCAL_PNGQUANT"

# ---- Strategy: Cargo build (Linux + Mac) ----

build_with_cargo() {
  # Bulk-check required tools — one entry per tool, with install hint.
  local DEPS=(
    "git:sudo apt install git  |  brew install git  |  xcode-select --install"
    "cargo:curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && source \$HOME/.cargo/env"
  )
  if ! require_all_cmds DEPS; then
    return 1
  fi

  info "git $(git --version | awk '{print $3}') + cargo $(cargo --version | awk '{print $2}')"

  local src_dir
  src_dir="$(mktemp -d)"
  trap 'rm -rf "$src_dir"' RETURN

  info "Cloning kornelski/pngquant"
  git clone --depth=1 --recurse-submodules \
    https://github.com/kornelski/pngquant.git "$src_dir" >/dev/null 2>&1 \
    || die "git clone failed (network? GitHub unreachable?)"

  info "cargo build --release (1-3 min the first time)"
  ( cd "$src_dir" && cargo build --release ) \
    || die "cargo build failed — run 'cd $src_dir && cargo build --release' for details"

  local built
  if   [ -x "$src_dir/target/release/pngquant" ];     then built="$src_dir/target/release/pngquant"
  elif [ -x "$src_dir/target/release/pngquant.exe" ]; then built="$src_dir/target/release/pngquant.exe"
  else die "cargo build succeeded but binary missing in target/release/"
  fi
  cp "$built" "$LOCAL_PNGQUANT" && chmod +x "$LOCAL_PNGQUANT"
}

# ---- Strategy: Windows prebuilt ----

download_windows_release() {
  info "Downloading pngquant for Windows from pngquant.org"
  local url="https://pngquant.org/pngquant-windows.zip"
  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  curl -fsSL "$url" -o "$tmp/pngquant.zip" || die "curl failed"
  unzip -q "$tmp/pngquant.zip" -d "$tmp"   || die "unzip failed"

  local exe
  exe="$(find "$tmp" -name 'pngquant.exe' -print -quit)"
  [ -n "$exe" ] || die "pngquant.exe not found in zip"
  cp "$exe" "$LOCAL_PNGQUANT.exe"
}

# ---- Dispatch on OS — single line, no nested ifs ----

os_run \
  "build_with_cargo" \
  "build_with_cargo" \
  "download_windows_release || build_with_cargo"

# Final verification
if [ -x "$LOCAL_PNGQUANT" ] || [ -x "$LOCAL_PNGQUANT.exe" ]; then
  ok "pngquant installed to $LOCAL_PNGQUANT"
  info "Add to PATH for this shell: export PATH=\"$TOOLS_BIN:\$PATH\""
else
  die "installation finished but binary not found"
fi
