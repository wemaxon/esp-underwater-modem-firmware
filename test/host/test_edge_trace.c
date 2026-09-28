#include <stdint.h>

#include "check.h"
#include "edge_trace.h"

_Static_assert(EDGE_TRACE_CAPACITY_FOR_SYMBOLS(512) == 1023, "One edge between every two recorded levels");

/* One RMT symbol: two {duration, level} halves, low half first. */
static uint32_t symbol(uint32_t duration0, uint32_t level0, uint32_t duration1, uint32_t level1)
{
    return duration0 | (level0 << 15) | (duration1 << 16) | (level1 << 31);
}

static void decodes_edges_and_duration(void)
{
    const uint32_t words[] = {symbol(100, 1, 100, 0), symbol(100, 1, 50, 0), symbol(0, 0, 0, 0)};
    uint32_t edges[5];
    edge_trace_t trace = {.edges = edges, .edge_capacity = 5};
    CHECK(edge_trace_decode_rmt(words, 3, &trace) == EDGE_TRACE_OK);
    CHECK(trace.initial_level);
    CHECK(trace.duration_ticks == 350);
    CHECK(trace.edge_count == 3);
    CHECK(edges[0] == 100 && edges[1] == 200 && edges[2] == 300);
}

static void merges_level_split_across_segments(void)
{
    const uint32_t words[] = {symbol(100, 0, 200, 0), symbol(30, 1, 0, 0)};
    uint32_t edges[3];
    edge_trace_t trace = {.edges = edges, .edge_capacity = 3};
    CHECK(edge_trace_decode_rmt(words, 2, &trace) == EDGE_TRACE_OK);
    CHECK(!trace.initial_level);
    CHECK(trace.duration_ticks == 330);
    CHECK(trace.edge_count == 1 && edges[0] == 300);
}

static void reports_empty_recording(void)
{
    const uint32_t words[] = {symbol(0, 1, 0, 0)};
    uint32_t edges[1];
    edge_trace_t trace = {.edges = edges, .edge_capacity = 1};
    CHECK(edge_trace_decode_rmt(words, 1, &trace) == EDGE_TRACE_EMPTY);
    CHECK(edge_trace_decode_rmt(words, 0, &trace) == EDGE_TRACE_EMPTY);
}

static void stops_when_edge_storage_is_full(void)
{
    const uint32_t words[] = {symbol(10, 1, 10, 0), symbol(10, 1, 10, 0)};
    uint32_t edges[2];
    edge_trace_t trace = {.edges = edges, .edge_capacity = 2};
    CHECK(edge_trace_decode_rmt(words, 2, &trace) == EDGE_TRACE_FULL);
    CHECK(trace.edge_count == 2 && edges[0] == 10 && edges[1] == 20);
}

int main(void)
{
    decodes_edges_and_duration();
    merges_level_split_across_segments();
    reports_empty_recording();
    stops_when_edge_storage_is_full();
    return 0;
}
