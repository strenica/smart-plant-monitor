#pragma once

#include <stdbool.h>
#include <stddef.h>

#include "sensors.h"

// A ring buffer of recent readings, kept in RTC memory.
//
// V3 sleeps between samples and the Pi is powered off, so nothing is listening
// when a reading is taken. Rather than throw the reading away, the ESP32 keeps
// the last SAMPLE_LOG_CAP of them here and hands them over when the Pi next
// wakes and asks. RTC memory survives deep sleep, so the buffer outlives the
// CPU being switched off; a power cycle clears it.
//
// V0/V1/V2 stream every reading to the Pi as it is taken and never use this.

void sample_log_add(const struct reading *r);

// How many readings are buffered, oldest first.
int sample_log_count(void);

// Format buffered reading `index` (0 = oldest) as a normal reading line, the
// same one the live variants send. Returns false if the index is out of range.
bool sample_log_line(int index, char *buf, size_t len);

// Drop everything. Called once the Pi has the readings, so the next wake does
// not log them a second time.
void sample_log_clear(void);
