#pragma once

/*
 * Transmit waveforms: consecutive tones, played phase-continuously as square
 * waves on IO2. Pure code without ESP-IDF dependencies, so it can be tested on
 * the host.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* In IO mode 1 the chip ends a burst if IO2 does not toggle for 64 us, so tones
 * need a half period below that; there is no silence within a waveform. */
#define TUSS4470_TONE_MIN_HZ  10000U
#define TUSS4470_TONE_MAX_HZ  1000000U

/* Clock of the IO2 square wave: each tone is played with whole half periods of it. */
#define TUSS4470_TRANSMIT_CLOCK_HZ 20000000U

typedef struct {
    uint32_t frequency_hz;
    uint32_t cycles;
} tuss4470_tone_t;

/* Position in a waveform while it is converted to RMT symbols. */
typedef struct {
    const tuss4470_tone_t *tones;
    size_t count;
    size_t tone;
    uint32_t cycle;
    uint32_t clock_hz;
} tuss4470_waveform_t;

void tuss4470_waveform_start(tuss4470_waveform_t *waveform, const tuss4470_tone_t *tones, size_t count, uint32_t clock_hz);

/*
 * Writes the next cycles as raw 32-bit RMT symbols (low half, then high half,
 * each rounded to whole clock ticks) and returns how many were written.
 */
size_t tuss4470_waveform_fill(tuss4470_waveform_t *waveform, uint32_t *symbols, size_t capacity);

static inline bool tuss4470_waveform_done(const tuss4470_waveform_t *waveform)
{
    return waveform->tone == waveform->count;
}

/* Duration of the tones as played, in microseconds. */
uint64_t tuss4470_waveform_duration_us(const tuss4470_tone_t *tones, size_t count, uint32_t clock_hz);
