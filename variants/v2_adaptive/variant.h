#pragma once

// V2 adaptive sampling: the rules move onto the ESP32.
//
// The Pi is no longer in the decision loop, so it can stop polling. The
// sampling interval follows the observed variance: a stable pot backs off to
// ten minutes, a changing one comes back to ten seconds.

#define VARIANT_NAME "V2 adaptive sampling"

#define SAMPLE_INTERVAL_MS          10000   // starting point, then adaptive
#define ADAPTIVE_INTERVAL           1
#define RULES_ON_ESP32              1
#define LIGHT_SLEEP_BETWEEN_SAMPLES 0
#define DEEP_SLEEP_BETWEEN_SAMPLES  0

// Adaptive interval bounds. A reading that moves by more than these deltas is
// "changing" and pulls the interval back to the fast end.
#define ADAPTIVE_FAST_MS            10000
#define ADAPTIVE_SLOW_MS            600000
#define ADAPTIVE_SOIL_DELTA         20
#define ADAPTIVE_TEMP_DELTA         1.0f
#define ADAPTIVE_STABLE_SAMPLES     3

// The rules have to live on the ESP32 to be evaluated without the Pi. Same
// format as config/configuration.txt.
#define RULES_TEXT \
    "1: air_humidity > 50\n" \
    "2: air_temperature < 15\n" \
    "3: soil_humidity < 300\n"
