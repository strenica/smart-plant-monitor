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

## 1. The measurement matrix

Thirteen runs, roughly five minutes each including setup. If you are short on
time, the **bold** ones are the core comparison and the rest are extras.

### ESP32 alone — `--voltage 3.3`

Disconnect the ESP32 from the Pi first. It must be powered only by the HVPM.

| # | Run | Duration | What it tells you |
|---|---|---|---|
| **E1** | ESP32 idle, no sensors read | 60 s | The floor. Everything else is measured against this. |
| **E2** | V0 behaviour: sensors every 2 s | 60 s | Cost of aggressive sampling |
| **E3** | V1 behaviour: sensors every 60 s | 60 s | Cost of duty cycling |
| **E4** | V3 behaviour: deep sleep, 60 s wake | 180 s | The headline number. Needs several wake cycles to average. |
| E5 | Buzzer firing continuously | 30 s | Cost of one notification |

E4 needs a long capture because the ESP32 is asleep for most of it. A 60 s
window might catch only one wake and the average will be dominated by the
transient. Three minutes gives you three cycles.

### Pi alone — `--voltage 5`

The Pi must be powered only by the HVPM. Nothing else on its USB ports.

| # | Run | Duration | What it tells you |
|---|---|---|---|
| **P1** | Pi halted (`sudo poweroff`, then measure) | 60 s | The V3 idle floor — what "off" actually costs |
| **P2** | Pi booted, no services running | 60 s | Idle floor with the OS up |
| **P3** | `v0_baseline` running | 120 s | Continuous polling |
| **P4** | `v1_duty` running | 120 s | Fixed duty cycle |
| **P5** | `v2_adaptive` running | 120 s | Adaptive sampling |
| P6 | Boot from power-on | 60 s | Inrush — start the capture, then apply power |
| P7 | Camera streaming, nothing else | 60 s | Camera contribution |

P1 is the one people forget and it is the most interesting: a halted Pi 4 still
draws current because the 5 V rail stays up (`POWER_OFF_ON_HALT=0`). That number
is the whole justification for V3's design, so measure it properly.

P7 minus P2 is the camera's share. No extra hardware needed.

### System total — `--voltage 5`

| # | Run | Duration | What it tells you |
|---|---|---|---|
| S1 | Pi with the ESP32 on its USB | 120 s | Cross-check: should be close to P4 + E3 |

If S1 does not roughly equal the sum of its parts, something in your per-component
methodology is wrong and you need to know that before you present it.

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

**USB passthrough.** For S1 the ESP32 is on the Pi's USB, so the Pi needs USB
data through the monitor: `--usb-passthrough on`. It adds noise, so do not use
it for the runs that do not need it.

**Dropped samples.** The summary reports them. Non-zero means the capture is
unreliable — usually USB contention or the laptop sleeping. Re-run it.

**Wifi is a large, variable load.** The Pi's wifi can be a significant fraction
of idle draw and it fluctuates with traffic. Decide once whether it is on, state
it in the report, and keep it constant. Measuring with it on and not saying so
is the easiest way to get caught out in questions.

**Thermal throttling.** Long runs at load make the Pi throttle, which changes
power draw mid-capture. Keep runs short and the Pi cool, and note if the fan
spun up.

**The ESP32 must be disconnected from the Pi** for the ESP32 runs. If it is
still on the Pi's USB it is being powered by the Pi, and you are measuring the
Pi.

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
