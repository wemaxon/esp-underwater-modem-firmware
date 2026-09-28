#pragma once

/*
 * Payloads of the TinyFrame USB interface to the host (README "USB interface
 * protocol"); not the acoustic modem protocol. Pure encoding without ESP-IDF or
 * TinyFrame dependencies, so it can be tested on the host.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "edge_trace.h"
#include "transmit.h"

#define TF_PROTOCOL_VERSION 5

typedef enum {
    TF_PROTOCOL_MSG_GET_DEVICE_INFO = 1,
    TF_PROTOCOL_MSG_CAPTURE = 2,
    TF_PROTOCOL_MSG_STOP = 3,
    TF_PROTOCOL_MSG_TRANSMIT = 4,
    TF_PROTOCOL_MSG_LOG = 5,
} tf_protocol_message_t;

typedef enum {
    TF_PROTOCOL_RESULT_OK = 0,
    TF_PROTOCOL_RESULT_INVALID_REQUEST = 1,
    TF_PROTOCOL_RESULT_BUSY = 2,
    TF_PROTOCOL_RESULT_TIMEOUT = 3,
    TF_PROTOCOL_RESULT_CANCELLED = 4,
    TF_PROTOCOL_RESULT_OVERFLOW = 5,
    TF_PROTOCOL_RESULT_DEVICE_ERROR = 6,
} tf_protocol_result_t;

#define TF_PROTOCOL_LOG_MAX_LENGTH       255U
#define TF_PROTOCOL_TONE_SIZE            6U
#define TF_PROTOCOL_INFO_HEADER_SIZE     7U
#define TF_PROTOCOL_CAPTURE_HEADER_SIZE  8U
#define TF_PROTOCOL_CAPTURE_SIZE(edges)  (TF_PROTOCOL_CAPTURE_HEADER_SIZE + 4U * (edges))

typedef struct {
    const char *name;
    uint32_t tick_hz;
    uint16_t max_edges;
} tf_protocol_device_info_t;

/* Encoders return the payload length, or 0 if the input is invalid or does not fit. */
size_t tf_protocol_encode_device_info(const tf_protocol_device_info_t *info, uint8_t *out, size_t capacity);
size_t tf_protocol_encode_capture(const edge_trace_t *trace, uint8_t *out, size_t capacity);

/* Decodes a TRANSMIT request payload of exactly TF_PROTOCOL_TONE_SIZE bytes. */
tone_burst_t tf_protocol_decode_tone(const uint8_t *data);
