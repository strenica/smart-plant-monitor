#!/usr/bin/env bash
# Build on this machine, flash on the Pi over SSH.
#
# The ESP32 is wired to the Pi, not to this laptop, so the build happens here
# and only the binaries travel. esptool runs on the Pi at 115200 baud: this
# board's CP2102 will not start the stub flasher at the default 460800.
#
#   ./tools/flash_pi.sh            build, copy, flash
#   ./tools/flash_pi.sh --build    build only
#   PI=admin@10.42.0.15 ./tools/flash_pi.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="$ROOT/firmware/build"
PI="${PI:-admin@10.42.0.15}"
PI_DIR="${PI_DIR:-~/plant/fw}"
BAUD="${BAUD:-115200}"
IDF_PATH="${IDF_PATH:-$HOME/esp/esp-idf}"

BUILD_ONLY=0
[[ "${1:-}" == "--build" ]] && BUILD_ONLY=1

if ! command -v idf.py >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  . "$IDF_PATH/export.sh" >/dev/null
fi

echo "building"
(cd "$ROOT/firmware" && idf.py build)

if [[ "$BUILD_ONLY" -eq 1 ]]; then
  echo "build only, not flashing"
  exit 0
fi

echo "copying to $PI"
ssh "$PI" "mkdir -p $PI_DIR"
scp -q "$BUILD/bootloader/bootloader.bin" \
       "$BUILD/partition_table/partition-table.bin" \
       "$BUILD/plant_monitor.bin" \
       "$PI:$PI_DIR/"

echo "flashing at $BAUD baud"
ssh "$PI" "cd $PI_DIR && ~/plant/.venv/bin/python -m esptool \
    --port /dev/ttyUSB0 --baud $BAUD write-flash \
    --flash-mode dio --flash-size 4MB --flash-freq 40m \
    0x1000 bootloader.bin 0x8000 partition-table.bin 0x10000 plant_monitor.bin"
