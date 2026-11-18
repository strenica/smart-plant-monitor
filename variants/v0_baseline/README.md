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
log_max_lines = 50000    # trim logs/events_log.txt to this many lines, 0 = keep all
```

The ESP32 keeps it in RTC memory, so it survives deep sleep but not a power
cycle. Leave the key out and the compiled default applies.

## Setup mode

Pressing EN on the ESP32 cold-boots it and puts it in setup mode. The camera
preview then runs instead of this variant's loop, so you can reframe. It works
whether the Pi is booting or already running: the ESP32 either answers `mode?`
or sends `setup` over UART2, and this loop exits with code 42 so the supervisor
can take over.

It ends on **save and apply**, or after five minutes with no browser, and the
loop starts afterwards either way.

```bash
.venv/bin/python tools/supervisor.py --variant v0_baseline
```

is what the systemd unit runs; it asks the ESP32 which mode to use.
