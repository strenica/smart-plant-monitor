#!/usr/bin/env python3
"""V1 fixed duty cycle: the same split as V0, on a slower clock.

The ESP32 samples once a minute instead of continuously, and the Pi takes a
picture every five minutes instead of running the camera flat out. Nothing is
adaptive yet. The intervals are fixed, which is what makes this the first
honest measurement of how much of V0's energy was pure waste.

    python3 v1_duty.py
    python3 v1_duty.py --image-interval 60     # picture every minute
    python3 v1_duty.py --no-vision             # sensors only
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import serial

from common.config import parse_config, parse_reading
from common.logger import EventLog
from common.rules import RuleEngine

# leafs.py imports helpers.py as a sibling, so pi/vision has to be on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent / "vision"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--config", default="config/configuration.txt")
    ap.add_argument("--log", default="logs/events_log.txt")
    ap.add_argument(
        "--cooldown",
        type=float,
        default=30 * 60,
        help="seconds before a rule that is still violated re-alerts",
    )
    ap.add_argument(
        "--image-interval",
        type=float,
        default=300.0,
        help="seconds between camera captures",
    )
    ap.add_argument(
        "--no-vision",
        action="store_true",
        help="sensors and rules only, never touch the camera",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="evaluate and log, but never send a buzz command",
    )
    args = ap.parse_args()

    rules = parse_config(Path(args.config).read_text())
    if not rules:
        sys.exit(f"no rules found in {args.config}")

    print(f"loaded {len(rules)} rules from {args.config}")
    for rule in rules:
        print(f"  {rule}")

    engine = RuleEngine(rules, cooldown_s=args.cooldown)

    vision = None
    if not args.no_vision:
        import leafs
        from common.camera import CameraSettings, capture

        settings = CameraSettings.load()
        vision = (leafs, settings, capture)
        print(
            f"vision every {args.image_interval:g} s at "
            f"{settings.size[0]}x{settings.size[1]}"
        )

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as exc:
        sys.exit(f"cannot open {args.port}: {exc}")

    next_image = time.monotonic()   # capture one straight away

    with EventLog(args.log) as log:
        log.note("v1 fixed duty cycle started")
        print(f"logging to {args.log}. ctrl-c to stop.")

        try:
            while True:
                raw = ser.readline()
                if raw:
                    reading = parse_reading(raw.decode(errors="replace"))
                    if reading is not None:
                        # Log every measurement, as the spec asks.
                        if reading.air_humidity is not None:
                            log.measurement("air_humidity", reading.air_humidity)
                        if reading.air_temp is not None:
                            log.measurement("air_temperature", reading.air_temp)
                        log.measurement("soil_humidity", reading.soil)

                        for rule in engine.evaluate(reading):
                            log.buzzer(rule.number)
                            if not args.dry_run:
                                ser.write(f"buzz {rule.number}\n".encode())
                            print(f"\n  rule {rule.number} fired: {rule}")

                        air = (
                            f"{reading.air_temp:.1f}C {reading.air_humidity:.0f}%"
                            if reading.air_temp is not None
                            else "ERR"
                        )
                        print(
                            f"\rsoil {reading.soil:4d}/1000  air {air}  "
                            f"active {len(engine.active())}",
                            end="",
                            flush=True,
                        )

                if vision is not None and time.monotonic() >= next_image:
                    next_image = time.monotonic() + args.image_interval
                    leafs_module, settings, capture = vision
                    try:
                        image = capture(settings)
                        _, results = leafs_module.analyse(image)
                    except Exception as exc:   # camera busy, model missing, ...
                        log.note(f"vision failed: {exc}")
                        print(f"\n  vision failed: {exc}")
                    else:
                        if not results:
                            log.note("vision: no leaf regions")
                        for result in results:
                            fractions = result["fractions"]
                            log.note(
                                f"vision leaf {result['number']}: "
                                f"G={fractions['green']:.2f} "
                                f"Y={fractions['yellow']:.2f} "
                                f"B={fractions['brown']:.2f} "
                                f"{result['condition']}"
                            )
                        print(f"\n  vision: {len(results)} leaf region(s)")

        except KeyboardInterrupt:
            print()
        finally:
            ser.close()
            log.note("v1 fixed duty cycle stopped")


if __name__ == "__main__":
    main()
