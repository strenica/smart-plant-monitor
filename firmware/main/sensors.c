#include "sensors.h"
#include "config.h"
#include "dht11.h"

#include "driver/gpio.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "sensors";

static adc_oneshot_unit_handle_t s_adc;
static int64_t s_last_dht_us = 0;
static float   s_last_temp   = 0.0f;
static float   s_last_hum    = 0.0f;
static bool    s_have_dht    = false;

void soil_power(bool on)
{
#if SOIL_POWER_GATED
    gpio_set_level(PIN_SOIL_POWER, on ? 1 : 0);
#else
    (void)on;   // probe is wired straight to 3V3 and GND, nothing to switch
#endif
}

void sensors_begin(void)
{
#if SOIL_POWER_GATED
    gpio_config_t pwr = {
        .pin_bit_mask = 1ULL << PIN_SOIL_POWER,
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    gpio_config(&pwr);
    soil_power(false);   // probe off by default
#endif

    adc_oneshot_unit_init_cfg_t unit_cfg = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&unit_cfg, &s_adc));

    // GPIO34 is ADC1 channel 6. 12 dB attenuation gives the widest usable
    // range, roughly 0-3.1 V, which covers a capacitive probe on 3.3 V.
    adc_oneshot_chan_cfg_t chan_cfg = {
        .atten    = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc, ADC_CHANNEL_6, &chan_cfg));

    dht11_init();
    ESP_LOGI(TAG, "sensors ready");
}

// Average the ADC over a short burst. Used by both the normal read and the
// bring-up diagnostic.
static int adc_average(void)
{
    int sum = 0;
    for (int i = 0; i < 8; i++) {
        int raw = 0;
        if (adc_oneshot_read(s_adc, ADC_CHANNEL_6, &raw) == ESP_OK) {
            sum += raw;
        }
        vTaskDelay(pdMS_TO_TICKS(2));
    }
    return sum / 8;
}

void soil_diagnose(int *raw_on, int *raw_off)
{
    soil_power(true);
    vTaskDelay(pdMS_TO_TICKS(50));   // let the probe's regulator come up
    *raw_on = adc_average();

    soil_power(false);
    vTaskDelay(pdMS_TO_TICKS(50));
    *raw_off = adc_average();
}

// ADC1 channel to GPIO mapping on the ESP32. Channels 0-3 are input-only pins
// that are not broken out on every board, so failures here are expected.
static const int adc1_gpio[8] = { 36, 37, 38, 39, 32, 33, 34, 35 };

void adc_scan(void)
{
    for (int ch = 0; ch < 8; ch++) {
        adc_oneshot_chan_cfg_t cfg = {
            .atten    = ADC_ATTEN_DB_12,
            .bitwidth = ADC_BITWIDTH_DEFAULT,
        };
        if (adc_oneshot_config_channel(s_adc, (adc_channel_t)ch, &cfg) != ESP_OK) {
            continue;
        }
        int raw = 0;
        if (adc_oneshot_read(s_adc, (adc_channel_t)ch, &raw) == ESP_OK) {
            ESP_LOGI(TAG, "scan ADC1_CH%d (GPIO%d) = %d", ch, adc1_gpio[ch], raw);
        }
    }
}

// Read the probe and map it onto the 0..1000 scale the spec asks for.
// The ESP32 ADC is noisy, so average a handful of samples.
static int read_soil(int *raw_out)
{
    soil_power(true);
    vTaskDelay(pdMS_TO_TICKS(10));   // let the probe's output settle

    int raw = adc_average();
    soil_power(false);

    *raw_out = raw;
    // Resistive probe: wet soil conducts better, so the raw value rises with
    // moisture. DRY < WET, giving a positive slope onto the 0..1000 scale.
    int scaled = (raw - SOIL_ADC_DRY) * 1000 / (SOIL_ADC_WET - SOIL_ADC_DRY);
    if (scaled < 0)   scaled = 0;
    if (scaled > 1000) scaled = 1000;
    return scaled;
}

struct reading sensors_read(void)
{
    struct reading r = {0};
    r.ms = (uint32_t)(esp_timer_get_time() / 1000);
    r.soil_raw = read_soil(&r.soil_adc);

    // Respect the DHT11's minimum interval. Between reads we hand back the last
    // good values rather than blocking or returning garbage.
    int64_t now = esp_timer_get_time();
    if (now - s_last_dht_us >= (int64_t)DHT_MIN_INTERVAL_MS * 1000) {
        s_last_dht_us = now;
        for (int attempt = 0; attempt < DHT_RETRIES; attempt++) {
            float t, h;
            if (dht11_read(&t, &h) == ESP_OK) {
                s_last_temp = t;
                s_last_hum  = h;
                s_have_dht  = true;
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }

    r.air_temp_c       = s_last_temp;
    r.air_humidity_pct = s_last_hum;
    r.dht_ok           = s_have_dht;
    return r;
}
