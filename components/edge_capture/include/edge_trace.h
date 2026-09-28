#pragma once

/*
 * A recorded digital signal. Pure data and decoding without ESP-IDF
 * dependencies, so it can be tested on the host.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Time starts at the first edge. initial_level is the level after that edge;
 * every entry in edges is a later level change, in ticks from the first edge,
 * strictly increasing and below duration_ticks.
 */
typedef struct {
    bool initial_level;
    uint32_t duration_ticks;
    size_t edge_count;
    size_t edge_capacity;
    uint32_t *edges;            /* caller-owned storage of edge_capacity entries */
} edge_trace_t;

typedef enum {
    EDGE_TRACE_OK,
    EDGE_TRACE_EMPTY,           /* no signal recorded */
    EDGE_TRACE_FULL,            /* edge storage ran out; trace is truncated */
} edge_trace_status_t;

/* Edge storage needed to decode every symbol of an RMT buffer. */
#define EDGE_TRACE_CAPACITY_FOR_SYMBOLS(symbols) (2U * (symbols) - 1U)

/*
 * Decodes RMT receive symbols given as raw 32-bit words. Each word holds two
 * {15-bit duration, 1-bit level} halves, low half first. A zero duration marks
 * the end of the recording.
 */
edge_trace_status_t edge_trace_decode_rmt(const uint32_t *words, size_t word_count, edge_trace_t *trace);
