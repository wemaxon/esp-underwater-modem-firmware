#include "edge_decoder.h"

#define HALF_BITS      16U
#define DURATION_MASK  0x7FFFU
#define LEVEL_SHIFT    15U

void edge_decoder_start(edge_decoder_t *decoder, uint32_t ns_per_tick)
{
    *decoder = (edge_decoder_t){.ns_per_tick = ns_per_tick};
}

size_t edge_decoder_feed(edge_decoder_t *decoder, const uint32_t *words, size_t word_count, edge_t *edges)
{
    size_t count = 0;
    for (size_t index = 0; index < 2 * word_count && !decoder->ended; ++index) {
        uint32_t half = words[index / 2] >> ((index % 2) * HALF_BITS);
        uint32_t duration = half & DURATION_MASK;
        bool level = (half >> LEVEL_SHIFT) & 1U;
        if (!duration) {
            decoder->ended = true;
        } else if (!decoder->started) {
            decoder->started = true;
            decoder->level = level;
            decoder->level_ticks = duration;
            edges[count++] = (edge_t){.time_ns = 0, .level = level};
        } else if (level == decoder->level) {
            decoder->level_ticks += duration;     /* a long level split across halves */
        } else {
            decoder->edge_ns += (int64_t)decoder->level_ticks * decoder->ns_per_tick;
            decoder->level = level;
            decoder->level_ticks = duration;
            edges[count++] = (edge_t){.time_ns = decoder->edge_ns, .level = level};
        }
    }
    return count;
}
