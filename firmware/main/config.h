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

// DHT11 needs about a second between reads and cannot be sampled faster.
#define DHT_MIN_INTERVAL_MS 2000

// How many times to retry a failed DHT11 read before giving up on that sample.
#define DHT_RETRIES 3
