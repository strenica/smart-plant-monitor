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

from common import SETUP_EXIT
from common.config import parse_reading, parse_retention, parse_timing
from common.logger import EventLog

# leafs.py imports helpers.py as a sibling, so pi/vision has to be on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent / "vision"))


class SetupRequested(Exception):
    """The ESP32 was reset, so the user wants to reframe the camera."""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--config", default="config/configuration.txt")
    ap.add_argument("--log", default="logs/events_log.txt")
    ap.add_argument(
        "--heartbeat",
        type=float,
        default=None,
        help="seconds between pictures when nothing happens (default: "
        "heartbeat from configuration.txt, else 3600)",
    )
    ap.add_argument(
        "--no-vision",
        action="store_true",
        help="log readings only, never touch the camera",
    )
    args = ap.parse_args()

    timing = parse_timing(Path(args.config).read_text())
    heartbeat = args.heartbeat
    if heartbeat is None:
        heartbeat = timing.heartbeat if timing.heartbeat is not None else 3600.0

    vision = None
    if not args.no_vision:
        import leafs
        from common.camera import CameraSettings, capture, save_last

        settings = CameraSettings.load()
        vision = (leafs, settings, capture)
        print(
            f"vision on event and every {heartbeat:g} s at "
            f"{settings.size[0]}x{settings.size[1]}"
        )

    setup = False

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
            save_last(image)
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

    # Retune the ESP32 without reflashing it.
    if timing.sample_interval is not None:
        ser.write(f"set interval {int(timing.sample_interval * 1000)}\n".encode())
    if timing.adaptive_fast is not None and timing.adaptive_slow is not None:
        ser.write(
            f"set adaptive {int(timing.adaptive_fast * 1000)} "
            f"{int(timing.adaptive_slow * 1000)}\n".encode()
        )

    next_heartbeat = time.monotonic() + heartbeat

    with EventLog(args.log, max_lines=retention.log_max_lines) as log:
        log.note("v2 adaptive sampling started")
        print(f"logging to {args.log}. ctrl-c to stop.")

        try:
            while True:
                raw = ser.readline()
                if raw:
                    text = raw.decode(errors="replace").strip()

                    if text == "setup":
                        log.note("esp32 asked for setup mode")
                        raise SetupRequested

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
                    next_heartbeat = time.monotonic() + heartbeat
                    photograph(log, "heartbeat")

        except SetupRequested:
            setup = True
            print("\n  esp32 asked for setup mode")
        except KeyboardInterrupt:
            print()
        finally:
            ser.close()
            log.note("v2 adaptive sampling stopped")

    if setup:
        sys.exit(SETUP_EXIT)


if __name__ == "__main__":
    main()
