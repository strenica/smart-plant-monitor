#pragma once

#include "esp_err.h"

// Configure the data pin. Call once before dht11_read().
void dht11_init(void);

// Read the DHT11 on PIN_DHT_DATA.
//
// Returns ESP_OK and fills both outputs on success. Returns ESP_ERR_TIMEOUT if
// the sensor never answers, or ESP_ERR_INVALID_CRC if the checksum does not
// match. Both are normal on a long or noisy cable; the caller should retry.
esp_err_t dht11_read(float *temp_c, float *humidity_pct);
