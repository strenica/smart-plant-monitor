#!/usr/bin/env python3
"""Summarise the raw HVPM captures in measurement/data/.

    python3 measurement/summarise_csv.py

summarise.py reads the JSON summaries that `hvpm capture --json` writes. The
captures actually taken were exported as CSV instead, so this reads those: one
row per capture, grouped by the folder it sits in.

The CSV columns are `Time (s),Main Avg Power (mW)[,Main Min Current (mA),Main
Min Power (mW)]`. Only the first two are used, and only the first two are
present in every export.

Two things the raw files need that a plain mean does not do:

  * Rows above SPIKE_MW are dropped. A few captures end with a single sample in
    the megawatt range, which is a logging artefact and would otherwise
    dominate the mean.
  * `--from` restricts the window. The V3 captures start with the Pi still
    running and booting, so their whole-file mean is not the idle figure; the
    steady state is what the report wants.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import statistics

DATA = pathlib.Path(__file__).resolve().parent / "data"
VOLTS = 5.0
SPIKE_MW = 20000.0


def read_capture(path: pathlib.Path, start: float) -> tuple[float, float, int] | None:
    """Return (duration_s, mean_mw, samples) for one capture, or None."""
    total = 0.0
    count = 0
    first = last = None

    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 2:
                continue
            try:
                t = float(row[0])
                mw = float(row[1])
            except ValueError:
                continue
            if mw > SPIKE_MW or t < start:
                continue
            total += mw
            count += 1
            if first is None:
                first = t
            last = t

    if not count or first is None or last is None:
        return None
    return last - first, total / count, count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--from",
        dest="start",
        type=float,
        default=0.0,
        metavar="S",
        help="ignore the first S seconds of every capture (default: 0)",
    )
    args = ap.parse_args()

    if not DATA.is_dir():
        raise SystemExit(f"no {DATA}. Copy the captures in first.")

    rows: dict[str, list[tuple[str, float, float, int]]] = {}
    for path in sorted(DATA.glob("*/*.csv")):
        result = read_capture(path, args.start)
        if result is None:
            continue
        duration, mean_mw, samples = result
        rows.setdefault(path.parent.name, []).append(
            (path.name, duration, mean_mw, samples)
        )

    if not rows:
        raise SystemExit(f"no CSV captures under {DATA}")

    print(f"{'run':22} {'capture':14} {'len s':>7} {'mW':>9} {'mA':>8} {'Wh/day':>8}")
    print("-" * 72)
    for run, captures in rows.items():
        for name, duration, mean_mw, _ in captures:
            print(
                f"{run:22} {name[:14]:14} {duration:7.1f} {mean_mw:9.1f} "
                f"{mean_mw / VOLTS:8.1f} {mean_mw * 24 / 1000:8.2f}"
            )
        if len(captures) > 1:
            currents = [mw / VOLTS for _, _, mw, _ in captures]
            print(
                f"{'':22} {'mean of ' + str(len(captures)):14} {'':7} "
                f"{statistics.mean(currents) * VOLTS:9.1f} "
                f"{statistics.mean(currents):8.1f} "
                f"{statistics.mean(currents) * VOLTS * 24 / 1000:8.2f}"
            )
            if len(currents) > 1:
                print(
                    f"{'':22} {'spread':14} {'':7} {'':9} "
                    f"{max(currents) - min(currents):8.1f}"
                )
        print()


if __name__ == "__main__":
    main()
