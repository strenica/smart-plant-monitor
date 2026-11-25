#pragma once

// ---------------------------------------------------------------------------
// Pin map, ESP32 WROOM-32.
// GPIO 34-39 are input-only with no internal pull-ups, which is what you want
// for an ADC input. Do not move the soil probe below GPIO 34.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Pin map, as physically wired on this build.
// GPIO 34-39 are input-only with no internal pull-ups, which is what you want
// for an ADC input.
// ---------------------------------------------------------------------------
#define PIN_DHT_DATA    4     // DHT11 one-wire data
#define PIN_SOIL_ADC    34    // DFRobot SEN0114 analog out (ADC1_CH6)
#define PIN_SOIL_POWER  23    // gate of the MOSFET that powers the probe (unused)
#define PIN_BUZZER      27    // Grove Buzzer, driven by LEDC PWM at 2300 Hz

// ---------------------------------------------------------------------------
// Raspberry Pi link, following the course lab guides.
//
// D25 is the wake line. The Pi 4 wakes when its GPIO3 (physical pin 5) is
// briefly pulled to ground, so the ESP32 drives this pin open-drain and pulses
// it low for 250 ms. GPIO25 is therefore reserved and the buzzer moved to 27.
//
// UART2 carries the text link, keeping UART0 free for the USB monitor:
//   TX2 (GPIO17) -> Pi pin 10 (RXD)
//   RX2 (GPIO16) -> Pi pin 8  (TXD)
//   GND          -> Pi pin 6
// ---------------------------------------------------------------------------
#define PIN_PI_WAKE     25
#define PIN_PI_UART_TX  17
#define PIN_PI_UART_RX  16

// Set to 1 only if the probe's ground really goes through a MOSFET on
// PIN_SOIL_POWER. With 0 the probe is assumed permanently powered and the gate
// pin is left alone, which is the case for a direct-to-GND wiring.
#define SOIL_POWER_GATED 0

// ---------------------------------------------------------------------------
// Soil calibration for the DFRobot SEN0114 (Gravity analog soil moisture).
//
// This is a RESISTIVE probe, not capacitive: two prongs pass a current through
// the soil and the module outputs a voltage proportional to conductivity.
// Wet soil conducts better, so the output RISES with moisture. That is the
// opposite of a capacitive probe, where dry reads high.
//
// DFRobot's own reference values on a 10-bit ADC are 0-300 dry soil, 300-700
// humid, 700-950 in water. Those assume a 5 V supply. Measured on this probe at
// 3.3 V: air reads 0, a glass of water reads a very stable 2297 (+-4). So the
// usable range here is 0..2300, not the full 0..4095.
//
// DRY is set to the air reading rather than a dry-soil reading because we have
// not measured dry soil yet. Refine both once the probe is in a real pot:
// run tools/live.py --csv, note the raw adc in dry soil and again in water.
// ---------------------------------------------------------------------------
#define SOIL_ADC_DRY    0     // raw ADC in air -> maps to 0
#define SOIL_ADC_WET    2300  // raw ADC in water -> maps to 1000

// Buzzer loudness, as a percentage of full duty.
//
// A piezo is loudest at 50% duty, which is far too loud for a desk. The
// fundamental of the square wave scales with sin(pi * duty), so 10% is about
// 10 dB quieter than 50% and still clearly audible at arm's length. Raise it
// for a demo in a big room, lower it for a shared one.
#define BUZZER_DUTY_PCT 10

// DHT11 needs about a second between reads and cannot be sampled faster.
#define DHT_MIN_INTERVAL_MS 2000

// How many times to retry a failed DHT11 read before giving up on that sample.
#define DHT_RETRIES 3

// How long the ESP32 stays awake after waking the Pi, waiting for it to boot
// and collect the readings buffered while it was off. The Pi says "bye" as soon
// as it has them, so this is a ceiling rather than a typical wait. Only V3 uses
// it; the other variants never power the Pi down.
#ifndef PI_HANDOVER_MS
#define PI_HANDOVER_MS 120000
#endif

// Setup mode is entered on every cold boot, because pressing EN is a cold boot
// and that is how you ask to reframe the camera. The catch is that a board
// powered up with no Pi attached would then stay awake forever, which silently
// ruins any deep-sleep measurement: the run measures an awake ESP32.
//
// So setup mode expires. If the Pi has not said anything at all, it is not
// coming and the node goes back to monitoring quickly. Once the Pi has spoken,
// the node stays awake long enough for the camera preview to run to its own
// five-minute timeout and send "mode run".
#ifndef SETUP_WAIT_MS
#define SETUP_WAIT_MS 120000
#endif

#ifndef SETUP_HOLD_MS
#define SETUP_HOLD_MS 600000
#endif

// ---------------------------------------------------------------------------
// Everything that differs between the four variants lives in variant.h, which
// install.sh copies in from variants/<name>/ before building. Keeping it out of
// this file means one firmware source serves the whole ladder, and the diff
// between two variants is a single small header.
// ---------------------------------------------------------------------------
#include "variant.h"

// Wake the Pi at least this often even when no rule fires, so a quiet plant
// still produces a photograph and a node that has died is distinguishable from
// one that has nothing to say. 0 disables it, which is what every variant but
// V3 wants. The Pi can override it at runtime with "set heartbeat <ms>".
#ifndef HEARTBEAT_MS
#define HEARTBEAT_MS 0
#endif
