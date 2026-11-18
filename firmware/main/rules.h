#pragma once

#include <stdint.h>

#include "sensors.h"

// The ESP32-side rule engine, used by V2 and V3 where the Pi is not in the
// decision loop.
//
// Same semantics as pi/common/rules.py: a rule buzzes when it enters violation,
// then re-alerts once per cooldown while it stays violated. Clearing a
// condition is silent, and a rule whose field has no measurement never fires.

#define RULES_MAX 8

// Parse configuration.txt-style text. Returns the number of rules loaded.
int rules_load(const char *text);

// Evaluate one reading. Writes the rule numbers that should buzz now into
// `fired` and returns how many.
//
// `now_ms` is a monotonic clock the caller keeps across deep sleep, because the
// CPU's own uptime restarts on every wake.
int rules_evaluate(const struct reading *r, uint32_t now_ms,
                   int *fired, int max_fired);

// How many rules are currently in violation.
int rules_active(void);
