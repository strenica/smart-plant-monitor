# V2 — adaptive sampling

The rules move onto the ESP32, so the Pi stops being in the decision loop, and
the sampling interval follows the observed variance.

## What it changes

| | V1 | V2 |
|---|---|---|
| Rules evaluated on | Pi | **ESP32** |
| Sample interval | fixed 60 s | **10 s when changing, 10 min when stable** |
| Pi camera | every 5 min | **on event, plus a heartbeat** |
| Pi role | poll and decide | log and photograph |

The ESP32 now buzzes on its own and sends `event rule=N` over UART2 when
something fires. The Pi photographs on that event and on a slow heartbeat, so a
quiet plant still gets a picture now and then.

## Install

```bash
./install.sh v2_adaptive
```

## Run

```bash
ssh admin@10.42.0.15
cd ~/plant && .venv/bin/python variants/v2_adaptive/run.py
```

Options:

```bash
--heartbeat 3600    # seconds between pictures when nothing happens
--no-vision         # log readings only
```

## The adaptive rule

A reading counts as "changing" when soil moves by 20 counts or more, or air
temperature by 1 °C or more. One quiet sample is not enough to justify a
ten-minute gap, so the interval only reaches the slow end after three
consecutive readings that barely moved.

The thresholds live in `variant.h` as `ADAPTIVE_SOIL_DELTA`,
`ADAPTIVE_TEMP_DELTA` and `ADAPTIVE_STABLE_SAMPLES`.

## Where the rules live

Compiled into the firmware as `RULES_TEXT` in `variant.h`, because the ESP32 has
to evaluate them with no Pi present. The format is identical to
`config/configuration.txt`. A production build would read them from NVS or
LittleFS instead; that is a provisioning step, not a design change.

## Timing

Set the intervals in `config/configuration.txt`; no reflash needed.

```
sample_interval = 10     # ESP32 base interval
adaptive_fast = 10       # while the readings are moving
adaptive_slow = 600      # after three quiet samples
heartbeat = 3600         # Pi photograph when nothing happens
```

The Pi pushes `sample_interval` and the adaptive bounds over UART2 at startup.
`--heartbeat` overrides the heartbeat for a single run.
