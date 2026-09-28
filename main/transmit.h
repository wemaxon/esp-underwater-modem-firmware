#pragma once

#include <stdint.h>

typedef struct {
    uint32_t frequency_hz;
    uint16_t cycles;
} tone_burst_t;

typedef enum {
    TRANSMIT_OK,
    TRANSMIT_INVALID,
    TRANSMIT_TIMEOUT,
    TRANSMIT_ERROR,
} transmit_status_t;

/* Sends one tone burst and returns once it is complete. VDRV is powered only during the burst. */
transmit_status_t transmit_send(const tone_burst_t *tone);
