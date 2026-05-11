#!/usr/bin/env bash
# Optimize ULog QA screenshots via pngquant (lossless palette quantization).
# Runs install_pngquant.sh first if pngquant is missing.
#
# Target: ulog/web/static/ulog/qa-screenshots/*.png
# (the assets served inline under the /_qa/ checklist items).

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$PROJECT_ROOT/scripts/_lib.sh"

TOOLS_BIN="$PROJECT_ROOT/tools/bin"
TARGET_DIR="$PROJECT_ROOT/ulog/web/static/ulog/qa-screenshots"

# Ensure pngquant is reachable (PATH or tools/bin/).
"$PROJECT_ROOT/scripts/install_pngquant.sh" || die "pngquant could not be installed" $?

# Resolve binary path (prefer PATH, fallback to local build).
PNGQUANT="$(command -v pngquant 2>/dev/null || true)"
[ -z "$PNGQUANT" ] && [ -x "$TOOLS_BIN/pngquant"     ] && PNGQUANT="$TOOLS_BIN/pngquant"
[ -z "$PNGQUANT" ] && [ -x "$TOOLS_BIN/pngquant.exe" ] && PNGQUANT="$TOOLS_BIN/pngquant.exe"
[ -z "$PNGQUANT" ] && die "pngquant not found after install"

[ -d "$TARGET_DIR" ] || die "$TARGET_DIR does not exist"

shopt -s nullglob
files=("$TARGET_DIR"/*.png)
if [ ${#files[@]} -eq 0 ]; then
  info "no PNG to optimize in $TARGET_DIR"
  exit 0
fi

info "using $PNGQUANT"
info "before: $(du -ch "${files[@]}" | tail -1 | awk '{print $1}')"

# --quality=65-85: skip if cannot get below 85, accept down to 65
# --strip:         remove metadata (smaller files)
# --skip-if-larger: never replace with a larger file
# --force --ext .png: overwrite the original PNG in place
"$PNGQUANT" \
  --quality=65-85 \
  --strip \
  --skip-if-larger \
  --force \
  --ext .png \
  "${files[@]}"

info "after:  $(du -ch "${files[@]}" | tail -1 | awk '{print $1}')"
ok "optimization done"
