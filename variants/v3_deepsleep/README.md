# V3 — deep sleep

The ESP32 sleeps between samples and the Pi is powered off. This is where the
headline number comes from.

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
cd ~/plant && .venv/bin/python variants/v3_wake.py
```

Use `--no-halt` while testing, or the Pi shuts down under you.

## Wiring this depends on

- ESP32 D25 (GPIO 25) → Pi physical pin 5, open-drain, 250 ms low pulse
- `POWER_OFF_ON_HALT=0` in `/boot/firmware/config.txt`, so the 5 V rail stays up
  while the Pi is halted and the ESP32 keeps running
- I2C must stay off: GPIO3 is both I2C1 SCL and the wake input

## Rule state across deep sleep

Deep sleep restarts the CPU, so `app_main` runs again on every wake. Two things
are kept in RTC memory to make that invisible:

- `s_violated[]` and `s_last_alert_ms[]` in `rules.c`, so a rule that is already
  violated does not re-alert on every wake
- `s_clock_ms` in `main.c`, a monotonic clock that survives sleep, because the
  CPU's own uptime restarts

The bring-up diagnostics (soil probe scan, three beeps) are skipped on a
deep-sleep wake. Three beeps a minute would be absurd and would wreck the
measurement.

## Timing

Set the intervals in `config/configuration.txt`.

```
sample_interval = 60     # ESP32 base interval
adaptive_fast = 60       # while the readings are moving
adaptive_slow = 600      # after three quiet samples
```

The Pi pushes these over UART2 whenever it is awake, and the ESP32 keeps them in
RTC memory across deep sleep. A power cycle falls back to the compiled defaults,
because the Pi is off and there is nobody to resend them.
