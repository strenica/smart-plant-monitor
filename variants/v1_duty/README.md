# V1 — fixed duty cycle

The same split as V0, on a slower clock. This is the first rung that should
show a real energy drop.

## What it changes

| | V0 | V1 |
|---|---|---|
| ESP32 sample interval | 2 s | 60 s |
| Pi camera | never | every 5 min |
| Rules evaluated on | Pi | Pi |
| ESP32 sleeps | no | no |

Nothing adapts. The intervals are fixed, which is what isolates the cost of
V0's sampling rate from everything else.

## Install

```bash
./install.sh v1_duty
```

## Run

```bash
ssh admin@10.42.0.15
cd ~/plant && .venv/bin/python variants/v1_duty/run.py
```

Options:

```bash
--image-interval 60    # picture every minute instead of every five
--no-vision            # sensors and rules only, never touch the camera
--dry-run              # evaluate and log, never buzz
```

## Why the ESP32 does not light sleep

It cannot. The ESP32 only wakes from light sleep on UART0 and UART1, and
UART1's wake pin is GPIO9, which is wired to the SPI flash on this module. The
Pi link is on UART2, so sleeping would silently drop the Pi's `buzz N`
commands. The ESP32 draws about 0.1 W against the Pi's 3 W, so the saving is
not worth losing the link. V3 deep sleeps instead, when the Pi is off and there
is nothing to receive.

## Timing

Set the intervals in `config/configuration.txt`; no reflash needed.

```
sample_interval = 60     # ESP32, pushed over UART2 at startup
image_interval = 300     # Pi camera
```

`--image-interval` overrides `image_interval` for a single run, which is handy
while testing. Leave a key out and the compiled default applies.

## Setup mode

Pressing EN on the ESP32 cold-boots it and puts it in setup mode. The camera
preview then runs instead of this variant's loop, so you can reframe. It works
whether the Pi is booting or already running: the ESP32 either answers `mode?`
or sends `setup` over UART2, and this loop exits with code 42 so the supervisor
can take over.

It ends on **save and apply**, or after five minutes with no browser, and the
loop starts afterwards either way.

```bash
.venv/bin/python tools/supervisor.py --variant v1_duty
```

is what the systemd unit runs; it asks the ESP32 which mode to use.
