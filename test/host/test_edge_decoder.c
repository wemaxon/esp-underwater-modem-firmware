#include <stdint.h>

#include "check.h"
#include "edge_decoder.h"

/* One RMT symbol: two {duration, level} halves, low half first. */
static uint32_t symbol(uint32_t duration0, uint32_t level0, uint32_t duration1, uint32_t level1)
{
    return duration0 | (level0 << 15) | (duration1 << 16) | (level1 << 31);
}

static void decodes_edges_from_first_edge(void)
{
    const uint32_t words[] = {symbol(100, 1, 100, 0), symbol(100, 1, 50, 0), symbol(0, 0, 0, 0)};
    edge_t edges[6];
    edge_decoder_t decoder;
    edge_decoder_start(&decoder, 100);
    CHECK(edge_decoder_feed(&decoder, words, 3, edges) == 4);
    CHECK(edges[0].time_ns == 0 && edges[0].level);
    CHECK(edges[1].time_ns == 10000 && !edges[1].level);
    CHECK(edges[2].time_ns == 20000 && edges[2].level);
    CHECK(edges[3].time_ns == 30000 && !edges[3].level);
    CHECK(decoder.ended);
}

static void continues_across_chunks(void)
{
    const uint32_t first[] = {symbol(10, 0, 20, 1)};
    const uint32_t second[] = {symbol(30, 0, 0, 1)};
    edge_t edges[2];
    edge_decoder_t decoder;
    edge_decoder_start(&decoder, 1);
    CHECK(edge_decoder_feed(&decoder, first, 1, edges) == 2);
    CHECK(edges[1].time_ns == 10 && edges[1].level);
    CHECK(edge_decoder_feed(&decoder, second, 1, edges) == 1);
    CHECK(edges[0].time_ns == 30 && !edges[0].level);
    CHECK(decoder.ended);
}

static void merges_level_split_across_halves(void)
{
    const uint32_t words[] = {symbol(100, 0, 200, 0), symbol(30, 1, 0, 0)};
    edge_t edges[4];
    edge_decoder_t decoder;
    edge_decoder_start(&decoder, 1);
    CHECK(edge_decoder_feed(&decoder, words, 2, edges) == 2);
    CHECK(edges[1].time_ns == 300 && edges[1].level);
}

static void ignores_symbols_after_the_end(void)
{
    const uint32_t words[] = {symbol(0, 1, 0, 0), symbol(10, 1, 10, 0)};
    edge_t edges[4];
    edge_decoder_t decoder;
    edge_decoder_start(&decoder, 1);
    CHECK(edge_decoder_feed(&decoder, words, 2, edges) == 0);
    CHECK(decoder.ended);
}

int main(void)
{
    decodes_edges_from_first_edge();
    continues_across_chunks();
    merges_level_split_across_halves();
    ignores_symbols_after_the_end();
    return 0;
}
