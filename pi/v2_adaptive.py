#!/usr/bin/env python3
"""V2 adaptive sampling: the Pi is out of the decision loop.

The ESP32 owns the rules now, so it buzzes on its own and only tells the Pi
when something happened. The Pi's job is to log the readings and to photograph
the plant when an event arrives, plus a slow heartbeat so a quiet plant still
gets a picture now and then.

    python3 v2_adaptive.py
    python3 v2_adaptive.py --heartbeat 3600
    python3 v2_adaptive.py --no-vision
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import serial

from common.config import parse_reading
from common.logger import EventLog

# leafs.py imports helpers.py as a sibling, so pi/vision has to be on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent / "vision"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--log", default="logs/events_log.txt")
    ap.add_argument(
        "--heartbeat",
        type=float,
        default=3600.0,
        help="seconds between pictures when nothing happens",
    )
    ap.add_argument(
        "--no-vision",
        action="store_true",
        help="log readings only, never touch the camera",
    )
    args = ap.parse_args()

    vision = None
    if not args.no_vision:
        import leafs
        from common.camera import CameraSettings, capture

        settings = CameraSettings.load()
        vision = (leafs, settings, capture)
        print(
            f"vision on event and every {args.heartbeat:g} s at "
            f"{settings.size[0]}x{settings.size[1]}"
        )

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as exc:
        sys.exit(f"cannot open {args.port}: {exc}")

    def photograph(log: EventLog, why: str) -> None:
        if vision is None:
            return
        leafs_module, settings, capture = vision
        try:
            image = capture(settings)
            _, results = leafs_module.analyse(image)
        except Exception as exc:   # camera busy, model missing, ...
            log.note(f"vision failed ({why}): {exc}")
            print(f"\n  vision failed: {exc}")
            return

        if not results:
            log.note(f"vision ({why}): no leaf regions")
        for result in results:
            fractions = result["fractions"]
            log.note(
                f"vision ({why}) leaf {result['number']}: "
                f"G={fractions['green']:.2f} "
                f"Y={fractions['yellow']:.2f} "
                f"B={fractions['brown']:.2f} "
                f"{result['condition']}"
            )
        print(f"\n  vision ({why}): {len(results)} leaf region(s)")

    next_heartbeat = time.monotonic() + args.heartbeat

    with EventLog(args.log) as log:
        log.note("v2 adaptive sampling started")
        print(f"logging to {args.log}. ctrl-c to stop.")

        try:
            while True:
                raw = ser.readline()
                if raw:
                    text = raw.decode(errors="replace").strip()

                    if text.startswith("event"):
                        # The ESP32 already buzzed. The Pi's contribution is a
                        # picture of whatever changed.
                        log.note(f"esp32 {text}")
                        print(f"\n  {text}")
                        photograph(log, text.replace(" ", "_"))
                    else:
                        reading = parse_reading(text)
                        if reading is not None:
                            if reading.air_humidity is not None:
                                log.measurement("air_humidity", reading.air_humidity)
                            if reading.air_temp is not None:
                                log.measurement("air_temperature", reading.air_temp)
                            log.measurement("soil_humidity", reading.soil)

                            air = (
                                f"{reading.air_temp:.1f}C "
                                f"{reading.air_humidity:.0f}%"
                                if reading.air_temp is not None
                                else "ERR"
                            )
                            print(
                                f"\rsoil {reading.soil:4d}/1000  air {air}",
                                end="",
                                flush=True,
                            )

                if time.monotonic() >= next_heartbeat:
                    next_heartbeat = time.monotonic() + args.heartbeat
                    photograph(log, "heartbeat")

        except KeyboardInterrupt:
            print()
        finally:
            ser.close()
            log.note("v2 adaptive sampling stopped")


if __name__ == "__main__":
    main()
