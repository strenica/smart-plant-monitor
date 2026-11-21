#!/usr/bin/env python3
"""Draw the energy figure from the measured numbers.

    python3 measurement/plot_results.py

Writes docs/figures/energy.png and .svg. The numbers are the ones recorded in
RESULTS.md; they are repeated here rather than parsed out of it so the figure
cannot silently drift from a half-edited table.

Needs matplotlib. The system python does not have it; the hvpm venv does:

    ~/Desktop/projects/hvpm-linux/.venv/bin/python measurement/plot_results.py
"""

from __future__ import annotations

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
    for suffix in ("png", "svg"):
        fig.savefig(OUT / f"energy.{suffix}", bbox_inches="tight")
    print(f"wrote {OUT / 'energy.png'} and .svg")


if __name__ == "__main__":
    main()
