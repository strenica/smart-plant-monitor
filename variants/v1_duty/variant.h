#pragma once

// V1 fixed duty cycle: the same split as V0, on a slower clock.
//
// The ESP32 samples once a minute instead of every two seconds, and the Pi
// takes a picture every five minutes instead of running the camera flat out.
// Nothing adapts. The intervals are fixed, which is what makes this the first
// honest measurement of how much of V0's energy was pure waste.

#define VARIANT_NAME "V1 fixed duty cycle"

#define SAMPLE_INTERVAL_MS          60000
#define ADAPTIVE_INTERVAL           0
#define RULES_ON_ESP32              0
#define LIGHT_SLEEP_BETWEEN_SAMPLES 0
#define DEEP_SLEEP_BETWEEN_SAMPLES  0
