#include "rules.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "esp_attr.h"
#include "esp_log.h"

static const char *TAG = "rules";

#define RULES_COOLDOWN_MS (30u * 60u * 1000u)

enum field {
    FIELD_AIR_HUMIDITY,
    FIELD_AIR_TEMPERATURE,
    FIELD_SOIL_HUMIDITY,
    FIELD_UNKNOWN,
};

enum op {
    OP_LT,
    OP_GT,
    OP_LE,
    OP_GE,
    OP_UNKNOWN,
};

struct rule {
    int   number;      // also the buzz count
    int   field;
    int   op;
    float threshold;
};

static struct rule s_rules[RULES_MAX];
static int s_count;

// These survive deep sleep, so a rule that is already violated does not
// re-alert on every wake.
static RTC_DATA_ATTR bool     s_violated[RULES_MAX];
static RTC_DATA_ATTR uint32_t s_last_alert_ms[RULES_MAX];

static int field_from_name(const char *name)
{
    if (strcmp(name, "air_humidity") == 0)    return FIELD_AIR_HUMIDITY;
    if (strcmp(name, "air_temperature") == 0) return FIELD_AIR_TEMPERATURE;
    if (strcmp(name, "soil_humidity") == 0)   return FIELD_SOIL_HUMIDITY;
    return FIELD_UNKNOWN;
}

static int op_from_name(const char *name)
{
    if (strcmp(name, "<") == 0)  return OP_LT;
    if (strcmp(name, ">") == 0)  return OP_GT;
    if (strcmp(name, "<=") == 0) return OP_LE;
    if (strcmp(name, ">=") == 0) return OP_GE;
    return OP_UNKNOWN;
}

int rules_load(const char *text)
{
    s_count = 0;
    const char *p = text;

    while (*p && s_count < RULES_MAX) {
        const char *eol = strchr(p, '\n');
        size_t len = eol ? (size_t)(eol - p) : strlen(p);

        char line[96];
        if (len >= sizeof(line)) {
            len = sizeof(line) - 1;
        }
        memcpy(line, p, len);
        line[len] = '\0';

        char *s = line;
        while (*s == ' ' || *s == '\t') {
            s++;
        }

        if (*s && *s != '#') {
            int   number = 0;
            char  field[32] = {0};
            char  op[3] = {0};
            float threshold = 0.0f;

            if (sscanf(s, "%d : %31[a-z_] %2s %f",
                       &number, field, op, &threshold) == 4) {
                int f = field_from_name(field);
                int o = op_from_name(op);
                if (f == FIELD_UNKNOWN || o == FIELD_UNKNOWN) {
                    ESP_LOGW(TAG, "unknown field or operator: %s", s);
                } else {
                    s_rules[s_count].number    = number;
                    s_rules[s_count].field     = f;
                    s_rules[s_count].op        = o;
                    s_rules[s_count].threshold = threshold;
                    s_count++;
                }
            } else {
                ESP_LOGW(TAG, "cannot parse rule: %s", s);
            }
        }

        if (!eol) {
            break;
        }
        p = eol + 1;
    }

    return s_count;
}

static bool value_of(const struct reading *r, int field, float *out)
{
    switch (field) {
    case FIELD_AIR_HUMIDITY:
        if (!r->dht_ok) return false;
        *out = r->air_humidity_pct;
        return true;
    case FIELD_AIR_TEMPERATURE:
        if (!r->dht_ok) return false;
        *out = r->air_temp_c;
        return true;
    case FIELD_SOIL_HUMIDITY:
        *out = (float)r->soil_raw;
        return true;
    default:
        return false;
    }
}

static bool violated(const struct rule *rule, const struct reading *r)
{
    float v;
    if (!value_of(r, rule->field, &v)) {
        // No measurement for this field yet. A missing value is not a
        // violation; buzzing because the DHT11 has not warmed up would be a
        // false alarm.
        return false;
    }

    switch (rule->op) {
    case OP_LT: return v <  rule->threshold;
    case OP_GT: return v >  rule->threshold;
    case OP_LE: return v <= rule->threshold;
    case OP_GE: return v >= rule->threshold;
    default:    return false;
    }
}

int rules_evaluate(const struct reading *r, uint32_t now_ms,
                   int *fired, int max_fired)
{
    int n = 0;

    for (int i = 0; i < s_count; i++) {
        bool v = violated(&s_rules[i], r);
        bool alert = false;

        if (v && !s_violated[i]) {
            // Entering violation: always alert.
            alert = true;
            s_last_alert_ms[i] = now_ms;
        } else if (v && s_violated[i]) {
            // Still violated: re-alert only after the cooldown.
            if (now_ms - s_last_alert_ms[i] >= RULES_COOLDOWN_MS) {
                alert = true;
                s_last_alert_ms[i] = now_ms;
            }
        }
        // Leaving violation is silent. Clearing a condition should not buzz.

        s_violated[i] = v;

        if (alert && n < max_fired) {
            fired[n++] = s_rules[i].number;
        }
    }

    return n;
}

int rules_active(void)
{
    int n = 0;
    for (int i = 0; i < s_count; i++) {
        if (s_violated[i]) {
            n++;
        }
    }
    return n;
}
