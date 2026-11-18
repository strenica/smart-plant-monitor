#pragma once

#include <stdbool.h>
#include <stdint.h>

// One sample of everything the sensor node knows.
struct reading {
    uint32_t ms;                // milliseconds since boot
    float    air_temp_c;        // last good DHT11 value
    float    air_humidity_pct;  // last good DHT11 value
    int      soil_raw;          // 0..1000, 0 = dry air, 1000 = water
    int      soil_adc;          // raw ADC counts, for calibration and debugging
    bool     dht_ok;            // false until the first successful DHT read
};

void           sensors_begin(void);
struct reading sensors_read(void);

// The soil probe is powered through a MOSFET because a capacitive probe left
// powered corrodes within weeks. Call with false when you are not sampling.
void soil_power(bool on);

// Bring-up helper: average the ADC with the probe powered and unpowered.
// If raw_on is well above raw_off the MOSFET is switching. If both are near
// zero the probe is not getting power at all.
void soil_diagnose(int *raw_on, int *raw_off);

// Bring-up helper: read every ADC1 channel once and log it. Use this when the
// probe reads zero on the expected pin, to find out whether its output is
// landing somewhere else.
void adc_scan(void);
