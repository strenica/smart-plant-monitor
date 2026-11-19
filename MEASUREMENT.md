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
- **ESP32:** USB cable, and you will be disconnecting it from the Pi.
- A way to keep the laptop's own power separate — the laptop must not be powered
  from the HVPM.

---

## 1. What to measure, per variant

Each variant needs three numbers: what the ESP32 draws, what the Pi draws, and
what the pair draws together. The runs are grouped by variant so you can do one
rung end to end and write it down before moving to the next.

**Flash the variant first.** `./install.sh <variant>` puts the right firmware on
the ESP32 and the right script on the Pi. The ESP32 keeps its firmware when you
unplug it, so flash, then disconnect, then measure.

**Before any E run:** unplug VIN from Pi pin 4 **and** the USB cable. The ESP32
must be powered only by the HVPM.

**Then wait two minutes before capturing.** Powering the ESP32 up is a cold
boot, and a cold boot means setup mode, which keeps the node awake. With no Pi
attached it gives up after `SETUP_WAIT_MS` (120 s) and starts deep sleeping. A
capture started before that measures an awake ESP32 and reports it as V3's
deep-sleep current — the one number the whole project rests on. Watch for
`setup mode: no Pi after 120000 ms, back to monitoring` on the console, or just
wait two minutes.

**The CP2102 USB bridge never sleeps.** It draws about 10 mA whenever it has
5 V, which is roughly a hundred times the ESP32's deep-sleep current. Powered
through VIN with the USB cable out, the bridge is unpowered and E4 measures the
chip. Leave USB connected and E4 measures the bridge instead. Check which one
you did before writing the number down — this is the single easiest way to make
V3 look like it saved nothing.

**Before any P run:** the Pi must be powered only by the HVPM. Nothing on its
USB ports, and nothing on the 5 V rail either.

### V0 baseline

| # | Run | HVPM voltage | Duration | Gives you |
|---|---|---|---|---|
| **E2** | ESP32 alone, V0 firmware, sensors every 2 s | 3.3 | 60 s | the ESP32's share |
| **P3** | Pi alone, `v0_baseline` running | 5 | 120 s | the Pi's share |
| S1 | both, ESP32 on the Pi's 5 V rail | 5 | 120 s | system total, and the cross-check |

S1 should land close to E2 + P3. If it does not, the per-component method is
wrong and every later number inherits the error.

### V1 fixed duty cycle

| # | Run | HVPM voltage | Duration | Gives you |
|---|---|---|---|---|
| **E3** | ESP32 alone, V1 firmware, sensors every 60 s | 3.3 | 60 s | the ESP32's share |
| **P4** | Pi alone, `v1_duty` running | 5 | 120 s | the Pi's share |

E3 - E2 is what the 30x slower sampling bought. P4 - P3 is the camera duty
cycle plus the slower polling.

### V2 adaptive sampling

| # | Run | HVPM voltage | Duration | Gives you |
|---|---|---|---|---|
| **E6** | ESP32 alone, V2 firmware, adaptive, awake | 3.3 | 180 s | the ESP32's share |
| **P5** | Pi alone, `v2_adaptive` running | 5 | 120 s | the Pi's share |

E6 - E3 is what adaptive sampling bought on the ESP32. This is the run that
separates "adaptive" from "deep sleep"; without it, E3 to E4 bundles both and
you cannot say which did the work.

### V3 deep sleep

| # | Run | HVPM voltage | Duration | Gives you |
|---|---|---|---|---|
| **E4** | ESP32 alone, V3 firmware, deep sleep | 3.3 | 180 s | the ESP32's share |
| **P1** | Pi alone, halted | 5 | 60 s | what "off" actually costs |
| **S4** | both, V3 running | 5 | 600 s | the headline number |

E4 - E6 is what deep sleep bought. P1 is the number the whole design rests on: a
halted Pi 4 still draws current because the 5 V rail stays up
(`POWER_OFF_ON_HALT=0`). Measure it properly.

S4 needs ten minutes because the Pi is off for most of it and the ESP32 wakes
every 60 s. A short capture catches one event and reports the transient as if it
were the average.

### Not per-variant

| # | Run | HVPM voltage | Duration | Gives you |
|---|---|---|---|---|
| E1 | ESP32 idle, no sensors read | 3.3 | 60 s | the floor everything is measured against |
| E5 | buzzer firing continuously | 3.3 | 30 s | cost of one notification |
| P2 | Pi booted, no services | 5 | 60 s | the OS floor |
| P6 | Pi boot from power-on | 5 | 60 s | inrush |
| P7 | camera streaming, nothing else | 5 | 60 s | the camera's share (P7 - P2) |

### If you only have time for eleven runs

**E1, E2, E3, E6, E4, P1, P2, P3, P4, P5, S4.**

That is the full ESP32 ladder, the full Pi ladder, and the V3 headline number.
E1 and P2 are not optional: the email asks for idle consumption explicitly, and
without a floor you cannot say what sensing costs above it.

The other four (E5, P6, P7, S1) make the discussion richer, not the comparison
possible.

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

**USB passthrough.** The ESP32 is on the Pi's 5 V rail, not its USB port, so S1
does not need USB data through the monitor for it. Unplug the ESP32's USB cable
for S1 anyway: with both VIN and USB connected there are two power paths and the
split between them is not something you can see from the meter.

**Dropped samples.** The summary reports them. Non-zero means the capture is
unreliable — usually USB contention or the laptop sleeping. Re-run it.

**Wifi is a large, variable load.** The Pi's wifi can be a significant fraction
of idle draw and it fluctuates with traffic. Decide once whether it is on, state
it in the report, and keep it constant. Measuring with it on and not saying so
is the easiest way to get caught out in questions.

**Thermal throttling.** Long runs at load make the Pi throttle, which changes
power draw mid-capture. Keep runs short and the Pi cool, and note if the fan
spun up.

**The ESP32 must be disconnected from the Pi** for the ESP32 runs. That means
both wires: VIN off pin 4 and the USB cable out. Either one left connected and
the Pi is powering it, so you are measuring the Pi.

**Do not let the laptop sleep** during a capture. It drops the USB device.

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

1. **A table**: rows = V0/V1/V2/V3, columns = ESP32 mWh/h, Pi mWh/h, total,
   and the ratio against V0. That single table answers the "comparative
   analysis" requirement.
2. **Idle vs active**: E1 vs E2, and P2 vs P3. This is the "idle consumption
   and energy required for sensing" the email asks for explicitly.
3. **One plot per variant** from `hvpm plot`, showing the duty pattern. V3's
   plot — flat near zero with periodic spikes — is the most persuasive single
   image you will have.
4. **The camera share**: P7 − P2, stated as a percentage of the Pi's total.
   That justifies event-triggered capture over periodic.

### The comparison the email asks for

"Comparative analysis of your solution and at least one alternative" is already
built into the project: V0 is the naive alternative, V1–V3 are the solutions.
Present it as a ladder with measured numbers at each rung, not as four separate
projects. The interesting claim is not "V3 uses less" but "V3 uses N× less, and
here is which mechanism bought which part of that" — deep sleep versus duty
cycling versus adaptive sampling each contribute a measurable share.

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
