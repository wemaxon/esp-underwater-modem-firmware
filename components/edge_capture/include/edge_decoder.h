#pragma once

/*
 * Decodes RMT receive symbols into edges. Pure code without ESP-IDF
 * dependencies, so it can be tested on the host.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    int64_t time_ns;
    bool level;                 /* level after the edge */
} edge_t;

/* State of one recording, which starts at its first edge. */
typedef struct {
    uint32_t ns_per_tick;
    int64_t edge_ns;            /* time of the most recent edge, from the first edge */
    uint32_t level_ticks;       /* time spent at the current level so far */
    bool level;
    bool started;
    bool ended;
} edge_decoder_t;

void edge_decoder_start(edge_decoder_t *decoder, uint32_t ns_per_tick);

/*
 * Decodes the next raw 32-bit RMT symbols of the recording; each holds two
 * {15-bit duration, 1-bit level} halves, low half first. Writes the edges they
 * contain, timed from the first edge, to edges (room for 2 * word_count) and
 * returns their number. A zero duration ends the recording.
 */
size_t edge_decoder_feed(edge_decoder_t *decoder, const uint32_t *words, size_t word_count, edge_t *edges);
