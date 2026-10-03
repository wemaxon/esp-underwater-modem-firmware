#include <stdint.h>

#include "check.h"
#include "tuss4470_waveform.h"

#define CLOCK_HZ 20000000U

/* One cycle: low for half ticks, then high for half ticks. */
static uint32_t cycle(uint32_t half)
{
    return half | ((half | (1U << 15)) << 16);
}

static void plays_tones_cycle_by_cycle_across_chunks(void)
{
    const tuss4470_tone_t tones[] = {{40000, 2}, {39000, 1}};
    tuss4470_waveform_t waveform;
    uint32_t symbols[4] = {0};
    tuss4470_waveform_start(&waveform, tones, 2, CLOCK_HZ);
    CHECK(tuss4470_waveform_fill(&waveform, symbols, 2) == 2);
    CHECK(symbols[0] == cycle(250) && symbols[1] == cycle(250));      /* 20 MHz / 40 kHz / 2 */
    CHECK(!tuss4470_waveform_done(&waveform));
    CHECK(tuss4470_waveform_fill(&waveform, symbols, 4) == 1);
    CHECK(symbols[0] == cycle(256));                                   /* 256.4 rounded */
    CHECK(tuss4470_waveform_done(&waveform));
    CHECK(tuss4470_waveform_fill(&waveform, symbols, 4) == 0);
}

static void reports_the_played_duration(void)
{
    const tuss4470_tone_t tones[] = {{40000, 2}, {39000, 1}};
    CHECK(tuss4470_waveform_duration_us(tones, 2, CLOCK_HZ) == 75);   /* (2 * 500 + 512) ticks of 50 ns */
    const tuss4470_tone_t symbol[] = {{40000, 400}};
    CHECK(tuss4470_waveform_duration_us(symbol, 1, CLOCK_HZ) == 10000);
}

int main(void)
{
    plays_tones_cycle_by_cycle_across_chunks();
    reports_the_played_duration();
    return 0;
}
