#!/usr/bin/env python3
"""Average the per-run JSON summaries into one row per variant.

    python3 measurement/summarise.py

Reads measurement/data/*.json, which capture.sh writes. Prints mean current,
the run-to-run spread, average power, and the same figure as Wh per day so the
numbers are comparable to a datasheet.
"""

from __future__ import annotations

import json
import pathlib
import statistics

DATA = pathlib.Path(__file__).resolve().parent / "data"


def main() -> None:
    runs: dict[str, list[dict]] = {}
    for path in sorted(DATA.glob("*.json")):
        variant = path.stem.rsplit("_", 1)[0]
        try:
            summary = json.loads(path.read_text())
        except json.JSONDecodeError:
            print(f"skipping {path.name}: not JSON")
            continue
        runs.setdefault(variant, []).append(summary)

    if not runs:
        raise SystemExit(f"no JSON summaries in {DATA}. Run capture.sh first.")

    print(f"{'variant':16} {'n':>2} {'mean mA':>9} {'sd':>6} {'mW':>8} {'Wh/day':>8}")
    print("-" * 55)
    for variant, summaries in runs.items():
        currents = [s["mean_current_ma"] for s in summaries
                    if s.get("mean_current_ma") is not None]
        volts = [s["mean_voltage_v"] for s in summaries
                 if s.get("mean_voltage_v") is not None]
        if not currents:
            continue
        mean_i = statistics.mean(currents)
        sd_i = statistics.stdev(currents) if len(currents) > 1 else 0.0
        mean_v = statistics.mean(volts) if volts else 0.0
        mw = mean_i * mean_v
        print(f"{variant:16} {len(currents):>2} {mean_i:9.2f} {sd_i:6.2f} "
              f"{mw:8.2f} {mw * 24 / 1000:8.3f}")

    print()
    print("sd is the sample standard deviation across runs, not the meter's")
    print("noise. With n=3 it is a rough spread, not a confidence interval.")


if __name__ == "__main__":
    main()
