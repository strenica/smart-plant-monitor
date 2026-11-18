#pragma once

// V0 baseline: the naive version.
//
// Sample as fast as the DHT11 allows, send every reading to the Pi, and let the
// Pi evaluate the rules. No energy management of any kind, which is the point:
// this is the reference every other variant is measured against.

#define VARIANT_NAME "V0 baseline"

#define SAMPLE_INTERVAL_MS          2000
#define ADAPTIVE_INTERVAL           0
#define RULES_ON_ESP32              0
#define LIGHT_SLEEP_BETWEEN_SAMPLES 0
#define DEEP_SLEEP_BETWEEN_SAMPLES  0
