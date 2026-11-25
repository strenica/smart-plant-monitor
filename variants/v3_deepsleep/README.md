# V3 — deep sleep

The ESP32 sleeps between samples and the Pi is powered off. This is where the
headline number comes from.

**This rung is frozen.** It produced the 268.8 mA in the report, so changing it
would make the report describe code that no longer exists. To deploy, or to
tune the sampling interval, use `variants/final/` instead: same behaviour, free
to change.

## What it changes

| | V2 | V3 |
|---|---|---|
| ESP32 between samples | awake | **deep sleep** |
| Pi | awake, logging | **off** |
| Pi wakes on | — | **ESP32 pulse on D25** |
| Pi job | log and photograph | **one photograph, then halt** |

The ESP32 wakes on its own timer, samples, evaluates the rules locally, and
only pulses the Pi's wake line when a rule fires. Between events the Pi draws
nothing at all.

## Install

```bash
./install.sh v3_deepsleep
```

## Run

The Pi side is not a daemon: it runs once per wake and halts.

```bash
ssh admin@10.42.0.15
cd ~/plant && .venv/bin/python variants/v3_deepsleep/run.py
```

Use `--no-halt` while testing, or the Pi shuts down under you.

## Logging

The Pi is off when the ESP32 takes a reading, so there is nobody to send it to.
Rather than drop it, the ESP32 keeps the last 96 readings in a ring buffer in
RTC memory — 1.6 h at the 60 s fast interval, 16 h at the 10 min slow one — and
replays them when the Pi next wakes.

The Pi asks first thing, before it touches the camera:

```
Pi  → log?
ESP → log t=60000 soil=1000 adc=2651 air_t=19.8 air_h=49
      log t=120000 soil=1000 adc=2650 air=ERR
      log end
Pi  → bye
```

The `log ` prefix is the only difference from a live reading, so the Pi parses
both with the same `parse_reading`. The ESP32 clears the buffer once it has
replayed it, so nothing is logged twice, and keeps it if the Pi never asks.

The handover needs both boards awake at once, which only happens in the window
after the ESP32 pulses the Pi. The ESP32 stays awake for that window, capped at
`PI_HANDOVER_MS` (120 s), and the Pi's `bye` ends it early — the real wait is
the Pi's boot time, not the ceiling.

The same session carries the rules the other way, so changing a rule needs no
reflash:

```
Pi  → rule clear
      rule 1 air_humidity > 50
      rule 2 air_temperature < 15
      rule 3 soil_humidity < 300
      rule save
ESP → rules ok ... rules saved 3
```

The ESP32 keeps the set in RTC memory, so it survives deep sleep. A power cycle
clears it and the firmware falls back to the text `install.sh` baked in. The
supervisor pushes the same set in setup mode, which is the faster path when you
are already pressing EN to reframe.

The log lines carry the Pi's clock, because that is when the Pi learned about
them. The ESP32's own sample times go in the summary line above them:

```
Thu Nov 19 12:36:45 CET 2026: v3 wake: 12 buffered readings, esp32 t=3600000..4260000 ms
```

## Wiring this depends on

- ESP32 D25 (GPIO 25) → Pi physical pin 5, open-drain, 250 ms low pulse
- ESP32 VIN → Pi physical pin 4 (5 V rail), **not** the Pi's USB port. The USB
  port loses power when the Pi halts, which cold-boots the ESP32, which reads a
  cold boot as setup mode, which pulses the Pi awake again. That loop is why V3
  saved nothing until the power was moved to the rail.
- `WAKE_ON_GPIO=1` in the **EEPROM** (`sudo rpi-eeprom-config --edit`), not
  `config.txt`. It is what makes `sudo poweroff` a low-power state that GPIO3
  can wake. `POWER_OFF_ON_HALT=0` alongside it is belt and braces: the PMIC-off
  state only applies when `WAKE_ON_GPIO=0`, and in that state nothing can wake
  the Pi. The 5 V rail is not a PMIC output, so the ESP32 keeps running across
  a halt either way.
- I2C must stay off: GPIO3 is both I2C1 SCL and the wake input

## Rule state across deep sleep

Deep sleep restarts the CPU, so `app_main` runs again on every wake. What is
kept in RTC memory to make that invisible:

- `s_violated[]` and `s_last_alert_ms[]` in `rules.c`, so a rule that is already
  violated does not re-alert on every wake
- `s_clock_ms` in `main.c`, a monotonic clock that survives sleep, because the
  CPU's own uptime restarts
- `s_interval_ms`, `s_fast_ms` and `s_slow_ms`, the intervals the Pi last sent
- `s_setup_mode`, so the Pi can ask whether the last boot was a cold one
- the 96-entry reading buffer in `sample_log.c`, which is what the Pi collects
  on wake

The bring-up diagnostics (soil probe scan, three beeps) are skipped on a
deep-sleep wake. Three beeps a minute would be absurd and would wreck the
measurement.

## Timing

Set the intervals in `config/configuration.txt`.

```
sample_interval = 60     # ESP32 base interval
adaptive_fast = 60       # while the readings are moving
adaptive_slow = 600      # after three quiet samples
log_max_lines = 0        # 0 = never trim logs/events_log.txt
```

The Pi pushes these over UART2 whenever it is awake, and the ESP32 keeps them in
RTC memory across deep sleep. A power cycle falls back to the compiled defaults,
because the Pi is off and there is nobody to resend them.

## Setup mode

Pressing EN on the ESP32 cold-boots it and puts it in setup mode. The camera
preview then runs instead of this variant's loop, so you can reframe. It works
whether the Pi is booting or already running: the ESP32 either answers `mode?`
or sends `setup` over UART2, and this loop exits with code 42 so the supervisor
can take over.

It ends on **save and apply**, or after five minutes with no browser, and the
loop starts afterwards either way.

This is the only variant where the Pi is off when you press EN, so the ESP32
wakes it and then stays awake until the Pi answers `mode run`. Sleeping in
between would leave the setup flag set and every later boot would land in the
preview again.

The wait expires, which is what makes deep-sleep measurement possible: a board
powered up with no Pi attached gives up after `SETUP_WAIT_MS` (120 s) and starts
sleeping, instead of staying awake forever and being measured as if it were
idle. Once the Pi has spoken the limit becomes `SETUP_HOLD_MS` (10 min), long
enough for the preview to finish.

The preview also holds off on opening the camera until a browser asks for a
frame, so a power cut costs two minutes of idle Pi rather than five minutes of
camera. Pressing EN and opening the page is what starts it. It is also the only moment the two nodes are awake together,
which makes it the only chance to hand the ESP32 the intervals from
`configuration.txt` — the supervisor does that just before `mode run`. Change
the interval by pressing EN, editing the config, and applying.

```bash
.venv/bin/python tools/supervisor.py --variant v3_deepsleep
```

is what the systemd unit runs; it asks the ESP32 which mode to use.
