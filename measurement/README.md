# Measurement

The energy evaluation. Run on the laptop, with the Monsoon HVPM feeding the Pi
and the ESP32 taking its power from the Pi's 5 V rail — the system as it
actually runs, measured as one load.

**A capture is 180 s, three per variant.** That is long enough for every
variant's own behaviour to be representative, so the configs use the deployed
intervals — with one exception, V1's camera, explained below.

If the meter resets mid-capture, the summary's dropped-sample count will say
so. Check it before trusting a run.

## What this produces

| Run | Captures | Each | Total | Answers |
|---|---|---|---|---|
| `v0_baseline` | 3 | 180 s | 9 min | the baseline |
| `v1_duty` | 3 | 180 s | 9 min | fixed duty cycle |
| `v2_adaptive` | 3 | 180 s | 9 min | adaptive sampling, Pi still on |
| `v3_deepsleep` | 3 | 180 s | 9 min | the headline: Pi halted, ESP32 sleeping |
| `v3_event` | 3 | 180 s | 9 min | what one wake costs |

45 minutes of capture. With flashing and settling, about 90 minutes.

## The compression

At 180 s every variant's own behaviour is representative, so the configs use
the **deployed** intervals. There is one exception:

| Variant | Deployed | Measured | Factor |
|---|---|---|---|
| V0 | 2 s sampling | 2 s | none |
| V1 | camera every 300 s | **camera every 60 s** | 5× |
| V2 | 10 s fast / 600 s slow | same | none |
| V3 | 60 s fast / 600 s slow | same | none |

V1's camera fires every 300 s, which does not fit in a 180 s window — a capture
would contain one photo or none, and the mean would depend on which. At 60 s it
contains three.

**Only V1's figure needs rescaling.** Take the camera component out, divide it
by 5, put it back:

```
E/hour(deployed) = idle + (E/hour(measured) - idle) / 5
```

`idle` is V1 with the camera off. V0 is a reasonable proxy for that.

Everything else is measured at the deployed interval and needs no correction.

## Procedure, once per variant

Everything happens on the Pi. `--local` does not rsync, so the config has to
come from the repository — and it does, the measurement configs are committed.

**1. Pull.**

```bash
ssh admin@<pi>
cd ~/plant_git_test/smart-plant-monitor
git pull
```

**2. Prepare and flash.**

```bash
./measurement/run.sh v0_baseline
```

That copies `measurement/configs/v0_baseline.txt` over `config/configuration.txt`,
flashes the variant, and prints the capture command for the HVPM machine.

**3. Let it settle.** About three minutes. Powering up is a cold boot, which
means setup mode, which keeps the ESP32 awake — capture before this and you
measure the warm-up.

- V3: `deep sleep for ...` on the console
- V0/V1/V2: readings scrolling

**4. Capture, on the machine with the HVPM.** The command is printed by step 2:

```bash
for n in 1 2 3; do
  hvpm capture -o v0_baseline_${n}.csv --duration 180 --voltage 5 --json \
    | tee v0_baseline_${n}.json
  sleep 2
done
```

**5. Repeat** for `v1_duty`, `v2_adaptive`, `v3_deepsleep`, `v3_event`.

## The event run

`v3_event` is the same firmware and wiring as `v3_deepsleep`. The only
difference is a rule that fires on the first sample, so the Pi wakes once per
capture. The 30-minute cooldown means it cannot fire twice, so three captures
give three events.

**Reflash rather than pressing EN.** The flash bakes the firing rule into the
firmware, so it is deterministic. Copying the config alone leaves the quiet
rules in the ESP32's RTC, nothing fires, the Pi never wakes, and the new rules
never get pushed — a deadlock.

```bash
./measurement/run.sh v3_event
```

`run.sh` knows that `v3_event` flashes the `v3_deepsleep` firmware — only the
rules differ.

## After

```bash
python3 measurement/summarise.py
```

Prints mean current, run-to-run spread, average power and Wh/day per variant.

## What the numbers cannot say

You measured the system, not the parts, so you cannot state "the Pi is 97% of
the energy" as a measurement. You can state it as an inference from
`v2_adaptive` against `v3_deepsleep`, and you should say which it is.

If you want it measured, one extra run: unplug VIN from pin 4 and repeat
`v2_adaptive`. The difference is the ESP32's share. Two minutes and one cable.

## Before you start

**Null test.** With nothing connected, current should read essentially zero.

```bash
hvpm capture -o /tmp/null.csv --duration 10 --voltage 5
```

If it reads tens of milliamps, the calibration is wrong and every number after
this is garbage. Do not skip it.

**Check the current limit** against the Pi 4's ~3 A peak. A brownout
mid-capture wastes a run.

**Fix the Pi's clock.** It has no RTC and boots to the time saved at shutdown,
so `events_log.txt` is mis-timestamped until NTP catches up.
