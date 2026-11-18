#include "dht11.h"
#include "config.h"

#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// The DHT11 speaks a one-wire protocol with no clock line, so every bit is
// timed by how long the line stays high:
//
//   host pulls low >= 18 ms, releases
//   sensor answers 80 us low, 80 us high
//   40 bits follow, each: 50 us low, then high for ~28 us (0) or ~70 us (1)
//   the 40 bits are humidity int, humidity dec, temp int, temp dec, checksum
//
// Timing is done with esp_timer_get_time() rather than a busy-wait counter so
// the numbers stay meaningful if the CPU frequency changes later.

// Wait until the line reaches `level`, giving up after `timeout_us`.
// Returns the microseconds spent waiting, or -1 on timeout.
static int wait_level(int level, int timeout_us)
{
    int64_t start = esp_timer_get_time();
    while (gpio_get_level(PIN_DHT_DATA) != level) {
        if (esp_timer_get_time() - start > timeout_us) {
            return -1;
        }
    }
    return (int)(esp_timer_get_time() - start);
}

void dht11_init(void)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << PIN_DHT_DATA,
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,   // harmless if the module has one
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&cfg);
}

esp_err_t dht11_read(float *temp_c, float *humidity_pct)
{
    uint8_t data[5] = {0};

    // Start signal: hold the line low long enough for the sensor to notice.
    gpio_set_direction(PIN_DHT_DATA, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_DHT_DATA, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(PIN_DHT_DATA, 1);
    esp_rom_delay_us(30);
    gpio_set_direction(PIN_DHT_DATA, GPIO_MODE_INPUT);

    // Response: 80 us low, then 80 us high, then the first bit's 50 us low.
    if (wait_level(0, 200) < 0) return ESP_ERR_TIMEOUT;
    if (wait_level(1, 200) < 0) return ESP_ERR_TIMEOUT;
    if (wait_level(0, 200) < 0) return ESP_ERR_TIMEOUT;

    // 40 bits, most significant bit first.
    for (int i = 0; i < 40; i++) {
        if (wait_level(1, 200) < 0) return ESP_ERR_TIMEOUT;  // 50 us low ends
        int high_us = wait_level(0, 200);                    // measure the high
        if (high_us < 0) return ESP_ERR_TIMEOUT;

        data[i / 8] <<= 1;
        if (high_us > 45) {          // ~28 us is a 0, ~70 us is a 1
            data[i / 8] |= 1;
        }
    }

    uint8_t sum = (uint8_t)(data[0] + data[1] + data[2] + data[3]);
    if (sum != data[4]) {
        return ESP_ERR_INVALID_CRC;
    }

    *humidity_pct = data[0] + data[1] * 0.1f;
    *temp_c       = data[2] + data[3] * 0.1f;
    return ESP_OK;
}
