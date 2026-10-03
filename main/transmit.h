#pragma once

/*
 * Transmits waveforms, with VDRV powered only while transmitting. Non-blocking:
 * transmit_start() begins, transmit_poll() reports the outcome.
 */

#include <stdbool.h>
#include <stddef.h>

#include "tuss4470_waveform.h"

typedef enum {
    TRANSMIT_OK,
    TRANSMIT_PENDING,
    TRANSMIT_INVALID,
    TRANSMIT_TIMEOUT,
    TRANSMIT_ERROR,
} transmit_status_t;

/* Returns TRANSMIT_PENDING once started; tones must stay valid until the outcome is reported. */
transmit_status_t transmit_start(const tuss4470_tone_t *tones, size_t count);
/* TRANSMIT_PENDING while transmitting, then the outcome, once. */
transmit_status_t transmit_poll(void);
bool transmit_busy(void);
