# V0 — baseline

The naive version, and the reference every other rung is measured against.

## What it does

- ESP32 samples every 2 s, as fast as the DHT11 allows
- Every reading goes to the Pi over UART2
- The Pi evaluates `config/configuration.txt`, drives the buzzer, and writes
  `logs/events_log.txt`
- No camera, no sleeping, no adaptivity

## What it changes

Nothing. This is the starting point.

## Install

```bash
./install.sh v0_baseline
```

Builds the firmware with `variants/v0_baseline/variant.h`, flashes it on the Pi
at 115200 baud, and syncs the Pi code.

## Run

```bash
ssh admin@10.42.0.15
cd ~/plant && .venv/bin/python variants/v0_baseline/run.py
```

## Expected energy

Highest of the four. The Pi is awake and polling continuously and the ESP32
never sleeps.

## Timing

Set the sampling interval in `config/configuration.txt`; no reflash needed.

```
sample_interval = 2      # seconds, pushed to the ESP32 over UART2 at startup
```

The ESP32 keeps it in RTC memory, so it survives deep sleep but not a power
cycle. Leave the key out and the compiled default applies.
