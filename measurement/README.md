# Measurement

The energy evaluation. Everything here is run on the laptop, with the Monsoon
HVPM feeding the Pi and the ESP32 taking its power from the Pi's 5 V rail — the
system as it actually runs, measured as one load.

The Monsoon resets every minute, so a capture is 60 s. Longer behaviour is
covered by repeating the capture, not by making it longer.

## What this produces

| Run | Captures | Each | Total | Answers |
|---|---|---|---|---|
| `v0_baseline` | 3 | 60 s | 3 min | the baseline |
| `v1_duty` | 5 | 60 s | 5 min | fixed duty cycle |
| `v2_adaptive` | 5 | 60 s | 5 min | adaptive sampling, Pi still on |
| `v3_deepsleep` | 10 | 60 s | 10 min | the headline: Pi halted, ESP32 sleeping |
| `v3_event` | 3 | 60 s | 3 min | what one wake costs |

26 minutes of capture. With flashing and settling, about an hour.

## Before you start

**1. Null test.** With nothing connected, current should read essentially zero.

```bash
hvpm capture -o /tmp/null.csv --duration 10 --voltage 5
```

If it reads tens of milliamps, the calibration is wrong and every number after
this is garbage. Do not skip it.

**2. Check the current limit** against the Pi 4's ~3 A peak. A brownout
mid-capture wastes a run.

**3. Fix the Pi's clock.** It has no RTC and boots to the time saved at
shutdown, so `events_log.txt` is mis-timestamped until NTP catches up.

```bash
ssh admin@<pi> date
```

## Procedure, once per variant

**Steps 1-4 are on the Pi, step 5 is on the laptop** (the HVPM is attached
there). `install.sh --local` does not rsync, so a config copied on the laptop
never reaches the Pi. Running `./install.sh <variant>` from the laptop instead
*does* rsync and would overwrite the Pi's config with the laptop's — which is
fine, but then the copy has to happen on the laptop. Pick one machine for the
config and stay on it.

**1. Get the run book onto the Pi.**

```bash
ssh admin@<pi>
cd ~/plant_git_test/smart-plant-monitor
git pull
```

**2. Put the measurement config in place.**

```bash
cp measurement/configs/v0_baseline.txt config/configuration.txt
```

These configs carry the same timing values as the variant's compiled defaults,
written out rather than commented so a stale value cannot survive in the ESP32's
RTC memory. Their rules never fire, which isolates the cost of monitoring.

**3. Flash the variant.** This also resets the ESP32, clearing its RTC.

```bash
./install.sh v0_baseline --local
```

**4. Let it settle.** Powering up is a cold boot, which means setup mode, which
keeps the ESP32 awake. Wait until the variant is actually running:

- V3: `deep sleep for ...` on the console
- V0/V1/V2: readings scrolling

About three minutes. **Do not capture before this** — you would measure the
warm-up.

**5. Capture, on the laptop.**

```bash
./measurement/capture.sh v0_baseline 3
```

**6. Repeat** for `v1_duty` (5), `v2_adaptive` (5), `v3_deepsleep` (10).

## The event run

`v3_event` is the same firmware and wiring as `v3_deepsleep`. The only
difference is a rule that fires on the first sample, so the Pi wakes exactly
once per capture.

```bash
cp measurement/configs/v3_event.txt config/configuration.txt
./measurement/capture.sh v3_event 3
```

The difference between `v3_deepsleep` and `v3_event` is the cost of one wake:
pulse, boot, camera, vision, halt. That is the number that makes V3's design
argument concrete, and it is the one nobody else will have.

## After

```bash
python3 measurement/summarise.py
```

Prints mean current, run-to-run spread, average power and Wh/day per variant.

## Two traps

**V1's camera fires once per 5 minutes.** A single 60 s capture either contains
that spike or does not, and the spike roughly doubles the mean. That is why V1
gets 5 consecutive captures covering a full 5-minute period, averaged. One
capture of V1 is meaningless.

**V3 wakes every 60 s.** A 60 s window catches exactly one wake, and whether it
lands at the start or the end swings the mean. Ten captures average that out.

## What the numbers cannot say

You measured the system, not the parts, so you cannot state "the Pi is 97% of
the energy" as a measurement. You can state it as an inference from
`v2_adaptive` against `v3_deepsleep`, and you should say which it is.

If you want it measured, one extra run: unplug VIN from pin 4 and repeat
`v2_adaptive`. The difference is the ESP32's share. Two minutes and one cable.
