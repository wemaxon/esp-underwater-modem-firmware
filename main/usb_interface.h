#pragma once

/*
 * Development interface to the host over USB: parses TinyFrame requests,
 * runs the matching command and sends responses and device log events.
 * Everything runs in the task that calls usb_interface_poll().
 */

#include "esp_err.h"

esp_err_t usb_interface_init(void);

/* Waits up to 10 ms for host data, then handles it and any completed capture. */
void usb_interface_poll(void);
