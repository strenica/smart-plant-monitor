#!/usr/bin/env python3
"""Live view of the plant monitor's serial output.

Redraws one status line in place so you can watch the sensors respond while you
move the probe between air and water, or breathe on the DHT11.

    python3 tools/live.py                 # live view
    python3 tools/live.py --raw           # raw log lines, no redraw
    python3 tools/live.py --csv out.csv   # also append every reading to a CSV

Defaults to /dev/ttyUSB0 at 115200. Override with --port and --baud.
"""

import argparse
import re
import sys
import time

import serial

LINE = re.compile(
    r"t=(?P<ms>\d+) soil=(?P<soil>\d+) adc=(?P<adc>\d+)"
    r"(?: air_t=(?P<t>[-\d.]+) air_h=(?P<h>[-\d.]+)| air=ERR)?"
)

BAR_WIDTH = 30


def bar(value, maximum, width=BAR_WIDTH):
    filled = int(round(width * value / maximum)) if maximum else 0
    filled = max(0, min(width, filled))
    return "#" * filled + "." * (width - filled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--raw", action="store_true",
                    help="print raw log lines instead of redrawing")
    ap.add_argument("--csv", help="append every reading to this file")
    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as e:
        sys.exit(f"cannot open {args.port}: {e}")

    csv = open(args.csv, "a", buffering=1) if args.csv else None
    if csv and csv.tell() == 0:
        csv.write("iso_time,uptime_ms,soil,adc,air_temp_c,air_humidity_pct\n")

    print(f"listening on {args.port} at {args.baud}. ctrl-c to stop.", flush=True)
    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            text = raw.decode(errors="replace").strip()
            if args.raw:
                print(text)
                continue

            m = LINE.search(text)
            if not m:
                continue

            soil = int(m["soil"])
            adc = int(m["adc"])
            t, h = m["t"], m["h"]

            air = f"{float(t):5.1f}C {float(h):3.0f}%" if t and h else "  ERR      "
            stamp = time.strftime("%H:%M:%S")

            sys.stdout.write(
                f"\r{stamp}  soil {soil:4d}/1000 [{bar(soil, 1000)}] "
                f"adc {adc:4d}  air {air}"
            )
            sys.stdout.flush()

            if csv:
                csv.write(
                    f"{time.strftime('%Y-%m-%dT%H:%M:%S')},{m['ms']},{soil},{adc},"
                    f"{t or ''},{h or ''}\n"
                )
    except KeyboardInterrupt:
        print()
    finally:
        ser.close()
        if csv:
            csv.close()


if __name__ == "__main__":
    main()
