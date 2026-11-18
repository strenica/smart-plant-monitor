#!/usr/bin/env python3
"""V0 baseline: the naive version, with no energy management at all.

The Pi polls the ESP32 over UART2, evaluates configuration.txt, drives the
buzzer, and writes events_log.txt. This is the reference point every other
variant is measured against, so it deliberately does the obvious thing: sample
as often as the ESP32 sends, evaluate every sample, log everything.

    python3 v0_baseline.py
    python3 v0_baseline.py --dry-run          # evaluate and log, never buzz
    python3 v0_baseline.py --cooldown 60      # re-alert after 60 s instead of 30 min
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import serial

from common.config import parse_config, parse_reading, parse_timing
from common.logger import EventLog
from common.rules import RuleEngine


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
        "--dry-run",
        action="store_true",
        help="evaluate and log, but never send a buzz command",
    )
    args = ap.parse_args()

    config_text = Path(args.config).read_text()
    rules = parse_config(config_text)
    timing = parse_timing(config_text)
    if not rules:
        sys.exit(f"no rules found in {args.config}")

    print(f"loaded {len(rules)} rules from {args.config}")
    for rule in rules:
        print(f"  {rule}")

    engine = RuleEngine(rules, cooldown_s=args.cooldown)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as exc:
        sys.exit(f"cannot open {args.port}: {exc}")

    # Retune the ESP32 without reflashing it.
    if timing.sample_interval is not None:
        ser.write(f"set interval {int(timing.sample_interval * 1000)}\n".encode())

    with EventLog(args.log) as log:
        log.note("v0 baseline started")
        print(f"logging to {args.log}. ctrl-c to stop.")

        try:
            while True:
                raw = ser.readline()
                if not raw:
                    continue

                reading = parse_reading(raw.decode(errors="replace"))
                if reading is None:
                    continue

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

        except KeyboardInterrupt:
            print()
        finally:
            ser.close()
            log.note("v0 baseline stopped")


if __name__ == "__main__":
    main()
