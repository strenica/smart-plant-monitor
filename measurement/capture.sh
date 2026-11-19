#!/usr/bin/env bash
# Capture N consecutive runs for one variant.
#
#   ./measurement/capture.sh v0_baseline 3
#   ./measurement/capture.sh v3_deepsleep 10
#
# Writes measurement/data/<variant>_<n>.csv and .json, and prints the summary
# for each run. DURATION defaults to 60 because the Monsoon resets every
# minute; override it if that turns out not to be true.
#
# Run this on the laptop, where the HVPM is attached. The Pi is the load.

set -euo pipefail

VARIANT="${1:?usage: capture.sh <variant> <count>}"
COUNT="${2:?usage: capture.sh <variant> <count>}"
DURATION="${DURATION:-60}"
VOLTAGE="${VOLTAGE:-5}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/measurement/data"
mkdir -p "$OUT"

for n in $(seq 1 "$COUNT"); do
  csv="$OUT/${VARIANT}_${n}.csv"
  json="$OUT/${VARIANT}_${n}.json"
  printf '=== %s run %d/%d -> %s\n' "$VARIANT" "$n" "$COUNT" "$csv"
  hvpm capture -o "$csv" --duration "$DURATION" --voltage "$VOLTAGE" --json \
    | tee "$json"
  sleep 2
done

printf '\n=== done: %d runs of %s s for %s\n' "$COUNT" "$DURATION" "$VARIANT"
printf '=== summarise with: python3 measurement/summarise.py\n'
