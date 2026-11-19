#!/usr/bin/env python3
"""V3 deep sleep: the Pi's whole job is one photograph per wake.

The ESP32 sleeps between samples and the Pi is powered off. When a rule fires
the ESP32 pulses the Pi's wake line, the Pi boots, runs this script, and halts
again. Between events the Pi draws nothing at all.

Readings taken while the Pi was off are not lost: the ESP32 keeps them in RTC
memory and hands them over as soon as the Pi asks, which is the first thing this
script does. The ESP32 stays awake for that handover and then goes back to
sleep.

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


def collect_backlog(port: str, baud: int, log, timeout: float = 5.0) -> int:
    """Ask the ESP32 for the readings it took while the Pi was off.

    The ESP32 only answers while it is awake, which is the window right after it
    wakes us. If it has already gone back to sleep there is no reply and nothing
    to log, and that is not an error: the readings stay buffered for next time.
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

    import leafs
    from common.camera import CameraSettings, capture, save_last
    from common.config import parse_retention
    from common.logger import EventLog

    settings = CameraSettings.load()
    retention = parse_retention(Path(args.config).read_text())

    with EventLog(args.log, max_lines=retention.log_max_lines) as log:
        # First, before the camera: the ESP32 is holding the backlog for us and
        # will not wait forever.
        log.note("v3 wake: collecting buffered readings")
        collect_backlog(args.port, args.baud, log)

        log.note("v3 wake: capturing")
        try:
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
