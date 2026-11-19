#include "sample_log.h"

#include <math.h>
#include <stdio.h>

#include "esp_attr.h"

// 96 readings is 1.6 h at the 60 s fast interval and 16 h at the 600 s slow
// one, which covers any realistic gap between Pi wakes. At 12 bytes each the
// buffer costs 1.2 KB of the 8 KB of RTC memory.
#define SAMPLE_LOG_CAP 96

typedef struct {
    uint32_t ms;
    int16_t  soil;
    int16_t  adc;
    int16_t  temp_x10;   // tenths of a degree, so 19.8 C is 198
    uint8_t  humidity;
    uint8_t  flags;      // bit 0: the DHT11 answered
} sample_entry_t;

static RTC_DATA_ATTR sample_entry_t s_entries[SAMPLE_LOG_CAP];
static RTC_DATA_ATTR uint16_t s_head;    // where the next reading goes
static RTC_DATA_ATTR uint16_t s_count;   // how many are valid

void sample_log_add(const struct reading *r)
{
    sample_entry_t *e = &s_entries[s_head];

    e->ms       = r->ms;
    e->soil     = (int16_t)r->soil_raw;
    e->adc      = (int16_t)r->soil_adc;
    e->temp_x10 = r->dht_ok ? (int16_t)lroundf(r->air_temp_c * 10.0f) : 0;
    e->humidity = r->dht_ok ? (uint8_t)lroundf(r->air_humidity_pct) : 0;
    e->flags    = r->dht_ok ? 1 : 0;

    s_head = (uint16_t)((s_head + 1) % SAMPLE_LOG_CAP);
    if (s_count < SAMPLE_LOG_CAP) {
        s_count++;
    }
}

int sample_log_count(void)
{
    return s_count;
}

bool sample_log_line(int index, char *buf, size_t len)
{
    if (index < 0 || index >= s_count) {
        return false;
    }

    // The buffer is a ring, so the oldest entry is not at index 0 once it has
    // wrapped. Walk forward from wherever the oldest one landed.
    int oldest = (s_head + SAMPLE_LOG_CAP - s_count) % SAMPLE_LOG_CAP;
    const sample_entry_t *e = &s_entries[(oldest + index) % SAMPLE_LOG_CAP];

    if (e->flags & 1) {
        snprintf(buf, len, "t=%lu soil=%d adc=%d air_t=%.1f air_h=%u",
                 (unsigned long)e->ms, e->soil, e->adc,
                 e->temp_x10 / 10.0f, (unsigned)e->humidity);
    } else {
        snprintf(buf, len, "t=%lu soil=%d adc=%d air=ERR",
                 (unsigned long)e->ms, e->soil, e->adc);
    }
    return true;
}

void sample_log_clear(void)
{
    s_head  = 0;
    s_count = 0;
}
