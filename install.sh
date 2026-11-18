#!/usr/bin/env bash
# Install one rung of the variant ladder.
#
#   ./install.sh v1_duty              build, flash the ESP32, deploy the Pi code
#   ./install.sh v1_duty --fw-only    firmware only
#   ./install.sh v1_duty --pi-only    Pi code only
#   ./install.sh v1_duty --no-flash   build the firmware but do not flash it
#   ./install.sh v1_duty --service    also install a systemd unit
#   ./install.sh v1_duty --dashboard  also install the web dashboard on boot
#   ./install.sh --list               show the variants
#
# The ESP32 is wired to the Pi, not to this laptop, so the build happens here
# and only the binaries travel. esptool runs on the Pi at 115200 baud with
# --no-stub: this board's CP2102 fails to start the stub flasher at any baud,
# and the ROM loader is slower but reliable.
#
# Override the target with PI=user@host, PI_DIR=~/plant, FW_DIR=~/plant/fw.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI="${PI:-admin@10.42.0.15}"
PI_DIR="${PI_DIR:-~/plant}"
FW_DIR="${FW_DIR:-~/plant/fw}"
BAUD="${BAUD:-115200}"
BUILD="$ROOT/firmware/build"

VARIANTS=(v0_baseline v1_duty v2_adaptive v3_deepsleep)

usage() {
  sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

list_variants() {
  echo "variants:"
  for v in "${VARIANTS[@]}"; do
    name="$(sed -n 's/^#define VARIANT_NAME "\(.*\)"/\1/p' "$ROOT/variants/$v/variant.h")"
    printf '  %-14s %s\n' "$v" "$name"
  done
}

VARIANT=""
FW_ONLY=0
PI_ONLY=0
NO_FLASH=0
SERVICE=0
DASHBOARD=0

for arg in "$@"; do
  case "$arg" in
    --list)     list_variants; exit 0 ;;
    --fw-only)  FW_ONLY=1 ;;
    --pi-only)  PI_ONLY=1 ;;
    --no-flash) NO_FLASH=1 ;;
    --service)  SERVICE=1 ;;
    --dashboard) DASHBOARD=1 ;;
    -h|--help)  usage; exit 0 ;;
    -*)         echo "unknown option: $arg" >&2; usage >&2; exit 1 ;;
    *)          VARIANT="$arg" ;;
  esac
done

if [ -z "$VARIANT" ]; then
  usage >&2
  echo >&2
  list_variants >&2
  exit 1
fi

VDIR="$ROOT/variants/$VARIANT"
if [ ! -d "$VDIR" ]; then
  echo "no such variant: $VARIANT" >&2
  list_variants >&2
  exit 1
fi

if [ "$FW_ONLY" -eq 1 ] && [ "$PI_ONLY" -eq 1 ]; then
  echo "--fw-only and --pi-only are mutually exclusive" >&2
  exit 1
fi

# --- firmware ---------------------------------------------------------------
if [ "$PI_ONLY" -eq 0 ]; then
  echo "== firmware: $VARIANT"
  cp "$VDIR/variant.h" "$ROOT/firmware/main/variant.h"

  # shellcheck disable=SC1091
  . "$ROOT/tools/idf_env.sh"
  (cd "$ROOT/firmware" && idf.py build)

  if [ "$NO_FLASH" -eq 1 ]; then
    echo "== built, not flashing (--no-flash)"
  else
    echo "== flashing on $PI"
    ssh "$PI" "mkdir -p $FW_DIR"
    scp -q "$BUILD/bootloader/bootloader.bin" \
           "$BUILD/partition_table/partition-table.bin" \
           "$BUILD/plant_monitor.bin" \
           "$PI:$FW_DIR/"
    ssh "$PI" "cd $FW_DIR && $PI_DIR/.venv/bin/python -m esptool \
        --port /dev/ttyUSB0 --baud $BAUD --no-stub write-flash \
        --flash-mode dio --flash-size 4MB --flash-freq 40m \
        0x1000 bootloader.bin 0x8000 partition-table.bin 0x10000 plant_monitor.bin"
  fi
fi

# --- Pi code ----------------------------------------------------------------
if [ "$FW_ONLY" -eq 0 ]; then
  echo "== pi code: $VARIANT"
  ssh "$PI" "mkdir -p $PI_DIR"

  # No --delete: the Pi also holds the venv, the logs and the flashed binaries,
  # and none of those live in this repo.
  rsync -az \
    --exclude '.git' --exclude '.venv' --exclude 'logs' --exclude 'fw' \
    --exclude '__pycache__' --exclude '*.pdf' --exclude '*.zip' \
    --exclude 'firmware/build' --exclude 'HANDOFF.md' \
    "$ROOT/" "$PI:$PI_DIR/"

  ssh "$PI" "cd $PI_DIR && \
    [ -d .venv ] || python3 -m venv --system-site-packages .venv; \
    .venv/bin/pip install -q -r requirements.txt"

  # Install a unit file. sudo over SSH has no terminal, so it only works
  # unattended when the Pi has passwordless sudo. Rather than embed a password
  # here, print the commands and let the user run them.
  install_unit() {
    local unit="$1" start="$2"
    scp -q "/tmp/$unit" "$PI:/tmp/$unit"
    if ssh "$PI" "sudo -n true" 2>/dev/null; then
      ssh "$PI" "sudo mv /tmp/$unit /etc/systemd/system/$unit && \
        sudo systemctl daemon-reload && sudo systemctl enable $start $unit"
      echo "   installed and enabled"
    else
      echo "   sudo needs a password on $PI, so run this yourself:"
      echo "     ssh $PI 'sudo mv /tmp/$unit /etc/systemd/system/$unit && \\"
      echo "       sudo systemctl daemon-reload && sudo systemctl enable $start $unit'"
    fi
  }

  if [ "$SERVICE" -eq 1 ]; then
    # One fixed unit name, so switching variants replaces the monitor instead
    # of leaving the previous one enabled and fighting for the camera.
    echo "== systemd unit: plant-monitor ($VARIANT)"
    UNIT="plant-monitor.service"
    printf '%s\n' \
      "[Unit]" \
      "Description=Smart plant monitor ($VARIANT)" \
      "After=multi-user.target" \
      "" \
      "[Service]" \
      "Type=simple" \
      "WorkingDirectory=$PI_DIR" \
      "ExecStart=$PI_DIR/.venv/bin/python $PI_DIR/tools/supervisor.py --variant $VARIANT" \
      "Restart=no" \
      "" \
      "[Install]" \
      "WantedBy=multi-user.target" \
      > "/tmp/$UNIT"
    install_unit "$UNIT" ""
  fi

  if [ "$DASHBOARD" -eq 1 ]; then
    echo "== systemd unit: plant-dashboard"
    UNIT="plant-dashboard.service"
    printf '%s\n' \
      "[Unit]" \
      "Description=Smart plant monitor dashboard" \
      "After=multi-user.target" \
      "" \
      "[Service]" \
      "Type=simple" \
      "WorkingDirectory=$PI_DIR" \
      "ExecStart=$PI_DIR/.venv/bin/python $PI_DIR/tools/dashboard.py" \
      "Restart=always" \
      "" \
      "[Install]" \
      "WantedBy=multi-user.target" \
      > "/tmp/$UNIT"
    install_unit "$UNIT" "--now"
    echo "   dashboard on http://<pi-address>:8081/"
  fi
fi

echo
echo "== done: $VARIANT"
echo "   run on the Pi:  ssh $PI 'cd $PI_DIR && .venv/bin/python tools/supervisor.py --variant $VARIANT'"
