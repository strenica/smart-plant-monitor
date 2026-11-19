# Energy measurement with the Monsoon HVPM

How to get the numbers the presentation needs. Written to be followed at the
bench, in order, without having to think about it.

The instrument is a **single-channel** power monitor: it powers one load and
measures what that load draws. Everything here follows from that — per-component
energy means sequential runs, not simultaneous measurement.

---

## 0. Before you capture anything

Do these in order. Each one catches a different failure, and finding it now
costs a minute instead of an afternoon.

```bash
# 1. USB permissions. Without this every command fails with a permission error.
sudo cp ~/Desktop/projects/hvpm-linux/udev/99-monsoon-powermonitor.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
# then unplug and replug the monitor

# 2. Is the setup sane? Checks libusb, the udev rule, and whether a unit is seen.
hvpm doctor

# 3. What is actually attached? Note the serial number.
hvpm info

# 4. Does the CLI work at all, independent of hardware?
hvpm capture --simulate --duration 1 -o /tmp/sim.csv

# 5. THE IMPORTANT ONE: a real capture with nothing connected.
hvpm capture -o /tmp/null.csv --duration 10 --voltage 3.3
```

Step 5 is the sanity check that matters. **With no load attached the current
should read essentially zero.** If it reads tens of milliamps, the calibration
or the channel is wrong and every number after this is garbage. Do not skip it.

If `hvpm doctor` or `hvpm info` fails, stop and fix that first — the real
backend in that repo has never been run against physical hardware, so this is
the step most likely to surprise you.

### Cables you need before you start

- **Pi 4:** the HVPM's output has to reach the Pi's USB-C power input. Check you
  have that cable *before* you go to the lab. This is the usual blocker.
- **ESP32:** nothing extra. It stays wired to the Pi exactly as it runs: VIN on
  pin 4 for power, USB for the console. Both are part of the system total.
- A way to keep the laptop's own power separate — the laptop must not be powered
  from the HVPM.

---

## 1. What to measure

Both boards are measured together, with the HVPM feeding the Pi and the ESP32
taking its power from the Pi's 5 V rail. That is one cable, it is how the system
actually runs, and it means the numbers are the system's rather than a sum of
parts that were never measured together.

Six runs, about an hour of capture.

| # | Run | Duration | What it tells you |
|---|---|---|---|
| **S0** | Pi booted, no services, ESP32 idle | 120 s | the floor: OS up, nothing sampling |
| **S1** | V0 running | 300 s | the baseline |
| **S2** | V1 running | 600 s | fixed duty cycle |
| **S3** | V2 running | 600 s | adaptive sampling, Pi still on |
| **S4** | V3 running, no rule fires | 600 s | the headline: Pi halted, ESP32 sleeping |
| **S5** | V3 running, one rule fires | 600 s | what one event costs |

S4 and S5 are the same firmware and the same wiring. The only difference is
whether you trigger a rule during the capture, and the difference between them
is the cost of one wake: Pi boot, camera, vision, halt.

### Triggering a rule on demand

| Rule | How |
|---|---|
| 1 `air_humidity > 50` | breathe on the DHT11 |
| 2 `air_temperature < 15` | ice pack next to it |
| 3 `soil_humidity < 300` | probe in dry air |

Breathe on the DHT11 about 60 s into the capture, so the Pi's boot and the
camera capture both land inside the window. Watch the console for
`rule 1 fired` to confirm it actually triggered.

### What this gives you

- the comparison across all four variants, which is the requirement
- idle (S0) and the sensing delta (S1 - S0)
- the cost of one event (S5 - S4), which is the number that makes V3's design
  argument concrete

### What it does not give you

The split between the Pi and the ESP32. The design argument is that the Pi is
almost all of the energy, and S3 against S4 supports that by inference, but it
is not measured.

If you want it measured, one extra run: unplug VIN from pin 4 and repeat S3. The
difference is the ESP32's share. Two minutes and one cable, and it turns the
central claim from an inference into a measurement.

### Two things to know about the wiring

**The CP2102 is in the total.** The ESP32's USB cable is plugged into the Pi, so
the bridge draws its ~10 mA from the Pi's USB port and is counted. That is
honest, because it is part of the system as deployed.

**It switches off in V3.** The Pi's USB port is behind a switch that opens when
the Pi halts, so in S4 and S5 the bridge is unpowered and the ESP32 runs from
the 5 V rail alone. V3's idle number is therefore slightly flattered relative to
the others, by about 50 mW. Say so rather than letting someone find it.

### Before every run: let it settle

Powering up is a cold boot, and a cold boot means setup mode, which keeps the
ESP32 awake. The system has to reach its steady state before the capture starts,
or you measure the warm-up instead of the system.

**With the supervisor (the normal path).** The Pi boots into the camera preview,
waits two minutes for a browser, then starts the variant. The camera never opens,
because nobody connects. Wait until the variant is actually running — for V3
that means `deep sleep for ...` on the console, for the others it means readings
scrolling. About three minutes from power-on.

**Without the supervisor (faster).** Stop the unit and run the variant directly,
which skips the preview entirely:

```bash
sudo systemctl stop plant-monitor
cd ~/plant_git_test/smart-plant-monitor
.venv/bin/python variants/v3_deepsleep/run.py
```

Nothing sends `mode?`, so setup mode expires after `SETUP_WAIT_MS` (120 s) and
the node starts sleeping. About three minutes from power-on.

Either way, **do not start the capture until the node is in its steady state.**
For V3, if you never see `deep sleep for ...`, it is still awake and the run is
worthless — it will report an awake ESP32 as V3's deep-sleep current.

**Check the HVPM's current limit against the Pi 4's ~3 A peak** before
connecting it. A brownout mid-capture wastes a run.

---

## 2. What to write down for every single run

Record these in a spreadsheet as you go, not afterwards from memory. The CSV
files alone are not enough — you will not remember which was which.

| Field | Example |
|---|---|
| Run ID | `E4` |
| Variant / config | `v3_deepsleep`, 60 s wake |
| What was connected | `ESP32 only, sensors on, Pi disconnected` |
| Voltage set | `3.3` |
| Duration | `180` |
| Mean current | from the summary |
| Min / max current | from the summary |
| Mean voltage | from the summary |
| Charge (mAh) | from the summary |
| Energy (mWh) | from the summary |
| Dropped samples | **must be 0** |
| Wifi on the Pi? | `off` |
| Anything odd | `Pi got warm, fan spun up at 90 s` |

`hvpm capture` prints all of this at the end. Add `--json` if you want to paste
it straight into a spreadsheet.

**Keep the CSV files.** Name them `<runid>_<variant>_<what>.csv`, e.g.
`E4_v3_esp32_deepsleep.csv`. They go in the repo or at least in the report
appendix, and the plots come from them.

### The one rule that makes the comparison valid

**Every variant must be measured under identical conditions.** Same voltage,
same duration, same sensors attached, same wifi state, same ambient temperature.
If V0 was measured with wifi on and V3 with it off, the comparison is worthless
and a reviewer will spot it.

Pick a condition set and write it down once, then follow it for all four.

---

## 3. Gotchas that will waste your time

**Current limits.** The Pi 4 peaks around 3 A. Set `--powerup-limit` and
`--runtime-limit` above that or the Pi browns out mid-capture and you get a
truncated run that looks like a crash. Check the HVPM's own rating first.

**Dropped samples.** The summary reports them. Non-zero means the capture is
unreliable — usually USB contention or the laptop sleeping. Re-run it.

**Wifi is a large, variable load.** The Pi's wifi can be a significant fraction
of idle draw and it fluctuates with traffic. Decide once whether it is on, state
it in the report, and keep it constant. Measuring with it on and not saying so
is the easiest way to get caught out in questions.

**Thermal throttling.** Long runs at load make the Pi throttle, which changes
power draw mid-capture. Keep runs short and the Pi cool, and note if the fan
spun up.

**Do not let the laptop sleep** during a capture. It drops the USB device.

**The Pi's clock must be right before a run.** It has no RTC, so it boots to the
time saved at shutdown and can be hours out. Every line in `events_log.txt` is
mis-timestamped until NTP fixes it. Check `date` before starting, and note the
offset if it is wrong.

---

## 4. Turning the numbers into report content

The summary gives you mWh for the capture window. Convert to a rate so runs of
different lengths are comparable:

```
average power (mW) = energy_mwh / duration_s * 3600
```

Then per variant, per hour:

```
energy per hour (mWh) = average power (mW) * 1
```

What the presentation actually needs:

1. **A table**: rows = V0/V1/V2/V3, columns = average power, mWh/h, and the
   ratio against V0. That single table answers the "comparative analysis"
   requirement.
2. **Idle vs active**: S0 vs S1. This is the "idle consumption and energy
   required for sensing" the email asks for explicitly.
3. **The cost of one event**: S5 − S4. This is the number that makes V3's
   design argument concrete, and it is the one nobody else will have.
4. **One plot per variant** from `hvpm plot`, showing the duty pattern. V3's
   plot — flat near zero with periodic spikes — is the most persuasive single
   image you will have.

### The comparison the email asks for

"Comparative analysis of your solution and at least one alternative" is already
built into the project: V0 is the naive alternative, V1–V3 are the solutions.
Present it as a ladder with measured numbers at each rung, not as four separate
projects. The interesting claim is not "V3 uses less" but "V3 uses N× less, and
here is which mechanism bought which part of that" — deep sleep versus duty
cycling versus adaptive sampling each contribute a measurable share.

### The one claim you cannot make

You measured the system, not the parts, so you cannot state "the Pi is 97% of
the energy" as a measurement. You can state it as an inference from S3 against
S4, and you should say which it is. If you want the measurement, the extra run
in §1 gives it to you for two minutes and one cable.

---

## 5. If the meter does not work

Budget an hour for the possibility that `hvpm doctor` fails or the real backend
misbehaves — it has never been exercised against hardware. If it cannot be made
to work in that hour, fall back to:

- **Datasheet and vendor figures** for the ESP32 (deep sleep current, active
  current) and the Pi 4 (idle and load power), clearly labelled as such.
- **A USB power meter** if one is available, for the Pi's total draw.
- **Software-side proxies**: count samples taken and camera frames captured per
  hour per variant, and present the *reduction in work* rather than the
  reduction in energy. That is still a defensible result, and it is honest.

Say plainly in the presentation which numbers are measured and which are
estimated. A labelled estimate is fine; an unlabelled one is not.
