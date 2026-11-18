#!/usr/bin/env python3
"""Decide what the Pi should do on boot: frame the camera, or monitor.

Pressing EN on the ESP32 cold-boots it, and it remembers that. This script asks
it over UART2 what mode it is in:

  setup   the camera preview runs instead of the monitoring loop, so you can
          reframe. It ends when you press "save and apply", or after five
          minutes with no browser connected.
  run     the monitoring loop starts straight away.

Either way the monitoring loop is what runs afterwards, so a forgotten preview
cannot leave the plant unwatched.

    python3 tools/supervisor.py --variant v1_duty
    python3 tools/supervisor.py --variant v1_duty --setup-timeout 300
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[1]


def _find_pi_root() -> Path | None:
    """Locate the `pi` package whether this runs from tools/ or from ~/plant."""
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "pi" / "common" / "camera.py").exists():
            return candidate / "pi"
    return None


_pi_root = _find_pi_root()
if _pi_root is not None:
    sys.path.insert(0, str(_pi_root))

from common import SETUP_EXIT  # noqa: E402


def ask_mode(port: str, baud: int, timeout: float = 5.0) -> str:
    """Ask the ESP32 whether it wants setup mode. Defaults to "run".

    Defaulting to run matters: if the ESP32 is asleep, unplugged or dead, the
    plant still gets monitored rather than the Pi sitting in a preview nobody
    asked for.
    """
    try:
        ser = serial.Serial(port, baud, timeout=0.5)
    except serial.SerialException as exc:
        print(f"cannot open {port}: {exc}; assuming run mode")
        return "run"

    try:
        ser.reset_input_buffer()
        ser.write(b"mode?\n")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = ser.readline().decode(errors="replace").strip()
            if line.startswith("mode "):
                return line.split(None, 1)[1]
    finally:
        ser.close()

    print("no answer from the ESP32; assuming run mode")
    return "run"


def tell_esp32(port: str, baud: int, command: str) -> None:
    """Best effort: the ESP32 may be asleep, and that is not an error."""
    try:
        ser = serial.Serial(port, baud, timeout=0.5)
    except serial.SerialException:
        return
    try:
        ser.write(command.encode() + b"\n")
        time.sleep(0.2)
    finally:
        ser.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", required=True, help="folder under variants/")
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "--setup-timeout",
        type=float,
        default=300.0,
        help="seconds the preview waits for a browser before giving up",
    )
    ap.add_argument("--preview-port", type=int, default=8080)
    args = ap.parse_args()

    run = ROOT / "variants" / args.variant / "run.py"
    if not run.exists():
        sys.exit(f"no such variant: {args.variant}")

    while True:
        mode = ask_mode(args.port, args.baud)
        print(f"esp32 mode: {mode}", flush=True)

        if mode == "setup":
            print(
                f"setup mode: preview on port {args.preview_port}, "
                f"giving up after {args.setup_timeout:g} s with no browser",
                flush=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "preview.py"),
                    "--force",
                    "--port",
                    str(args.preview_port),
                    "--timeout",
                    str(args.setup_timeout),
                ]
            )
            # Framing is done, one way or another. Clear the flag so the next
            # boot goes straight to monitoring.
            tell_esp32(args.port, args.baud, "mode run")

        print(f"starting {args.variant}", flush=True)
        result = subprocess.run([sys.executable, str(run)])

        if result.returncode != SETUP_EXIT:
            break

        # The ESP32 was reset while we were monitoring, so the user wants to
        # reframe. Loop round: the next pass asks for the mode again and lands
        # in the preview.
        print("esp32 was reset, switching to setup mode", flush=True)


if __name__ == "__main__":
    main()
