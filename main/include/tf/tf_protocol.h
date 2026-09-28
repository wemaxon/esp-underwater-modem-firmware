#pragma once

#include <stddef.h>
#include <stdint.h>
#include "capture.h"
#include "transmit.h"

enum { TF_USB_PROTOCOL_VERSION = 4 };

typedef enum {
    TF_USB_MSG_GET_DEVICE_INFO = 1,
    TF_USB_MSG_CAPTURE = 2,
    TF_USB_MSG_STOP = 3,
    TF_USB_MSG_TRANSMIT = 4,
} tf_usb_message_t;

typedef enum {
    TF_USB_RESULT_OK = 0,
    TF_USB_RESULT_INVALID_REQUEST = 1,
    TF_USB_RESULT_BUSY = 2,
    TF_USB_RESULT_TIMEOUT = 3,
    TF_USB_RESULT_CANCELLED = 4,
    TF_USB_RESULT_OVERFLOW = 5,
    TF_USB_RESULT_DEVICE_ERROR = 6,
} tf_usb_result_t;

typedef struct {
    const uint8_t *data;
    size_t length;
} tf_payload_t;

tf_payload_t tf_protocol_device_info(const char *name, uint32_t tick_hz, uint16_t max_edges);
tf_payload_t tf_protocol_capture(const capture_result_t *capture);
bool tf_protocol_decode_tone(const uint8_t *data, size_t length, tone_burst_t *tone);
