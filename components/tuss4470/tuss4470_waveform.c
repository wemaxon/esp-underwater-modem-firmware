#include "tuss4470_waveform.h"

#define LEVEL_HIGH (1U << 15)

static uint32_t half_period_ticks(uint32_t frequency_hz, uint32_t clock_hz)
{
    return (clock_hz + frequency_hz) / (2U * frequency_hz);
}

void tuss4470_waveform_start(tuss4470_waveform_t *waveform, const tuss4470_tone_t *tones, size_t count, uint32_t clock_hz)
{
    *waveform = (tuss4470_waveform_t){.tones = tones, .count = count, .clock_hz = clock_hz};
}

size_t tuss4470_waveform_fill(tuss4470_waveform_t *waveform, uint32_t *symbols, size_t capacity)
{
    size_t written = 0;
    while (written < capacity && !tuss4470_waveform_done(waveform)) {
        const tuss4470_tone_t *tone = &waveform->tones[waveform->tone];
        uint32_t half = half_period_ticks(tone->frequency_hz, waveform->clock_hz);
        symbols[written++] = half | ((half | LEVEL_HIGH) << 16);     /* low first: a falling edge starts the burst */
        if (++waveform->cycle == tone->cycles) {
            waveform->cycle = 0;
            ++waveform->tone;
        }
    }
    return written;
}

uint64_t tuss4470_waveform_duration_us(const tuss4470_tone_t *tones, size_t count, uint32_t clock_hz)
{
    uint64_t ticks = 0;
    for (size_t i = 0; i < count; ++i) {
        ticks += 2ULL * half_period_ticks(tones[i].frequency_hz, clock_hz) * tones[i].cycles;
    }
    return ticks * 1000000U / clock_hz;
}
