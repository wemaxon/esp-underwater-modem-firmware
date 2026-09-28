#include "edge_trace.h"

#define HALF_BITS      16U
#define DURATION_MASK  0x7FFFU
#define LEVEL_SHIFT    15U

typedef struct {
    uint32_t duration;
    bool level;
} segment_t;

static segment_t segment_at(const uint32_t *words, size_t index)
{
    uint32_t half = words[index / 2] >> ((index % 2) * HALF_BITS);
    return (segment_t){.duration = half & DURATION_MASK, .level = (half >> LEVEL_SHIFT) & 1U};
}

edge_trace_status_t edge_trace_decode_rmt(const uint32_t *words, size_t word_count, edge_trace_t *trace)
{
    trace->duration_ticks = 0;
    trace->edge_count = 0;
    trace->initial_level = false;

    for (size_t index = 0; index < 2 * word_count; ++index) {
        segment_t segment = segment_at(words, index);
        if (!segment.duration) {
            break;
        }
        if (index == 0) {
            trace->initial_level = segment.level;
        } else if (segment.level != segment_at(words, index - 1).level) {
            if (trace->edge_count == trace->edge_capacity) {
                return EDGE_TRACE_FULL;
            }
            trace->edges[trace->edge_count++] = trace->duration_ticks;
        }
        trace->duration_ticks += segment.duration;
    }
    return trace->duration_ticks ? EDGE_TRACE_OK : EDGE_TRACE_EMPTY;
}
