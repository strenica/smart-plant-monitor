#!/usr/bin/env bash
# Prepare and flash one measurement run. Run this on the Pi.
#
#   ./measurement/run.sh v0_baseline
#   ./measurement/run.sh v3_event
#
# Copies the measurement config into place, flashes the variant, and prints
# what to do next. Everything it needs is in the repository, so a `git pull`
# on the Pi is enough — no rsync, no copying files across by hand.

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: run.sh <variant>" >&2
  echo "  v0_baseline  v1_duty  v2_adaptive  v3_deepsleep  v3_event  v3_trigger  v3_loop" >&2
  exit 1
fi

NAME="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$ROOT/measurement/configs/${NAME}.txt"

if [ ! -f "$CONFIG" ]; then
  echo "no such measurement config: $CONFIG" >&2
  echo "available:" >&2
  ls -1 "$ROOT/measurement/configs" | sed 's/\.txt$//' | sed 's/^/  /' >&2
  exit 1
fi

# v3_event, v3_trigger and v3_loop are the same firmware as v3_deepsleep;
# only the rules and the timing differ.
VARIANT="$NAME"
case "$NAME" in v3_event|v3_trigger|v3_loop) VARIANT="v3_deepsleep" ;; esac

cp "$CONFIG" "$ROOT/config/configuration.txt"
echo "== config:  measurement/configs/${NAME}.txt"
echo "== variant: ${VARIANT}"
echo

"$ROOT/install.sh" "$VARIANT" --local

cat <<EOF

== flashed. Now let it settle, about 3 minutes:
     V3:       look for "deep sleep for ..." on the console
     V0/V1/V2: readings scrolling

   Do not capture before then. Powering up is a cold boot, which means setup
   mode, which keeps the ESP32 awake — you would measure the warm-up.

== then, on the machine with the HVPM:

     for n in 1 2 3; do
       hvpm capture -o ${NAME}_\${n}.csv --duration 180 --voltage 5 --json \\
         | tee ${NAME}_\${n}.json
       sleep 2
     done

== and to summarise, copy the .json files into measurement/data/ and run:

     python3 measurement/summarise.py
EOF
