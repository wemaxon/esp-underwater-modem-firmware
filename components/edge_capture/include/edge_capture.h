#pragma once

/*
 * Continuously records the edges of one digital input with an RMT receive
 * channel, without gaps.
 *
 * The signal is received in segments that end after idle_timeout_ns without an
 * edge. A GPIO interrupt timestamps the first edge of each segment; later edges
 * are timed by the RMT from there. Edges are buffered between the interrupt
 * and edge_capture_read().
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "edge_decoder.h"
#include "esp_err.h"

/* Room edge_capture_read() needs to decode one buffered chunk. */
#define EDGE_CAPTURE_READ_MIN_EDGES 128U

typedef struct {
    gpio_num_t gpio;
    uint32_t resolution_hz;     /* edge timing resolution; must divide 1 GHz */
    uint32_t min_pulse_ns;      /* shorter pulses are filtered out as glitches */
    uint32_t idle_timeout_ns;   /* a segment ends after this long without an edge */
    size_t buffer_bytes;        /* buffered edge data between interrupt and reader */
} edge_capture_config_t;

typedef struct edge_capture *edge_capture_handle_t;

esp_err_t edge_capture_new(const edge_capture_config_t *config, edge_capture_handle_t *handle);
esp_err_t edge_capture_start(edge_capture_handle_t handle);
esp_err_t edge_capture_stop(edge_capture_handle_t handle);

/*
 * Non-blocking. Writes buffered edges, timed in ns of esp_timer device time,
 * and returns their number. capacity must be at least EDGE_CAPTURE_READ_MIN_EDGES.
 */
size_t edge_capture_read(edge_capture_handle_t handle, edge_t *edges, size_t capacity);

/* True once edges were lost because the buffer was full; cleared by edge_capture_start(). */
bool edge_capture_overflowed(edge_capture_handle_t handle);
