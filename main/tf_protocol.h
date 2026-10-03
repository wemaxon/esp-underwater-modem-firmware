#pragma once

/*
 * Payloads of the TinyFrame USB interface to the host (README "USB interface
 * protocol"); not the acoustic modem protocol. Pure encoding without ESP-IDF or
 * TinyFrame dependencies, so it can be tested on the host.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "edge_decoder.h"
#include "tuss4470_waveform.h"

#define TF_PROTOCOL_VERSION 9

typedef enum {
    TF_PROTOCOL_MSG_GET_DEVICE_INFO = 1,
    TF_PROTOCOL_MSG_STREAM_START = 2,
    TF_PROTOCOL_MSG_STREAM_STOP = 3,
    TF_PROTOCOL_MSG_TRANSMIT = 4,
    TF_PROTOCOL_MSG_LOG = 5,            /* device event */
    TF_PROTOCOL_MSG_VOUT_SAMPLES = 6,   /* device event */
    TF_PROTOCOL_MSG_OUT3_EDGES = 7,     /* device event */
    TF_PROTOCOL_MSG_STREAM_END = 8,     /* device event */
    TF_PROTOCOL_MSG_GET_CONFIG = 9,
    TF_PROTOCOL_MSG_SET_CONFIG = 10,
} tf_protocol_message_t;

typedef enum {
    TF_PROTOCOL_RESULT_OK = 0,
    TF_PROTOCOL_RESULT_INVALID_REQUEST = 1,
    TF_PROTOCOL_RESULT_TIMEOUT = 2,
    TF_PROTOCOL_RESULT_OVERFLOW = 3,
    TF_PROTOCOL_RESULT_DEVICE_ERROR = 4,
    TF_PROTOCOL_RESULT_BUSY = 5,
} tf_protocol_result_t;

#define TF_PROTOCOL_LOG_MAX_LENGTH       255U
#define TF_PROTOCOL_TONE_SIZE            8U      /* one tone of a TRANSMIT waveform */
#define TF_PROTOCOL_CONFIG_SIZE          8U      /* TUSS4470 configuration register values */
#define TF_PROTOCOL_VOUT_SIZE(samples)   (10U + 2U * (samples))
#define TF_PROTOCOL_EDGES_SIZE(edges)    (11U + 2U * ((edges) - 1U))

typedef struct {
    const char *name;
    uint32_t vout_rate_hz;
    uint32_t edge_clock_hz;
    uint32_t transmit_clock_hz;
} tf_protocol_device_info_t;

/* Encoders return the payload length, or 0 if the input is invalid or does not fit. */
size_t tf_protocol_encode_device_info(const tf_protocol_device_info_t *info, uint8_t *out, size_t capacity);
/* Result, followed by the configuration register values if the result is OK. */
size_t tf_protocol_encode_config(tf_protocol_result_t result, const uint8_t *values, uint8_t *out, size_t capacity);
size_t tf_protocol_encode_vout(int64_t first_sample_ns, const uint16_t *millivolts, size_t count, uint8_t *out, size_t capacity);

/*
 * Encodes a run of consecutive edges: as many as fit, alternate in level and
 * are spaced by at most 65535 ticks of ns_per_tick. Sets *encoded to the number
 * of edges included (at least one if any fit).
 */
size_t tf_protocol_encode_edges(const edge_t *edges, size_t count, uint32_t ns_per_tick,
                                uint8_t *out, size_t capacity, size_t *encoded);

/* Decodes a TRANSMIT waveform into tones; returns their number, or 0 if the payload is invalid or too long. */
size_t tf_protocol_decode_waveform(const uint8_t *data, size_t length, tuss4470_tone_t *tones, size_t capacity);
