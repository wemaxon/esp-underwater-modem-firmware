#pragma once

/*
 * Captures ESP log output into a bounded queue so it can be forwarded to the
 * host. Writing never blocks: long entries are truncated and new entries are
 * dropped while the queue is full.
 */

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

#define DEVICE_LOG_TEXT_CAPACITY 256U

typedef struct {
    uint16_t length;
    char text[DEVICE_LOG_TEXT_CAPACITY];
} device_log_entry_t;

esp_err_t device_log_init(void);
/* Non-blocking; returns false when no entry is queued. */
bool device_log_read(device_log_entry_t *entry);
