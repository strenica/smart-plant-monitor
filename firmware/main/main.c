// Smart Plant Monitoring System - sensor node
//
// One firmware source serves the whole variant ladder. Everything that differs
// between V0 and V3 lives in variant.h, which install.sh copies in before
// building. See variants/ for the four headers and what each one changes.
//
// Build and flash with ./install.sh <variant>.

#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>

#include "config.h"
#include "sensors.h"
#include "buzzer.h"
#include "pi_link.h"

#if RULES_ON_ESP32
#include "rules.h"
#endif

#include "esp_attr.h"
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#if DEEP_SLEEP_BETWEEN_SAMPLES && !RULES_ON_ESP32
#error "deep sleep without rules on the ESP32 would wake the Pi on every sample"
#endif

static const char *TAG = "plant";

// A clock that survives deep sleep. The CPU's own uptime restarts on every
// wake, so the rule cooldown needs a counter of its own.
static RTC_DATA_ATTR uint32_t s_clock_ms = 0;

#if ADAPTIVE_INTERVAL
// Back off when the readings are boring, come back fast when they move.
//
// A single quiet sample is not enough to justify a ten-minute gap, so the
// interval only reaches the slow end after ADAPTIVE_STABLE_SAMPLES consecutive
// readings that barely moved.
static uint32_t adaptive_interval(const struct reading *r)
{
    static int   prev_soil = 0;
    static float prev_temp = 0.0f;
    static bool  have_prev = false;
    static int   stable = 0;

    if (!have_prev) {
        prev_soil = r->soil_raw;
        prev_temp = r->air_temp_c;
        have_prev = true;
        return SAMPLE_INTERVAL_MS;
    }

    int   soil_delta = abs(r->soil_raw - prev_soil);
    float temp_delta = fabsf(r->air_temp_c - prev_temp);
    prev_soil = r->soil_raw;
    prev_temp = r->air_temp_c;

    if (soil_delta >= ADAPTIVE_SOIL_DELTA || temp_delta >= ADAPTIVE_TEMP_DELTA) {
        stable = 0;
        return ADAPTIVE_FAST_MS;
    }

    if (++stable >= ADAPTIVE_STABLE_SAMPLES) {
        return ADAPTIVE_SLOW_MS;
    }
    return SAMPLE_INTERVAL_MS;
}
#endif

void app_main(void)
{
    // Deep sleep restarts the CPU, so app_main runs again on every wake. The
    // bring-up diagnostics must not repeat: three beeps a minute would be
    // absurd and would wreck the energy measurement.
    bool cold_boot = esp_reset_reason() != ESP_RST_DEEPSLEEP;

    ESP_LOGI(TAG, "=== plant monitor: %s ===", VARIANT_NAME);
    ESP_LOGI(TAG, "sample interval: %d ms", SAMPLE_INTERVAL_MS);

    sensors_begin();
    buzzer_init();
    pi_link_init();

#if RULES_ON_ESP32
    ESP_LOGI(TAG, "rules on the ESP32: %d", rules_load(RULES_TEXT));
#endif

    if (cold_boot) {
        ESP_LOGI(TAG, "soil calibration: dry=%d wet=%d", SOIL_ADC_DRY, SOIL_ADC_WET);

        // Bring-up diagnostic: if the probe is wired through the MOSFET, the
        // powered reading should be well above the unpowered one.
        int raw_on = 0, raw_off = 0;
        soil_diagnose(&raw_on, &raw_off);
        ESP_LOGI(TAG, "soil diagnostic: powered=%d unpowered=%d", raw_on, raw_off);

        // Which pin is the probe actually on?
        adc_scan();

        ESP_LOGI(TAG, "buzzer: 3 beeps");
        buzzer_beep(3);
    }

    ESP_LOGI(TAG, "--- readings ---");

    while (1) {
        struct reading r = sensors_read();

        char line[128];
        if (r.dht_ok) {
            snprintf(line, sizeof(line),
                     "t=%lu soil=%d adc=%d air_t=%.1f air_h=%.0f",
                     (unsigned long)r.ms, r.soil_raw, r.soil_adc,
                     r.air_temp_c, r.air_humidity_pct);
        } else {
            snprintf(line, sizeof(line),
                     "t=%lu soil=%d adc=%d air=ERR",
                     (unsigned long)r.ms, r.soil_raw, r.soil_adc);
        }

        ESP_LOGI(TAG, "%s", line);

        uint32_t interval_ms = SAMPLE_INTERVAL_MS;

#if ADAPTIVE_INTERVAL
        interval_ms = adaptive_interval(&r);
#endif

#if RULES_ON_ESP32
        int fired[RULES_MAX];
        int nf = rules_evaluate(&r, s_clock_ms, fired, RULES_MAX);
        for (int i = 0; i < nf; i++) {
            ESP_LOGI(TAG, "rule %d fired", fired[i]);
            buzzer_beep(fired[i]);
#if !DEEP_SLEEP_BETWEEN_SAMPLES
            // Tell the Pi, so it can photograph whatever just changed. In V3
            // the Pi is off and the wake pulse is the notification instead.
            char event[32];
            snprintf(event, sizeof(event), "event rule=%d", fired[i]);
            pi_link_send(event);
#endif
        }
#endif

#if DEEP_SLEEP_BETWEEN_SAMPLES
        // The Pi is off. Only wake it when something is worth reporting.
        if (nf > 0) {
            pi_link_wake();
        }
#else
        pi_link_send(line);

        // Anything the Pi sent since the last pass. "buzz N" proves the link
        // works in both directions.
        char cmd[64];
        if (pi_link_recv(cmd, sizeof(cmd)) > 0) {
            ESP_LOGI(TAG, "pi says: %s", cmd);
            int n = 0;
            if (sscanf(cmd, "buzz %d", &n) == 1 && n > 0 && n <= 5) {
                buzzer_beep(n);
            }
        }
#endif

        s_clock_ms += interval_ms;

#if DEEP_SLEEP_BETWEEN_SAMPLES
        ESP_LOGI(TAG, "deep sleep for %lu ms", (unsigned long)interval_ms);
        esp_sleep_enable_timer_wakeup((uint64_t)interval_ms * 1000);
        esp_deep_sleep_start();
#elif LIGHT_SLEEP_BETWEEN_SAMPLES
        esp_sleep_enable_timer_wakeup((uint64_t)interval_ms * 1000);
        esp_light_sleep_start();
#else
        vTaskDelay(pdMS_TO_TICKS(interval_ms));
#endif
    }
}
