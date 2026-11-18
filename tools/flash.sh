#!/usr/bin/env bash
# Build and flash the plant monitor firmware with ESP-IDF.
#
#   ./tools/flash.sh              build + flash
#   ./tools/flash.sh --build      build only
#   ./tools/flash.sh --monitor    build, flash, then open the serial monitor
#   PORT=/dev/ttyACM0 ./tools/flash.sh
#
# Requires ESP-IDF. Source it first, or let this script do it:
#   . ~/esp/esp-idf/export.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$ROOT/firmware"
IDF_PATH="${IDF_PATH:-$HOME/esp/esp-idf}"

if ! command -v idf.py >/dev/null 2>&1; then
  if [[ -f "$IDF_PATH/export.sh" ]]; then
    # shellcheck disable=SC1091
    . "$IDF_PATH/export.sh" >/dev/null
  else
    echo "ESP-IDF not found at $IDF_PATH. Set IDF_PATH or install it." >&2
    exit 1
  fi
fi

BUILD_ONLY=0
MONITOR=0
for arg in "$@"; do
  case "$arg" in
    --build)   BUILD_ONLY=1 ;;
    --monitor) MONITOR=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

cd "$PROJECT"

if [[ "$BUILD_ONLY" -eq 1 ]]; then
  idf.py build
  exit 0
fi

PORT="${PORT:-}"
if [[ -z "$PORT" ]]; then
  PORT="$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1 || true)"
fi
if [[ -z "$PORT" ]]; then
  echo "no board found. plug it in, or set PORT=/dev/ttyUSB0" >&2
  exit 1
fi

idf.py -p "$PORT" flash

if [[ "$MONITOR" -eq 1 ]]; then
  idf.py -p "$PORT" monitor
fi
