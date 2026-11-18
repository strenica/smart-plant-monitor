#!/usr/bin/env python3
"""V3 deep sleep: the Pi's whole job is one photograph per wake.

The ESP32 sleeps between samples and the Pi is powered off. When a rule fires
the ESP32 pulses the Pi's wake line, the Pi boots, runs this script, and halts
again. Between events the Pi draws nothing at all.

    python3 v3_wake.py
    python3 v3_wake.py --no-halt      # leave the Pi running, for testing
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# leafs.py imports helpers.py as a sibling, so pi/vision has to be on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent / "vision"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", default="logs/events_log.txt")
    ap.add_argument(
        "--no-halt",
        action="store_true",
        help="do not halt the Pi afterwards, for testing",
    )
    args = ap.parse_args()

    import leafs
    from common.camera import CameraSettings, capture, save_last
    from common.logger import EventLog

    settings = CameraSettings.load()

    with EventLog(args.log) as log:
        log.note("v3 wake: capturing")
        try:
            image = capture(settings)
            save_last(image)
            _, results = leafs.analyse(image)
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
