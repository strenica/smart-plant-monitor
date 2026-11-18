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
#include <string.h>

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

// Intervals retuned by the Pi from configuration.txt. Zero means "use the
// compiled default". RTC memory keeps them across deep sleep, so a V3 node
// keeps the interval the Pi last sent it; a power cycle resets them.
static RTC_DATA_ATTR uint32_t s_interval_ms = 0;

// Set when the board cold-boots, which is what pressing EN does. The Pi asks
// about it at startup and, if set, boots into the camera preview instead of the
// monitoring loop. Cleared when the Pi says it is done framing.
static RTC_DATA_ATTR bool s_setup_mode = false;
static RTC_DATA_ATTR uint32_t s_fast_ms = 0;
static RTC_DATA_ATTR uint32_t s_slow_ms = 0;

static uint32_t base_interval(void)
{
    return s_interval_ms ? s_interval_ms : SAMPLE_INTERVAL_MS;
}

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
        return base_interval();
    }

    int   soil_delta = abs(r->soil_raw - prev_soil);
    float temp_delta = fabsf(r->air_temp_c - prev_temp);
    prev_soil = r->soil_raw;
    prev_temp = r->air_temp_c;

    if (soil_delta >= ADAPTIVE_SOIL_DELTA || temp_delta >= ADAPTIVE_TEMP_DELTA) {
        stable = 0;
        return s_fast_ms ? s_fast_ms : ADAPTIVE_FAST_MS;
    }

    if (++stable >= ADAPTIVE_STABLE_SAMPLES) {
        return s_slow_ms ? s_slow_ms : ADAPTIVE_SLOW_MS;
    }
    return base_interval();
}
#endif

static void handle_command(const char *cmd)
{
    int n = 0;
    unsigned long ms = 0, fast = 0, slow = 0;

    if (sscanf(cmd, "buzz %d", &n) == 1 && n > 0 && n <= 5) {
        buzzer_beep(n);
    } else if (strncmp(cmd, "mode?", 5) == 0) {
        pi_link_send(s_setup_mode ? "mode setup" : "mode run");
    } else if (strncmp(cmd, "mode run", 8) == 0) {
        s_setup_mode = false;
        ESP_LOGI(TAG, "setup mode cleared");
    } else if (sscanf(cmd, "set interval %lu", &ms) == 1 && ms >= 1000) {
        s_interval_ms = (uint32_t)ms;
        ESP_LOGI(TAG, "sample interval now %lu ms", ms);
    } else if (sscanf(cmd, "set adaptive %lu %lu", &fast, &slow) == 2 &&
               fast >= 1000 && slow >= fast) {
        s_fast_ms = (uint32_t)fast;
        s_slow_ms = (uint32_t)slow;
        ESP_LOGI(TAG, "adaptive bounds now %lu..%lu ms", fast, slow);
    }
}

// Commands are polled from their own task rather than the sampling loop. With a
// 60 s interval the loop would otherwise take a minute to answer "mode?", and
// the Pi would sit waiting at boot.
static void command_task(void *arg)
{
    char cmd[64];
    while (1) {
        if (pi_link_recv(cmd, sizeof(cmd)) > 0) {
            ESP_LOGI(TAG, "pi says: %s", cmd);
            handle_command(cmd);
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

void app_main(void)
{
    // Deep sleep restarts the CPU, so app_main runs again on every wake. The
    // bring-up diagnostics must not repeat: three beeps a minute would be
    // absurd and would wreck the energy measurement.
    bool cold_boot = esp_reset_reason() != ESP_RST_DEEPSLEEP;

    if (cold_boot) {
        // Pressing EN is how you ask for setup mode: the Pi comes up in the
        // camera preview so you can reframe, then returns to monitoring.
        s_setup_mode = true;
    }

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

    xTaskCreate(command_task, "commands", 3072, NULL, 5, NULL);

    if (cold_boot) {
        // Tell a Pi that is already running. A Pi that is still booting misses
        // this and asks "mode?" instead, which is why both paths exist.
        pi_link_send("setup");
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

        uint32_t interval_ms = base_interval();

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
#endif

        s_clock_ms += interval_ms;

#if DEEP_SLEEP_BETWEEN_SAMPLES
        if (s_setup_mode) {
            // The Pi is framing the camera and has to be able to reach us: it
            // asks "mode?" at boot and sends "mode run" when it is done.
            // Sleeping here would leave the flag set, and every later boot
            // would land in the preview again.
            ESP_LOGI(TAG, "setup mode: staying awake");
            vTaskDelay(pdMS_TO_TICKS(interval_ms));
            continue;
        }
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
