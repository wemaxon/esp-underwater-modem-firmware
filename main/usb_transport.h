#pragma once

/* Byte transport over the ESP32-C3 USB Serial/JTAG CDC port. */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"
#include "freertos/FreeRTOS.h"

esp_err_t usb_transport_init(void);
bool usb_transport_connected(void);
int usb_transport_read(uint8_t *data, size_t capacity, TickType_t timeout);
/* Writes everything, waiting for buffer space; fails if the host stops reading. */
esp_err_t usb_transport_write(const uint8_t *data, size_t length);
/* Writes everything or nothing, without waiting. */
bool usb_transport_try_write(const uint8_t *data, size_t length);
