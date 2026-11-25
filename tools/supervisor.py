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
from common.config import parse_config, parse_timing  # noqa: E402


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


def tell_esp32_many(port: str, baud: int, commands: list[str]) -> None:
    """Same, but over one connection. A rule push is a dozen lines."""
    try:
        ser = serial.Serial(port, baud, timeout=0.5)
    except serial.SerialException:
        return
    try:
        for command in commands:
            ser.write(command.encode() + b"\n")
            time.sleep(0.05)
        time.sleep(0.2)
    finally:
        ser.close()


def push_rules(port: str, baud: int, config_path: Path) -> None:
    """Send the rules from configuration.txt to the ESP32.

    Only lands while the ESP32 is awake, same as the timing. It keeps them in
    RTC memory, so changing a rule needs no reflash: press EN, save, and this
    hands them over. V3 also pushes them on every wake, so a change made while
    the Pi happened to be up reaches the ESP32 at the next event.

    The whole set goes every time, starting with "rule clear". Replacing rather
    than patching means a rule deleted from configuration.txt actually
    disappears on the ESP32 too.
    """
    try:
        rules = parse_config(config_path.read_text())
    except (OSError, ValueError) as exc:
        print(f"cannot read {config_path}: {exc}", flush=True)
        return

    commands = ["rule clear"]
    commands += [
        f"rule {rule.number} {rule.field} {rule.op} {rule.threshold:g}"
        for rule in rules
    ]
    commands.append("rule save")
    tell_esp32_many(port, baud, commands)
    print(f"pushed {len(rules)} rules to the ESP32", flush=True)


def push_timing(port: str, baud: int, config_path: Path) -> None:
    """Send the intervals from configuration.txt to the ESP32.

    Only lands while the ESP32 is awake, which in V3 means setup mode: the rest
    of the time it is deep asleep and keeps whatever it already had. Best
    effort, like every other command on this link.
    """
    try:
        timing = parse_timing(config_path.read_text())
    except (OSError, ValueError) as exc:
        print(f"cannot read {config_path}: {exc}", flush=True)
        return

    if timing.sample_interval is not None:
        tell_esp32(port, baud, f"set interval {int(timing.sample_interval * 1000)}")
    if timing.adaptive_fast is not None and timing.adaptive_slow is not None:
        tell_esp32(
            port,
            baud,
            f"set adaptive {int(timing.adaptive_fast * 1000)} "
            f"{int(timing.adaptive_slow * 1000)}",
        )
    if timing.wake_every_n_samples is not None:
        tell_esp32(port, baud, f"set wake {int(timing.wake_every_n_samples)}")
    if timing.wake_heartbeat is not None:
        tell_esp32(port, baud, f"set heartbeat {int(timing.wake_heartbeat * 1000)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", required=True, help="folder under variants/")
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument(
        "--setup-timeout",
        type=float,
        default=120.0,
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
            # The ESP32 is awake right now, which is the only chance to hand it
            # the intervals and the rules from configuration.txt. In V3 it is
            # asleep the rest of the time, so this is the only path that ever
            # reaches it without a reflash.
            config = ROOT / "config" / "configuration.txt"
            push_timing(args.port, args.baud, config)
            push_rules(args.port, args.baud, config)
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
