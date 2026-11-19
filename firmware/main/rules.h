#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "sensors.h"

// The ESP32-side rule engine, used by V2 and V3 where the Pi is not in the
// decision loop.
//
// Same semantics as pi/common/rules.py: a rule buzzes when it enters violation,
// then re-alerts once per cooldown while it stays violated. Clearing a
// condition is silent, and a rule whose field has no measurement never fires.
//
// The rule set lives in RTC memory, so the Pi can replace it over UART without
// a reflash and the replacement survives deep sleep. A power cycle clears it
// and the firmware falls back to the text baked in at install time.

#define RULES_MAX 8

// Parse configuration.txt-style text. Replaces the current set and marks it as
// coming from the firmware rather than the Pi. Returns the number of rules.
int rules_load(const char *text);

// Empty the staging area. The live set is untouched until rules_commit(), so a
// push that dies halfway leaves the old rules working rather than an empty set
// that silently never buzzes.
void rules_clear(void);

// Append one rule to the staging area. Returns false if the field or operator
// is unknown.
bool rules_add(int number, const char *field, const char *op, float threshold);

// Swap the staged set in for the live one and mark it as Pi-supplied, so a boot
// does not overwrite it with the firmware text. Also forgets which rules were
// violated, because the new set has nothing to do with the old one.
void rules_commit(void);

// True once the Pi has pushed a set, even an empty one.
bool rules_pushed(void);

// How many rules are loaded.
int rules_count(void);

// Evaluate one reading. Writes the rule numbers that should buzz now into
// `fired` and returns how many.
//
// `now_ms` is a monotonic clock the caller keeps across deep sleep, because the
// CPU's own uptime restarts on every wake.
int rules_evaluate(const struct reading *r, uint32_t now_ms,
                   int *fired, int max_fired);

// How many rules are currently in violation.
int rules_active(void);
