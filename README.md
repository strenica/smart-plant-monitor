# Smart Plant Monitor

An ESP32 sensor node and a Raspberry Pi 4 vision node monitoring a plant's
health, built as a ladder of four energy-management variants so the energy cost
of each technique can be measured rather than guessed.

Course project for FRI, 2026.

## Hardware

| Part | Notes |
|---|---|
| ESP32-D0WD-V3 | 4 MB flash, dual core + LP core |
| Raspberry Pi 4 Model B | 4 GB, Debian 13 (trixie) |
| DHT11 | temperature and humidity |
| DFRobot SEN0114 | **resistive** soil moisture, two prongs |
| Grove Buzzer | passive piezo, driven at its 2300 Hz resonance |
| Raspberry Pi Camera Module 3 | Sony IMX708, 12 MP |
| Monsoon HVPM | power measurement, 5 kHz |

## How the two boards are connected

| ESP32 | Pi | Purpose |
|---|---|---|
| D25 (GPIO25) | pin 5 (GPIO3) | wake, open-drain, 250 ms low pulse |
| GND | pin 6 | common ground |
| TX2 (GPIO17) | pin 10 (RXD) | ESP32 → Pi |
| RX2 (GPIO16) | pin 8 (TXD) | Pi → ESP32 |
| USB | USB | power, and the UART0 console |

Never touch Pi pins 2 and 4 — they are 5 V.

## Layout

```
firmware/          ESP-IDF project for the ESP32
  main/
    config.h       pin map and soil calibration
    sensors.c      DHT11 + ADC, with the soil probe's power gate
    dht11.c        bit-bang one-wire driver (ESP-IDF has no official one)
    buzzer.c       LEDC PWM at 2300 Hz
    pi_link.c      wake pulse + UART2
pi/                Raspberry Pi side
  common/config.py configuration.txt and reading parsers
  common/rules.py  rule evaluation, edge triggering, cooldown
  common/logger.py events_log.txt writer
  v0_baseline.py   the naive variant
config/            configuration.txt
tools/             flash and live-view helpers
```

## Build and flash

The ESP32 is wired to the Pi, so the build happens on a workstation and only
the binaries travel:

```bash
export IDF_PYTHON_ENV_PATH="$HOME/.espressif/python_env/idf5.5_py3.12_env"
./tools/flash_pi.sh
```

This board will not flash above 115200 baud — the stub flasher fails to start.

## Run

On the Pi:

```bash
cd ~/plant/pi
.venv/bin/python v0_baseline.py --dry-run
```

`--dry-run` evaluates and logs without buzzing. Drop it to drive the buzzer.

## configuration.txt

```
1: air_humidity > 50
2: air_temperature < 15
3: soil_humidity < 300
```

The rule number is the buzz count: rule 2 buzzes twice. A rule buzzes when it
*enters* violation, then re-alerts once per cooldown (30 min by default) while
it stays violated. Clearing a condition is silent.

## Vision

`pi/vision/leafs.py` runs the U2-Net saliency model to isolate leaf-like
foreground, then applies hand-written colour rules.

```bash
cd ~/plant/pi/vision
~/plant/.venv/bin/python leafs.py
~/plant/.venv/bin/python leafs.py --image images/pepper_bacterial_spot.jpg
```

The split between learned and hand-written stages is the point:

| Stage | Kind |
|---|---|
| Saliency map | learned (U2-Net, 7 outputs, first one used) |
| Otsu threshold, morphology, component filtering | hand-written |
| HSV colour fractions, health label | hand-written |

So `healthy-ish` is a colour heuristic, not a diagnosis. On the bundled
samples it reports `healthy-ish` for both the healthy pepper and the bacterial
spot one, because the spots are a small fraction of leaf area. That is a
limitation of the rule, not a bug in the model.

**`u2netp.onnx` is not in this repo** — its provenance and licence are not
recorded in the source project, so it is not redistributed. Unzip
`leafs-starter.zip` and copy it into `pi/vision/`.

Sample photographs: Mohanty, Hughes and Salathe / PlantVillage, CC BY-SA 3.0.

## Camera preview

The Pi is headless, so the preview is served over HTTP and viewed in a browser:

```bash
cd ~/plant
.venv/bin/python tools/preview.py
# open http://10.42.0.15:8080/
```

Settings live in `config/camera.json` and are shared with the leaf scanner, so
what you frame in the browser is what gets analysed.

| Key | Meaning |
|---|---|
| `size` | output resolution |
| `sensor_mode` | `[2304, 1296]` uses the whole sensor |
| `rotation` | 0, 90, 180 or 270 |
| `zoom` | 1.0 is the full frame, 2.0 crops to the middle half |
| `preview` | set `false` to disable the server |
| `preview_port`, `preview_fps` | server settings |

**`sensor_mode` matters.** The Camera Module 3 offers three modes and picamera2
picks the fastest by default, which is a centre crop of the sensor — the preview
looks zoomed in. `[2304, 1296]` uses the whole sensor.

**Only one process can hold the camera.** Stop the preview before running
`leafs.py --camera`:

```bash
fuser -k 8080/tcp
```

## Status

Working and verified on hardware: both sensors, the buzzer, the Pi wake pulse,
the UART2 link in both directions, the camera, and the V0 baseline with its
rule engine and event log.

Not started: the vision pipeline, and variants V1–V3.

See `PLAN.md` for the variant ladder, the measurement methodology, and the
hardware gotchas that cost time to find.
