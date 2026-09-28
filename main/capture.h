#pragma once

/*
 * Single OUT3 capture: armed on request, starts at the first zero crossing,
 * ends 20 ms after the last one and times out 2 s after arming.
 */

#include "driver/gpio.h"
#include "edge_capture.h"

#define CAPTURE_CLOCK_HZ        1000000U
#define CAPTURE_SYMBOL_CAPACITY 512U
#define CAPTURE_EDGE_CAPACITY   EDGE_TRACE_CAPACITY_FOR_SYMBOLS(CAPTURE_SYMBOL_CAPACITY)

typedef enum {
    CAPTURE_OK,
    CAPTURE_PENDING,
    CAPTURE_BUSY,
    CAPTURE_TIMEOUT,
    CAPTURE_OVERFLOW,
    CAPTURE_ERROR,
} capture_status_t;

esp_err_t capture_init(gpio_num_t out3_gpio);

capture_status_t capture_start(void);
capture_status_t capture_stop(void);
/* Completes the armed capture once it has finished or timed out; otherwise returns CAPTURE_PENDING. */
capture_status_t capture_poll(const edge_trace_t **trace);
