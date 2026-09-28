#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

esp_err_t usb_transport_init(void);
int usb_transport_read(uint8_t *data, size_t capacity);
esp_err_t usb_transport_write(const uint8_t *data, size_t length);
bool usb_transport_try_write(const uint8_t *data, size_t length);
bool usb_transport_connected(void);
