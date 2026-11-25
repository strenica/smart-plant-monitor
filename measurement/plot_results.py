#!/usr/bin/env python3
"""Draw the energy figure from the measured numbers.

    python3 measurement/plot_results.py

Writes docs/figures/energy.png and .svg, plus v3_trace.png and .svg from the
raw V3 loop capture. The numbers are the ones recorded in
RESULTS.md; they are repeated here rather than parsed out of it so the figure
cannot silently drift from a half-edited table.

Needs matplotlib. The system python does not have it; the hvpm venv does:

    ~/Desktop/projects/hvpm-linux/.venv/bin/python measurement/plot_results.py
"""

from __future__ import annotations

import csv
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "figures"
VOLTS = 5.0

# (label, mean current mA, spread mA, colour, note)
RUNS = [
    ("V0\nbaseline", 381.4, 1.3, "#9aa5b1", "Pi on, 2 s sampling"),
    ("V1\nfixed duty", 660.6, 39.4, "#c98b6b", "Pi on, camera every 60 s"),
    ("V2\nadaptive", 380.5, 0.8, "#9aa5b1", "Pi on, adaptive sampling"),
    ("V3\ndeep sleep", 268.8, 0.5, "#4a7fb5", "Pi halted, ESP32 asleep"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=200)

    labels = [r[0] for r in RUNS]
    currents = [r[1] for r in RUNS]
    spreads = [r[2] for r in RUNS]
    colours = [r[3] for r in RUNS]

    bars = ax.bar(
        labels,
        currents,
        yerr=spreads,
        color=colours,
        width=0.58,
        edgecolor="#333333",
        linewidth=0.8,
        capsize=4,
        error_kw={"elinewidth": 0.9, "ecolor": "#333333"},
    )

    for bar, (_, current, _, _, _) in zip(bars, RUNS):
        wh_day = current * VOLTS * 24 / 1000
        ax.annotate(
            f"{current:.0f} mA\n{wh_day:.1f} Wh/day",
            xy=(bar.get_x() + bar.get_width() / 2, current),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )

    # The point of the figure: V3's floor is the halted Pi, not the ESP32.
    ax.axhline(
        268.8,
        color="#4a7fb5",
        linestyle=":",
        linewidth=1.1,
        zorder=0,
        label="halted Pi 4 floor, 268.8 mA",
    )
    ax.legend(loc="upper left", fontsize=8, frameon=False)

    ax.set_ylabel("mean current at 5 V (mA)")
    ax.set_ylim(0, 780)
    ax.set_title("Mean current per variant, steady state", fontsize=10.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#dddddd", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", labelsize=9)

    fig.tight_layout()
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(OUT / f"energy.{suffix}", bbox_inches="tight")
    print(f"wrote {OUT / 'energy.png'}, .svg and .pdf")


def plot_trace() -> None:
    """Draw the V3 loop capture as a time series.

    This is the figure that shows what V3 looks like on the meter: a flat idle
    floor with a burst every time the Pi boots. The raw capture is 3.5 million
    rows, so it is bucketed into one-second bins before plotting.
    """
    source = (
        pathlib.Path(__file__).resolve().parent
        / "data"
        / "cyclesleep"
        / "PowerBox_23585_-8584064943713825023.csv"
    )
    if not source.exists():
        print(f"skipping the trace: no {source}")
        return

    buckets: dict[int, list[float]] = {}
    with source.open(newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            try:
                t = float(row[0])
                mw = float(row[1])
            except ValueError:
                continue
            if mw > 20000:
                continue
            buckets.setdefault(int(t), []).append(mw)

    times = sorted(buckets)
    power = [sum(buckets[t]) / len(buckets[t]) for t in times]

    fig, ax = plt.subplots(figsize=(7.2, 3.0), dpi=200)
    ax.plot(times, power, color="#4a7fb5", linewidth=0.9)
    ax.axhline(1344, color="#c98b6b", linestyle=":", linewidth=1.0,
               label="idle floor, 268.8 mA")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("power (mW)")
    ax.set_title("V3 loop: the Pi woken every ~70 s", fontsize=10.5)
    ax.set_xlim(0, max(times))
    ax.set_ylim(0, max(power) * 1.12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=8, frameon=False)

    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(OUT / f"v3_trace.{suffix}", bbox_inches="tight")
    print(f"wrote {OUT / 'v3_trace.png'} and .svg")


if __name__ == "__main__":
    main()
    plot_trace()
