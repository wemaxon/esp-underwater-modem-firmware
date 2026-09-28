#pragma once

/*
 * Records the edges of one digital input with an RMT receive channel.
 *
 * A capture is armed with edge_capture_start(), begins at the first edge and
 * ends after idle_timeout_ns without an edge or when the buffer is full.
 * Poll edge_capture_take() for the result.
 */

#include <stddef.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "edge_trace.h"
#include "esp_err.h"

typedef struct {
    gpio_num_t gpio;
    uint32_t resolution_hz;         /* tick rate of recorded durations */
    size_t symbol_capacity;         /* receive buffer; each symbol holds two levels */
    uint32_t min_pulse_ns;          /* shorter pulses are filtered out as glitches */
    uint32_t idle_timeout_ns;       /* capture ends after this long without an edge */
} edge_capture_config_t;

typedef enum {
    EDGE_CAPTURE_PENDING,           /* armed, not finished */
    EDGE_CAPTURE_COMPLETE,
    EDGE_CAPTURE_TRUNCATED,         /* buffer filled up; the trace holds what fit */
    EDGE_CAPTURE_EMPTY,             /* finished without a usable signal */
} edge_capture_result_t;

typedef struct edge_capture *edge_capture_handle_t;

esp_err_t edge_capture_new(const edge_capture_config_t *config, edge_capture_handle_t *handle);
esp_err_t edge_capture_start(edge_capture_handle_t handle);
/* Cancels an armed capture and discards an untaken result. */
esp_err_t edge_capture_stop(edge_capture_handle_t handle);

/*
 * Non-blocking. Once the capture has finished, decodes it into trace, whose
 * edge storage should hold EDGE_TRACE_CAPACITY_FOR_SYMBOLS(symbol_capacity) entries.
 */
edge_capture_result_t edge_capture_take(edge_capture_handle_t handle, edge_trace_t *trace);
