#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#define DEVICE_LOG_TEXT_CAPACITY 256U

typedef struct {
    uint16_t length;
    char text[DEVICE_LOG_TEXT_CAPACITY];
} device_log_entry_t;

esp_err_t device_log_init(void);
bool device_log_read(device_log_entry_t *entry);
