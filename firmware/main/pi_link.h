#pragma once

#include <stddef.h>

// Set up the link to the Raspberry Pi: the wake line on GPIO25 and UART2 on
// GPIO17/16.
//
// The wake line is pulsed unless we just came out of deep sleep, so a deep-sleep
// wake does not restart a Pi that is already running.
void pi_link_init(void);

// Send one line to the Pi. A newline is appended.
void pi_link_send(const char *text);

// Read whatever the Pi has sent, up to len-1 bytes, and NUL-terminate it.
// Returns the byte count, or 0 if nothing arrived. Never blocks.
int pi_link_recv(char *buf, size_t len);
