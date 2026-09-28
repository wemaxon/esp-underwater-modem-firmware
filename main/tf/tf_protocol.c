#include "tf/tf_protocol.h"

#include <string.h>

enum { CAPTURE_HEADER_SIZE = 8, INFO_HEADER_SIZE = 7 };
static uint8_t payload[CAPTURE_HEADER_SIZE + 4 * CAPTURE_OUT3_EDGE_CAPACITY];

bool tf_protocol_decode_tone(const uint8_t *data, size_t length, tone_burst_t *tone)
{
    if (length != 6) {
        return false;
    }
    tone->frequency_hz = (uint32_t)data[0] | ((uint32_t)data[1] << 8) | ((uint32_t)data[2] << 16) | ((uint32_t)data[3] << 24);
    tone->cycles = (uint16_t)data[4] | ((uint16_t)data[5] << 8);
    return true;
}

static void put_u16(uint8_t *dest, uint16_t value)
{
    dest[0] = (uint8_t)value;
    dest[1] = (uint8_t)(value >> 8);
}

static void put_u32(uint8_t *dest, uint32_t value)
{
    put_u16(dest, (uint16_t)value);
    put_u16(dest + 2, (uint16_t)(value >> 16));
}

static tf_payload_t invalid_payload(void)
{
    payload[0] = TF_USB_RESULT_DEVICE_ERROR;
    return (tf_payload_t){payload, 1};
}

tf_payload_t tf_protocol_device_info(const char *name, uint32_t tick_hz, uint16_t max_edges)
{
    size_t length = strlen(name);
    if (!length || length > sizeof(payload) - INFO_HEADER_SIZE) {
        return invalid_payload();
    }
    payload[0] = TF_USB_PROTOCOL_VERSION;
    put_u32(payload + 1, tick_hz);
    put_u16(payload + 5, max_edges);
    memcpy(payload + INFO_HEADER_SIZE, name, length);
    return (tf_payload_t){payload, INFO_HEADER_SIZE + length};
}

tf_payload_t tf_protocol_capture(const capture_result_t *capture)
{
    if (!capture->duration_ticks || capture->edge_count > CAPTURE_OUT3_EDGE_CAPACITY) {
        return invalid_payload();
    }
    payload[0] = TF_USB_RESULT_OK;
    payload[1] = capture->initial_high;
    put_u32(payload + 2, capture->duration_ticks);
    put_u16(payload + 6, (uint16_t)capture->edge_count);
    for (size_t i = 0; i < capture->edge_count; ++i) {
        put_u32(payload + CAPTURE_HEADER_SIZE + 4 * i, capture->edges[i]);
    }
    return (tf_payload_t){payload, CAPTURE_HEADER_SIZE + 4 * capture->edge_count};
}
