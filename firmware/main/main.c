// Smart Plant Monitoring System - sensor node
//
// Phase 0 bring-up plus the Pi link. Reads the DHT11 and the soil probe, prints
// them on the USB console, and sends the same line to the Pi over UART2.
// The Pi can answer with "buzz N" to prove the link works both ways.
//
// Build and flash with tools/flash_pi.sh.

#include <stdio.h>

#include "config.h"
#include "sensors.h"
#include "buzzer.h"
#include "pi_link.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "plant";

void app_main(void)
{
    ESP_LOGI(TAG, "=== plant monitor: phase 0 bring-up ===");
    ESP_LOGI(TAG, "soil calibration: dry=%d wet=%d", SOIL_ADC_DRY, SOIL_ADC_WET);

    sensors_begin();
    buzzer_init();
    pi_link_init();

    // Bring-up diagnostic: if the probe is wired through the MOSFET, the
    // powered reading should be well above the unpowered one.
    int raw_on = 0, raw_off = 0;
    soil_diagnose(&raw_on, &raw_off);
    ESP_LOGI(TAG, "soil diagnostic: powered=%d unpowered=%d", raw_on, raw_off);

    // Which pin is the probe actually on?
    adc_scan();

    ESP_LOGI(TAG, "buzzer: 3 beeps");
    buzzer_beep(3);

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

        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}
