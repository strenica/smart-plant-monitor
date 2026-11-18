# Install

From bare boards to a running monitor. If you only want to switch variants on a
machine that is already set up, skip to [Install a variant](#install-a-variant).

## What you need

| Part | Notes |
|---|---|
| ESP32-D0WD-V3 | 4 MB flash. Any ESP32-WROOM-32 board should work |
| Raspberry Pi 4 Model B | 4 GB is plenty. Pi 5 untested |
| DHT11 | temperature and humidity |
| DFRobot SEN0114 | **resistive** soil moisture, two prongs |
| Grove Buzzer | passive piezo, driven at its 2300 Hz resonance |
| Raspberry Pi Camera Module 3 | Sony IMX708 |
| microSD card | 16 GB or more |
| 5 V supply for the Pi | the ESP32 is powered from the Pi's USB |

## Wiring

| ESP32 | Pi | Purpose |
|---|---|---|
| D25 (GPIO25) | pin 5 (GPIO3) | wake, open-drain, 250 ms low pulse |
| GND | pin 6 | common ground |
| TX2 (GPIO17) | pin 10 (RXD) | ESP32 → Pi |
| RX2 (GPIO16) | pin 8 (TXD) | Pi → ESP32 |
| USB | USB | power, and the UART0 console |

Sensors:

| Sensor | ESP32 pin |
|---|---|
| DHT11 data | GPIO 4 |
| SEN0114 analog out | GPIO 34 (ADC1_CH6) |
| Grove buzzer | GPIO 27 |

Never touch Pi pins 2 and 4 — they are 5 V. The SEN0114 must be powered from
3.3 V, not 5 V: its output can reach 4.2 V and damage the ADC.

## Raspberry Pi setup

Debian 13 (trixie) is what this was built and tested on.

### Camera

The Camera Module 3 needs to be named explicitly, because auto-detect picks the
wrong sensor mode and the preview looks zoomed in for no obvious reason. In
`/boot/firmware/config.txt`:

```
camera_auto_detect=0
dtoverlay=imx708
```

### I2C must stay off

GPIO3 is both I2C1 SCL and the wake input. With I2C enabled the kernel claims
the pin and the wake becomes unreliable. Leave it commented out:

```
#dtparam=i2c_arm=on
```

### Keep the 5 V rail up while halted

This is an EEPROM setting, not a config.txt one. Without it the Pi cuts power to
its own USB ports when it halts, which kills the ESP32 that is supposed to wake
it again.

```bash
sudo rpi-eeprom-config --edit
```

```
WAKE_ON_GPIO=1
POWER_OFF_ON_HALT=0
```

Reboot after changing either file.

### Packages

```bash
sudo apt install python3-picamera2 python3-numpy python3-serial
```

`picamera2` and `numpy` come from apt because they are tied to the system
Python. The venv is created with `--system-site-packages` so it can see them.

### SSH

The installer assumes `admin@10.42.0.15`. Override with `PI=user@host`. Key
auth is worth setting up, since the installer runs several commands over SSH.

## ESP-IDF setup

ESP-IDF 5.5.6 is what this was built against.

```bash
git clone -b v5.5.6 --recursive https://github.com/espressif/esp-idf.git ~/esp/esp-idf
~/esp/esp-idf/install.sh esp32
```

Then, before any build:

```bash
. tools/idf_env.sh
```

That wrapper exists because `export.sh` looks for a Python venv matching the
system `python3`. Upgrade the system Python and `export.sh` fails with
"virtual environment not found" even though the venv is fine. `idf_env.sh` points
`IDF_PYTHON_ENV_PATH` at whatever venv is actually installed.

## Install a variant

```bash
./install.sh v1_duty
```

That builds the firmware with `variants/v1_duty/variant.h`, flashes it on the Pi
at 115200 baud, and syncs the Pi code.

```bash
./install.sh --list               # show the four variants
./install.sh v1_duty --fw-only    # firmware only
./install.sh v1_duty --pi-only    # Pi code only
./install.sh v1_duty --no-flash   # build, do not flash
./install.sh v1_duty --service    # also install a systemd unit
./install.sh v1_duty --dashboard  # also install the web dashboard
```

Each `variants/<name>/` folder also works on its own:
`./variants/v1_duty/install.sh`.

### Flashing needs `--no-stub`

The stub flasher fails on this board with "Failed to start stub flasher" at
460800 *and* at 115200. The ROM loader is slower — about 26 s for the app — but
works every time. `install.sh` already does this.

## Running

```bash
ssh admin@10.42.0.15
cd ~/plant
.venv/bin/python tools/supervisor.py --variant v1_duty
```

The supervisor is what the systemd unit runs. It asks the ESP32 which mode to
use and then starts either the camera preview or the variant's loop.

To run a variant directly, without the supervisor:

```bash
.venv/bin/python variants/v1_duty/run.py
```

## Setup mode: press EN to reframe

Pressing EN on the ESP32 cold-boots it, and it remembers that. Two paths lead
into setup mode:

- **Pi booting** — the supervisor asks `mode?` and gets `mode setup`.
- **Pi already running** — the ESP32 sends `setup` over UART2, the variant exits
  with code 42, and the supervisor switches to the preview.

The preview ends when you press **save and apply**, or after five minutes with
no browser connected. Either way the monitoring loop starts afterwards, so a
forgotten preview cannot leave the plant unwatched.

## Dashboard

```bash
./install.sh v1_duty --dashboard
```

Serves on port 8081: latest sensor values, the event log, and an editor for
`configuration.txt` that validates before writing. It shows the last frame the
scanner analysed rather than a live stream, because only one process can hold
the camera and the monitoring loop needs it.

## Why systemd

Nothing starts the supervisor on its own otherwise. The whole point of pressing
EN is that the Pi comes up and the preview is just there — that needs something
to run at boot, and systemd is the standard way on Debian.

The units are optional. Without them you start the supervisor by hand after
every boot. With them, `plant-monitor.service` runs the supervisor and
`plant-dashboard.service` runs the web UI. The monitor unit keeps a fixed name
whatever variant is installed, so switching variants replaces it rather than
leaving the old one enabled and fighting for the camera.

```bash
sudo systemctl status plant-monitor
sudo systemctl status plant-dashboard
journalctl -u plant-monitor -f
```

`install.sh` only installs a unit when you pass `--service` or `--dashboard`.
It needs sudo, which over SSH has no terminal, so it works unattended only if
the Pi has passwordless sudo. Otherwise it prints the two commands for you to
run.

## Troubleshooting

**`Failed to start stub flasher`** — use `--no-stub`. `install.sh` does.

**`Device or resource busy` on the camera** — only one process can hold it. The
usual culprit is a preview left running:

```bash
fuser -k 8080/tcp
```

**`pkill -f preview.py` kills your SSH session** — the pattern matches the SSH
command line itself. Use `fuser -k 8080/tcp` or `ss -ltnp | grep 8080`.

**The preview looks zoomed in** — picamera2's default sensor mode is a centre
crop. `open_camera` forces `(2304, 1296)`; check that `camera_auto_detect=0` and
`dtoverlay=imx708` are set.

**The image is blurry** — the lens starts at infinity. `autofocus` in
`config/camera.json` should be `true`.

**The Pi's clock is wrong** — it drifts badly with no internet, and
`events_log.txt` timestamps will lie. Set it before a logging run.

**The ESP32 prints a burst then goes quiet** — that is a boot burst, not a
crash. Wait a full sample interval before concluding anything.

**`export.sh` says the virtual environment is not found** — source
`tools/idf_env.sh` instead.
