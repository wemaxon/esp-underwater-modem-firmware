#pragma once

/*
 * Continuous acquisition of VOUT samples and OUT3 edges on one time base:
 * nanoseconds since acquisition_start(), derived from the device clock.
 */

#include <stddef.h>
#include <stdint.h>

#include "edge_decoder.h"
#include "esp_err.h"

#define ACQUISITION_VOUT_RATE_HZ    20000U
#define ACQUISITION_VOUT_BLOCK      256U        /* samples returned per read */
#define ACQUISITION_EDGE_CLOCK_HZ   10000000U   /* OUT3 timing resolution */

typedef enum {
    ACQUISITION_OK,
    ACQUISITION_OVERFLOW,   /* data was lost because the reader fell behind */
    ACQUISITION_ERROR,
} acquisition_status_t;

esp_err_t acquisition_init(void);
esp_err_t acquisition_start(void);
esp_err_t acquisition_stop(void);

/*
 * Non-blocking. Each returns the number of items written: up to
 * ACQUISITION_VOUT_BLOCK consecutive VOUT samples in millivolts, starting at
 * *first_sample_ns, or OUT3 edges (capacity at least EDGE_CAPTURE_READ_MIN_EDGES).
 */
size_t acquisition_read_vout(int64_t *first_sample_ns, uint16_t *millivolts);
size_t acquisition_read_out3(edge_t *edges, size_t capacity);

acquisition_status_t acquisition_status(void);
