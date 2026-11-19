#!/usr/bin/env python3
"""V3 deep sleep: the Pi's whole job is one photograph per wake.

The ESP32 sleeps between samples and the Pi is powered off. When a rule fires
the ESP32 pulses the Pi's wake line, the Pi boots, runs this script, and halts
again. Between events the Pi draws nothing at all.

Readings taken while the Pi was off are not lost: the ESP32 keeps them in RTC
memory and hands them over as soon as the Pi asks, which is the first thing this
script does. The same session pushes the rules from configuration.txt the other
way, so changing a rule does not need a reflash. The ESP32 stays awake for that
handover and then goes back to sleep.

    python3 v3_wake.py
    python3 v3_wake.py --no-halt      # leave the Pi running, for testing
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import serial

# leafs.py imports helpers.py as a sibling, so pi/vision has to be on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent / "vision"))


def handover(port: str, baud: int, log, config_path: Path,
             timeout: float = 5.0) -> int:
    """Do everything that needs the ESP32 awake, in one session.

    The ESP32 only answers while it is awake, which is the window right after it
    wakes us. Two jobs: collect the readings it buffered while we were off, and
    hand it the rules from configuration.txt so a rule change needs no reflash.
    It goes back to sleep when we say "bye", so both have to happen before that.

    If it has already gone back to sleep there is no reply and nothing to log,
    and that is not an error: the readings stay buffered for next time.

    Returns how many readings were collected.
    """
    from common.config import parse_reading

    try:
        ser = serial.Serial(port, baud, timeout=0.5)
    except serial.SerialException as exc:
        log.note(f"v3 wake: no serial link: {exc}")
        return 0

    readings = []
    try:
        ser.reset_input_buffer()
        ser.write(b"log?\n")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = ser.readline().decode(errors="replace").strip()
            if line == "log end":
                break
            if line.startswith("log "):
                reading = parse_reading(line)
                if reading is not None:
                    readings.append(reading)

        push_rules(ser, log, config_path)

        # Let the ESP32 stop waiting and go back to sleep now rather than at the
        # end of its handover timeout.
        ser.write(b"bye\n")
    finally:
        ser.close()

    if not readings:
        return 0

    log.note(
        f"v3 wake: {len(readings)} buffered readings, "
        f"esp32 t={readings[0].uptime_ms}..{readings[-1].uptime_ms} ms"
    )
    for reading in readings:
        if reading.air_humidity is not None:
            log.measurement("air_humidity", reading.air_humidity)
        if reading.air_temp is not None:
            log.measurement("air_temperature", reading.air_temp)
        log.measurement("soil_humidity", reading.soil)
    return len(readings)


def push_rules(ser, log, config_path: Path) -> None:
    """Hand the ESP32 the current rule set, and record what it ended up with.

    The whole set goes every time, starting with "rule clear", so a rule deleted
    from configuration.txt actually disappears on the ESP32 too.
    """
    from common.config import parse_config

    try:
        rules = parse_config(config_path.read_text())
    except (OSError, ValueError) as exc:
        log.note(f"v3 wake: cannot read rules: {exc}")
        return

    commands = ["rule clear"]
    commands += [
        f"rule {rule.number} {rule.field} {rule.op} {rule.threshold:g}"
        for rule in rules
    ]
    commands.append("rule save")

    for command in commands:
        ser.write(command.encode() + b"\n")
        time.sleep(0.05)

    # The ESP32 answers every line. Read them back so the log records what it
    # actually holds rather than what we hoped it took.
    confirmed = None
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if not line:
            break
        if line.startswith("rules saved"):
            confirmed = line

    log.note(
        f"v3 wake: pushed {len(rules)} rules, esp32 says {confirmed or 'nothing'}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--config", default="config/configuration.txt")
    ap.add_argument("--log", default="logs/events_log.txt")
    ap.add_argument(
        "--no-halt",
        action="store_true",
        help="do not halt the Pi afterwards, for testing",
    )
    args = ap.parse_args()

    from common.camera import CameraSettings, capture, save_last
    from common.config import parse_retention
    from common.logger import EventLog

    retention = parse_retention(Path(args.config).read_text())

    with EventLog(args.log, max_lines=retention.log_max_lines) as log:
        # First, before anything that can fail: the ESP32 is holding the backlog
        # for us and will not wait forever. The rules go the other way in the
        # same session, because it sleeps as soon as we say "bye".
        log.note("v3 wake: collecting buffered readings")
        handover(args.port, args.baud, log, Path(args.config))

        log.note("v3 wake: capturing")
        try:
            import leafs

            settings = CameraSettings.load()
            image = capture(settings)
            save_last(image)
            masks, results = leafs.analyse(image)
            save_last(
                leafs.annotate(image, masks, results),
                "logs/last_analysis.jpg",
            )
        except Exception as exc:   # camera busy, model missing, ...
            log.note(f"v3 wake: vision failed: {exc}")
            print(f"vision failed: {exc}")
        else:
            if not results:
                log.note("v3 wake: no leaf regions")
            for result in results:
                fractions = result["fractions"]
                log.note(
                    f"v3 wake leaf {result['number']}: "
                    f"G={fractions['green']:.2f} "
                    f"Y={fractions['yellow']:.2f} "
                    f"B={fractions['brown']:.2f} "
                    f"H={result['hsv'][0]:.0f} "
                    f"S={result['hsv'][1]:.0f} "
                    f"V={result['hsv'][2]:.0f} "
                    f"{result['condition']}"
                )
            print(f"{len(results)} leaf region(s)")

        if args.no_halt:
            log.note("v3 wake: not halting (--no-halt)")
        else:
            log.note("v3 wake: halting")

    if not args.no_halt:
        subprocess.run(["sudo", "halt"], check=False)


if __name__ == "__main__":
    main()
