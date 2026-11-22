# Smart Plant Monitoring System — Build Plan

> **This is the design record, written before implementation.** Several ideas
> here were dropped or changed once they met the hardware. The code is the
> authority, and [What changed during the build](#12-what-changed-during-the-build)
> at the end lists every divergence. For what the system actually does, read the
> [README](README.md).

Four firmware variants of the same system, each adding one energy-saving technique,
so the report can plot a measured energy/accuracy tradeoff instead of four unrelated
programs.

Hardware: ESP32 (sensor node) + Raspberry Pi 4 (vision + orchestration), DHT11,
DFRobot SEN0114 **resistive** soil moisture probe, Pi Camera Module 3 (CSI
ribbon), Grove passive buzzer, Monsoon HVPM for energy measurement.

---

## 1. The core idea

All four variants share the same config parser, event logger, buzzer semantics and
log format. **Only the scheduling and power layer changes.** That is what makes the
energy numbers comparable.

The progression is not "sleep more". It is **moving the decision from the expensive
node to the cheap one**:

```
V0  Pi decides everything, always awake      → Pi is the bottleneck
V1  same split, slower fixed intervals       → still Pi-bound
V2  rules move to ESP32, Pi wakes on event   → Pi stops being always-on
V3  ESP32 deep sleeps, Pi powered off        → Pi is off most of the time
```

That narrative is the report's technical contribution.

---

## 2. Why the Pi is the whole game

Typical figures, to be replaced by HVPM measurements:

| Component | State | Current | Power |
|---|---|---|---|
| Pi 4 | idle, no peripherals | ~600 mA @ 5 V | ~3.0 W |
| Pi 4 | camera streaming | ~750 mA @ 5 V | ~3.75 W |
| Pi 4 | running CV | up to 1.2 A @ 5 V | ~6 W |
| ESP32 WROOM | active, WiFi off, 80 MHz | ~20–25 mA | ~0.1 W |
| ESP32 WROOM | light sleep | ~0.8 mA | ~4 mW |
| ESP32 WROOM | deep sleep | ~10 µA | ~0.05 mW |
| DHT11 | active | ~0.5–1 mA | — |
| Soil sensor | active | ~5 mA | power-gateable to 0 |
| Buzzer | active | ~30 mA | — |

Pi at 3 W for 24 h = **72 Wh/day**. ESP32 at 20 mA for 24 h = **0.48 Wh/day**.
Ratio ≈ 150:1.

So: shaving ESP32 sleep current saves milliwatts. Powering the Pi off saves watts.
**V2 and V3 spend their complexity budget on the Pi side.**

Expected headline: V3 powers the Pi off ~95% of the time → ~3.7 Wh/day total,
roughly **18–20× less than V0**. The HVPM will replace this estimate with a curve.

---

## 3. The four variants

The only firmware difference between two variants is `variants/<name>/variant.h`.
Everything else is shared, so the diff between two rungs is a dozen lines and the
comparison stays honest.

| | V0 baseline | V1 fixed duty | V2 adaptive | V3 deep sleep |
|---|---|---|---|---|
| ESP32 sample interval | 2 s | 60 s | 10 s → 10 min | 60 s → 10 min |
| Adaptive | no | no | yes | yes |
| ESP32 between samples | awake | awake | awake | **deep sleep** |
| Rules evaluated on | Pi | Pi | **ESP32** | **ESP32** |
| Buzzer driven by | Pi | Pi | **ESP32** | **ESP32** |
| Pi | always on | always on | always on | **halted between events** |
| Pi wakes on | — | — | — | ESP32 pulse on D25 |
| Camera | never | every 5 min | on event + 1 h heartbeat | one shot per wake |
| Readings reach the log | live stream | live stream | live stream | RTC buffer, pulled on wake |

### V0 — Baseline (naive)

- Pi always awake, reads the ESP32 over UART2 every 2 s
- Pi evaluates `configuration.txt` and drives the buzzer over UART
- No camera at all
- ESP32 is a sensor bridge: read DHT11 + soil, print one line, listen for commands
- No sleep anywhere

Purpose: reference point. Worst-case energy, best-case latency.

### V1 — Fixed duty cycle

- Same split as V0
- ESP32 samples every 60 s and stays awake between reads (`vTaskDelay`)
- Pi takes a picture every 5 min
- Fixed intervals, no adaptivity

Purpose: isolates the cost of the naive sampling rate. Shows how much of V0's
energy is pure waste.

### V2 — Adaptive sampling + rules on the ESP32

- The ESP32 evaluates the rules and buzzes on its own; the Pi is out of the
  decision loop
- Interval backs off to 10 min after three quiet samples, returns to 10 s when
  soil moves >= 20 raw or temperature >= 1.0 C
- Pi stays awake, logs readings, photographs on an event plus a 1 h heartbeat
- Rules reach the ESP32 over UART2 and live in RTC memory

Purpose: the "smart" version. Most of the energy win, most of the interesting design.

### V3 — Deep sleep

- ESP32 deep sleeps between samples; the main CPU wakes on a timer
- Rules and the last 96 readings live in RTC memory
- Pi **halted** between events, woken by a 250 ms low pulse on GPIO3
- One photograph per wake, then halt
- Buzzer edge-triggered only

Purpose: headline number. Costs boot latency (~20-30 s per Pi wake), which the
report must argue is acceptable for a plant monitor.

---

## 4. Shared contract (identical in all four)

This is the part that must not drift, or the comparison is meaningless.

### Reading

```c
struct Reading {
  uint32_t ms;          // uptime
  float    air_temp_c;
  float    air_humidity_pct;
  int      soil_raw;    // 0..1000
};
```

### Rule format

```
1: air_humidity > 50
2: air_temperature < 15
3: soil_humidity < 300
```

Rule number N → buzz N times. Fields: `air_humidity`, `air_temperature`,
`soil_humidity`. Operators: `<`, `>`, `<=`, `>=`.

### Buzzer semantics

Edge-triggered: buzz on transition *into* violation, not every sample. Plus a
re-alert cooldown (default 30 min) so a persistent condition re-alerts without
buzzing continuously.

Without this, a dry pot buzzes forever. The report should argue for it explicitly.

### Log format

Exactly as the spec:

```
Mon Oct 21 14:04:30 CEST 2024: air_humidity = 48
Mon Oct 21 14:04:30 CEST 2024: air_temperature = 13
Mon Oct 21 14:04:31 CEST 2024: buzzer 2
```

---

## 5. Gotchas to design around now

**DHT11 is capped at ~1 Hz.** V0's "every 2 s" is already near the sensor limit, so
V0's baseline is honest but V1's 60 s is where real savings begin. Do not claim
sub-second sampling.

**The USB-UART bridge never sleeps.** CP2102/CH340 on a dev board draws ~5–10 mA
continuously and cannot be put to sleep. That will dominate your deep-sleep current
and make the ESP32 look far worse than the datasheet. Either measure it and subtract
it explicitly, or use a bare module / a board with a native-USB ESP32-S3. **The HVPM
will show this immediately** — it is exactly the kind of thing a multimeter average
hides.

**Time source.** The log format needs wall-clock time, and the ESP32 has no RTC
battery. The Pi stamps every line with its own clock, so the ESP32 never needs
wall time at all: its `t=` field is a synthetic millisecond counter that survives
deep sleep and exists only to drive the rule cooldown. The cost is that a V3
backlog is stamped with the time the Pi collected it rather than the time it was
measured, which is why the ESP32's own sample times go in the summary line above
the measurements.

**ESP32 power comes from the 5 V rail, which is live whenever the supply is.**
5 V on the header is not a PMIC output, so it stays up across a halt whatever the
EEPROM says. The ESP32 keeps running and can wake the Pi back up, with no
independent supply needed. What the EEPROM does control is whether the Pi can be
woken at all: `WAKE_ON_GPIO=1` makes `sudo poweroff` a low-power state that GPIO3
can wake. Cutting the 5 V rail with a MOSFET would drop the ESP32 with it, so
that route needs the ESP32 on its own rail.

Note that the ESP32 has to be fed from the 5 V rail (pin 4), not the Pi's USB
port. The USB port is behind a switch that opens on halt, so powering from it
cold-boots the ESP32 every time the Pi goes down, and a cold boot means setup
mode, which pulses the Pi awake again. That loop is invisible until you watch
the serial console across a halt.

**Pin map is fixed by the course labs.** GPIO25 is the Pi wake line (open-drain,
pulsed low 250 ms) and GPIO16/17 are UART2 for the Pi text link. The buzzer
therefore lives on GPIO27. Do not reuse 16, 17 or 25.

**CSI camera cannot be power-gated easily.** The ribbon carries 3.3 V with no
switch. Closing the camera in `picamera2` drops it to a low-power state but not to
zero. Full gating means cutting the ribbon's 3.3 V line and inserting a MOSFET —
possible, but say so honestly in the report rather than claiming "camera off".

**The soil probe is resistive, not capacitive.** It is a DFRobot SEN0114
(Gravity analog soil moisture), two prongs, 0–4.2 V output. This inverts the
intuition: wet soil conducts better, so the output **rises** with moisture.
Dry soil reads low, water reads high. DFRobot's own 10-bit reference values are
0–300 dry, 300–700 humid, 700–950 in water.

**It will corrode.** DFRobot says so explicitly and recommends their capacitive
SEN0193 instead for anything long-term. A resistive probe left powered in damp
soil erodes within days. Power-gating it through a MOSFET is not an optimisation
here, it is the difference between a probe that lasts the project and one that
does not. Currently wired straight to 3V3, so it is always powered.

**Never power it from 5 V.** The output can reach 4.2 V, which exceeds the
ESP32's ADC limit and will damage the pin. 3.3 V keeps the output inside range,
at the cost of the top of the scale saturating near 3.1 V.

**Soil calibration is a guess right now.** `SOIL_ADC_DRY 0` is the air reading,
not a dry-soil reading, and `SOIL_ADC_WET 2300` is a glass of water. Both need a
real pot measurement: `tools/live.py --csv`, probe in dry soil, then in water.

**Buzzer on the ESP32, not the Pi.** Keeps the alert path alive when the Pi is off.

---

## 6. Repository layout

```
lowerEnergy/
├── install.sh                 # build, flash and deploy one variant
├── requirements.txt
├── README.md  INSTALL.md  MEASUREMENT.md  PLAN.md
├── variants/                  # one folder per rung
│   ├── v0_baseline/           # variant.h, run.py, install.sh, README.md
│   ├── v1_duty/
│   ├── v2_adaptive/
│   └── v3_deepsleep/
├── firmware/                  # ESP-IDF project, shared by all four
│   ├── CMakeLists.txt
│   ├── sdkconfig.defaults
│   └── main/
│       ├── CMakeLists.txt
│       ├── main.c             # the loop, branching on the variant knobs
│       ├── config.h           # pins, calibration, PI_HANDOVER_MS
│       ├── variant.h          # generated by install.sh from variants/<name>/
│       ├── dht11.c/.h         # bit-bang one-wire driver
│       ├── sensors.c/.h       # ADC + DHT, power gating
│       ├── buzzer.c/.h        # LEDC PWM at 2300 Hz
│       ├── pi_link.c/.h       # wake pulse + UART2
│       ├── sample_log.c/.h    # 96-reading ring in RTC memory, V3 only
│       └── rules.c/.h         # ESP32-side rule engine, V2 and V3
├── pi/
│   ├── common/                # config, logger, camera, rules
│   ├── v0_baseline.py
│   ├── v1_duty.py
│   ├── v2_adaptive.py
│   ├── v3_wake.py
│   └── vision/                # U2-Net leaf pipeline + u2netp.onnx
├── config/
│   ├── configuration.txt
│   └── camera.json
├── logs/                      # events_log.txt, last_capture.jpg, ...
└── tools/
    ├── supervisor.py          # asks the ESP32 which mode to run
    ├── dashboard.py           # web UI on 8081
    ├── preview.py             # camera preview on 8080
    ├── live.py                # tail the UART link
    ├── flash.sh  flash_pi.sh  idf_env.sh
    └── nat.sh                 # laptop-side: gives the Pi internet
```

There is no `report/` directory: the report is not part of this repository.

---

## 7. Milestones

| Phase | Work | Done when | Status |
|---|---|---|---|
| 0 | Bring-up: serial, DHT11, soil, buzzer, Pi wake pulse | All of it works from one build | **done** |
| 0b | HVPM bring-up: `hvpm doctor`, `hvpm info`, one real capture | A CSV from real hardware, not `--simulate` | **not started** |
| 1 | V0 end-to-end | Rules fire, log matches the spec format | **done** |
| 2 | V1 | Same behaviour at 60 s / 5 min | **done** |
| 3 | V2 | ESP32 autonomous, adaptive interval demonstrably backs off | built, **never run on hardware** |
| 4 | V3 | Pi halted, ESP32 deep sleeping, full cycle | **done** |
| 5 | Measurement + report | Energy table across all four, test scenario documented | **not started** |

Phase 0b is the one blocking everything else: without a trustworthy CSV there are
no numbers, and without numbers the ladder is four programs rather than an
evaluation.

---

## 8. Energy measurement with the Monsoon HVPM

You already have `~/Desktop/projects/hvpm-linux` — a Linux CLI for the HVPM (AAA10F)
built on PyMonsoon. Use it; do not write measurement code from scratch.

```bash
hvpm doctor                                    # device reachable?
hvpm info                                      # what's attached
hvpm capture -o v0_esp32.csv --duration 60 --voltage 3.3
hvpm capture -o v0_pi.csv    --duration 60 --voltage 5
hvpm plot v0_pi.csv -o v0_pi.png
```

5 kHz sampling. CSV is `timestamp_ms,main_current_ma,main_voltage_v`, and
`capture.py` already does charge/energy integration.

### The single-channel constraint

The HVPM powers **one load at a time**. Per-component energy therefore means
sequential runs, not simultaneous measurement:

| Run | HVPM powers | Gives you |
|---|---|---|
| 1 | ESP32 alone | sensor node, all four variants |
| 2 | Pi alone, camera attached, ESP32 detached | vision node |
| 3 | Pi with ESP32 on its 5 V rail | system total, cross-check on 1 + 2 |

Camera share: measure Pi with camera closed vs camera streaming; the difference is
the camera's contribution. No extra hardware needed.

Check the HVPM's current limit against the Pi 4's ~3 A peak before connecting it —
a brownout mid-capture wastes a run.

### Caveat

That repo's README says the real backend is written against the documented PyMonsoon
API but **has never been exercised against physical hardware**. Run `hvpm doctor`
then `hvpm info` before trusting any capture, and budget an hour for it. If the
backend needs fixing, that is Phase 0b, not a surprise during evaluation week.

### Why this instrument matters for the report

5 kHz resolves the ESP32's sleep current (tens of µA) and the Pi's boot inrush, not
just a 60 s average. That turns "we estimate 18×" into a measured curve, and it
catches things an average hides — whether light sleep actually reaches its datasheet
current, whether the USB-UART bridge is quietly drawing 5 mA the whole time, whether
the Pi's idle floor is really 3 W or 4.5 W with the camera attached.

---

## 9. Test scenario

The spec asks for a practical evaluation scenario. Four tests, run identically against
every variant:

**A. Environmental sweep.** Hairdryer at fixed distance raises air temp ~0.5 °C/min.
Log the moment the threshold is crossed and the moment the buzzer fires. Measure
detection latency and false positives. Repeat cooling with an ice pack.

**B. Soil dry-down.** Let a pot dry naturally over several days, or water it to go the
other way. Weigh the pot alongside the ADC reading to build a real calibration curve
(ADC → volumetric water content). This turns "soil_humidity = 300" into a defensible
threshold instead of a guess.

**C. Visual.** Display a fixed set of plant images on a tablet in front of the camera:
healthy, yellowing, different leaf counts. Measure classification accuracy per class.
This is the spec's "show different plant images to the camera" test, made repeatable.

**D. Energy.** Run each variant through the same 2 h accelerated scenario with
`hvpm capture` running throughout. Report Wh per variant, per component, using the
three-run methodology in §8.

A–C are run by hand and the results written down as they go. There is no
`scenario.py` or `energy_bench.py`: the timeline is short enough to drive
manually, and a script that half-automates it would be more to trust than to
write. D follows the run list in `MEASUREMENT.md`.

---

## 10. Verified infrastructure

Recorded because each of these cost time to discover.

### Laptop

- Hotspot `wlp0s20f3` = 10.42.0.1/24, NetworkManager connection `LRK5`,
  `ipv4.method=shared`
- Uplink is whatever owns the default route. It has been `enxa6c337b9f279`
  (phone USB tethering, 172.20.10.3/28) and `enx6c1ff761ed1b` (wired university
  net, 88.200.102.134/24). Do not hardcode it — `tools/nat.sh` detects it.
- **NetworkManager's shared mode does not apply its NAT rules on this machine.**
  The log shows the hotspot, dnsmasq and DHCP all coming up, but no iptables
  setup at all, so the Pi gets an address and no route out. `tools/nat.sh`
  installs them:

```bash
sudo tools/nat.sh
```

  It is idempotent (`iptables -C` before `-A`) and takes the uplink from the
  default route. `/etc/NetworkManager/dispatcher.d/90-pi-nat` calls it on every
  interface up/down, so it survives reboots and uplink changes. Verified by
  deleting the rules and bouncing the hotspot: they came back on their own.
- `iptables` and `sysctl` live in `/usr/sbin`, which is not on a normal user
  PATH. `iptables: command not found` means PATH, not a missing package.
- **Bouncing the hotspot drops the Pi for three to four minutes.** It
  re-associates on its own — do not conclude it is dead. Avoid bouncing while
  the Pi is the only client.

### Raspberry Pi

- `PEON-Miha-Rene`, Pi 4 Model B Rev 1.5, Debian 13 (trixie), aarch64
- `admin@10.42.0.15`, SSH key auth installed, `admin` has passwordless-to-us sudo
- Python 3.13.5, numpy 2.2.4, picamera2 0.3.38, libcamera 0.7.2
- venv at `~/plant/.venv` created with `--system-site-packages` so picamera2 and
  numpy stay visible
- **Clock is wrong after every reboot unless NAT works.** No RTC, so it boots to
  the time saved at shutdown — it has been 6 days and 8h45m behind. With
  `tools/nat.sh` in place, systemd-timesyncd syncs within a couple of minutes
  and it stays correct. Without it, set the clock by hand or `events_log.txt`
  timestamps lie.
- **Camera: Raspberry Pi Camera Module 3 (Sony IMX708), working.** 4608x2592
  RGGB, module ID `0x0301`. Both `rpicam-still` and `picamera2` capture fine.
  - `camera_auto_detect=0` with an explicit `dtoverlay=imx708` in `config.txt`.
    Auto-detect never found it; forcing the overlay made the driver probe and
    report a real error instead of silence.
  - **The ribbon was in backwards.** Symptom was
    `imx708 10-001a: failed to read chip id 708, with error -5` — `EIO` on the
    I2C probe, meaning the sensor never acknowledged. Reversing the ribbon fixed
    it instantly. Worth remembering: `error -5` on a camera probe is physical,
    not software.
  - Only one process can hold the camera. Running `rpicam-still` and `picamera2`
    at the same time gives `Device or resource busy`.

### Pi link (from the course lab guides)

Wiring, all on the 40-pin header:

| ESP32 | Pi | Purpose |
|---|---|---|
| D25 (GPIO25) | pin 5 (GPIO3) | wake, open-drain, 250 ms low pulse |
| GND | pin 6 | common ground |
| TX2 (GPIO17) | pin 10 (RXD) | ESP32 → Pi |
| RX2 (GPIO16) | pin 8 (TXD) | Pi → ESP32 |

**Never touch Pi pins 2 and 4** — they are 5 V and sit right next to the pins in use.

Pi side, already verified on this machine:

- `WAKE_ON_GPIO=1` — GPIO3 wakes the Pi from halt
- `POWER_OFF_ON_HALT=0` — belt and braces; the PMIC-off state only applies with
  `WAKE_ON_GPIO=0`, and then nothing can wake the Pi
- No `gpio-shutdown` overlay (that would make GPIO3 shut the Pi down instead)
- `enable_uart=1`, `/dev/serial0 -> ttyS0`
- **Serial console removed** from `cmdline.txt` (backup at `cmdline.txt.bak`).
  Without this a login shell fights the ESP32 for the UART.

ESP32 side: UART2 at 115200 8N1, and `main/CMakeLists.txt` must list
`esp_driver_uart` in `PRIV_REQUIRES` or `driver/uart.h` will not be found.

Wake logic: pulse only when `esp_reset_reason() != ESP_RST_DEEPSLEEP`, otherwise
every deep-sleep wake restarts the Pi. An unpowered ESP32 is *not* an open switch —
the Pi's pull-up can leak into it and look like a button press. The lab's optional
NPN transistor (BC547/2N2222/2N3904 + 1 kΩ base) fixes that.

**Verified working on this hardware:** ESP32 → Pi readings arrive on `/dev/serial0`
at 2.05 s intervals, `buzz 2` sent from the Pi is received and executed by the
ESP32, and the **wake pulse works end to end** — Pi powered off, EN pressed, Pi
booted, UART2 link resumed with no intervention. The ESP32 kept running throughout
because 5 V on the header is not a PMIC output and stays live across a halt.

**I2C must stay off.** GPIO3 is I2C1 SCL as well as the wake input. With
`dtparam=i2c_arm=on` the kernel claims the pin and the wake is unreliable. It is
commented out in `config.txt`; `/dev/i2c-1` is gone and GPIO3 is claimed only by
`GLOBAL_RESET`.

`main/CMakeLists.txt` needs `PRIV_REQUIRES` to list every driver the code touches —
adding it drops the implicit defaults, so `esp_driver_gpio`, `esp_driver_uart`,
`esp_driver_ledc`, `esp_adc` and `esp_timer` must all be named explicitly or the
build fails on missing headers.

### ESP32

- ESP32-D0WD-V3 rev 3.1, 4 MB flash, MAC `b4:bf:e9:1a:ae:bc`, dual core + LP core
- Wired to the **Pi**, not the laptop, at `/dev/ttyUSB0` (CP2102)
- **Flash at 115200 baud.** The default 460800 fails with "Failed to start stub
  flasher". `tools/flash_pi.sh` handles this.
- esptool 5.6.0 lives in the Pi venv; invoke as `python -m esptool` because the
  console script was never created (packages were copied in, not pip-installed)

---

## 11. Open questions

- Plant species in the greenhouse kit — needed to set real thresholds in
  `configuration.txt` (optimal temp/humidity, visual distress signals per species).
- Does the HVPM backend actually work against your unit? Phase 0b answers this.
- What does a halted Pi 4 actually draw? P1 in `MEASUREMENT.md` answers it, and
  the V3 headline number depends on it.

---

## 12. What changed during the build

Written after the fact, so the plan above is not mistaken for a description of
the code.

| Planned | Built instead | Why |
|---|---|---|
| ULP coprocessor watches the soil ADC in V3 | Main CPU wakes on a timer | The ULP needs its own toolchain and build step. A timer wake is enough for a plant, where nothing happens on a second timescale. |
| `configuration.txt` on ESP32 LittleFS | Rules pushed over UART2 into RTC memory | LittleFS would need the file on the ESP32's flash plus a way to update it. The UART push reuses the link that was already there and needs no filesystem. |
| V1 light sleeps between reads | `vTaskDelay`, stays awake | The ESP32 cannot wake from light sleep on UART2, only UART0/UART1, and UART1's wake pin is GPIO9, which is the SPI flash. Dead end. |
| V0 photographs every 30 s | V0 never uses the camera | The camera is the most expensive peripheral. Leaving it out makes V0 a clean sensor-only floor, and the camera's share is measured separately (P7 - P2). |
| int8 quantised CV model | Float `u2netp.onnx` | Quantising cost more time than it saved, and in V3 the Pi is halted anyway, so the model's runtime barely moves the total. |
| Pi sleeps between events in V2 | Pi stays awake | V2's job is to isolate adaptive sampling. Sleeping the Pi there would have made V2 and V3 the same experiment. |
| `tools/scenario.py`, `tools/energy_bench.py` | Not written | The scenario is run by hand; the procedure is in `MEASUREMENT.md`. |
| Radio off in V3 | Nothing to turn off | No variant uses the radio, so there was never a radio cost to remove. |
| A halted Pi draws ~0.5-1 W | Measured at 1.34 W | The guess was low. `measurement/RESULTS.md` has the number: 268.8 mA at 5 V, with the ESP32 unplugged and with it sampling. |
