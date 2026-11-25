# Final build

The system as deployed. This is the one to install.

```bash
./install.sh final
```

## What it does

The ESP32 samples every 60 s, evaluates the rules itself, and deep-sleeps
between samples. It wakes the Pi only when a rule fires, or once a day
regardless. The Pi boots, collects the readings the ESP32 buffered while it was
off, photographs the plant, runs the vision pipeline, appends to the log and
halts.

Between events the Pi draws nothing. A halted Pi 4 still draws 1.34 W, and that
is the floor this design sits on.

## How it differs from `v3_deepsleep`

Nothing, in behaviour. The firmware is the same code with the same values.

The difference is what the folder is for. `v3_deepsleep` is a **measurement
rung**: it produced the 268.8 mA in the report, and it is frozen so that number
stays reproducible. This folder is the **deployment**, and it is free to change.

If you tune the sampling interval, the thresholds or the heartbeat, do it here.
Do not edit `v3_deepsleep`, or the report stops describing the code.

## Timing

| Setting | Value | Where |
|---|---|---|
| sample interval | 60 s | `SAMPLE_INTERVAL_MS` |
| back off to | 600 s after 3 quiet samples | `ADAPTIVE_SLOW_MS` |
| back to | 60 s on the first reading that moves | `ADAPTIVE_FAST_MS` |
| heartbeat | once a day | `HEARTBEAT_MS` |

All four can be overridden at runtime from `config/configuration.txt` without a
reflash, because the Pi pushes them over UART2 whenever the ESP32 is awake.

## The rules

Baked in from `config/configuration.txt` at install time as a fallback, and
pushed over UART2 on every wake, so changing a rule needs no reflash.

## Wake the Pi by hand

The Pi halts after each capture. Press EN on the ESP32 to wake it, or wait for
the next rule or the daily heartbeat.
