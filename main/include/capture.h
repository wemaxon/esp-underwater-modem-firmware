#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "tuss4470.h"

#define CAPTURE_OUT3_EDGE_CAPACITY (2U * TUSS4470_RX_SYMBOL_CAPACITY - 1U)

typedef enum {
    CAPTURE_OK,
    CAPTURE_PENDING,
    CAPTURE_BUSY,
    CAPTURE_TIMEOUT,
    CAPTURE_OVERFLOW,
    CAPTURE_ERROR,
} capture_status_t;

typedef struct {
    uint32_t duration_ticks;
    bool initial_high;
    size_t edge_count;
    uint32_t edges[CAPTURE_OUT3_EDGE_CAPACITY];
} capture_result_t;

uint32_t capture_clock_hz(void);
capture_status_t capture_start(void);
capture_status_t capture_stop(void);
capture_status_t capture_poll(const capture_result_t **result);
