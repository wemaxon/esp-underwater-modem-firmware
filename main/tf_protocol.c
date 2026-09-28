#include "tf_protocol.h"

#include <string.h>

static void put_u16(uint8_t *out, uint16_t value)
{
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8);
}

static void put_u32(uint8_t *out, uint32_t value)
{
    put_u16(out, (uint16_t)value);
    put_u16(out + 2, (uint16_t)(value >> 16));
}

static uint16_t get_u16(const uint8_t *in)
{
    return (uint16_t)(in[0] | (in[1] << 8));
}

static uint32_t get_u32(const uint8_t *in)
{
    return get_u16(in) | ((uint32_t)get_u16(in + 2) << 16);
}

size_t tf_protocol_encode_device_info(const tf_protocol_device_info_t *info, uint8_t *out, size_t capacity)
{
    size_t name_length = strlen(info->name);
    size_t length = TF_PROTOCOL_INFO_HEADER_SIZE + name_length;
    if (!name_length || length > capacity) {
        return 0;
    }
    out[0] = TF_PROTOCOL_VERSION;
    put_u32(out + 1, info->tick_hz);
    put_u16(out + 5, info->max_edges);
    memcpy(out + TF_PROTOCOL_INFO_HEADER_SIZE, info->name, name_length);
    return length;
}

size_t tf_protocol_encode_capture(const edge_trace_t *trace, uint8_t *out, size_t capacity)
{
    if (!trace->duration_ticks || trace->edge_count > UINT16_MAX || TF_PROTOCOL_CAPTURE_SIZE(trace->edge_count) > capacity) {
        return 0;
    }
    out[0] = TF_PROTOCOL_RESULT_OK;
    out[1] = trace->initial_level;
    put_u32(out + 2, trace->duration_ticks);
    put_u16(out + 6, (uint16_t)trace->edge_count);
    for (size_t i = 0; i < trace->edge_count; ++i) {
        put_u32(out + TF_PROTOCOL_CAPTURE_HEADER_SIZE + 4 * i, trace->edges[i]);
    }
    return TF_PROTOCOL_CAPTURE_SIZE(trace->edge_count);
}

tone_burst_t tf_protocol_decode_tone(const uint8_t *data)
{
    return (tone_burst_t){.frequency_hz = get_u32(data), .cycles = get_u16(data + 4)};
}
