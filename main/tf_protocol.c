#include "tf_protocol.h"

#include <string.h>

#define INFO_HEADER_SIZE 9U

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

static void put_u64(uint8_t *out, uint64_t value)
{
    put_u32(out, (uint32_t)value);
    put_u32(out + 4, (uint32_t)(value >> 32));
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
    size_t length = INFO_HEADER_SIZE + name_length;
    if (!name_length || length > capacity) {
        return 0;
    }
    out[0] = TF_PROTOCOL_VERSION;
    put_u32(out + 1, info->vout_rate_hz);
    put_u32(out + 5, info->edge_clock_hz);
    memcpy(out + INFO_HEADER_SIZE, info->name, name_length);
    return length;
}

size_t tf_protocol_encode_afe(tf_protocol_result_t result, const uint8_t *values, uint8_t *out, size_t capacity)
{
    size_t length = result == TF_PROTOCOL_RESULT_OK ? 1 + TF_PROTOCOL_AFE_SIZE : 1;
    if (length > capacity) {
        return 0;
    }
    out[0] = (uint8_t)result;
    if (result == TF_PROTOCOL_RESULT_OK) {
        memcpy(out + 1, values, TF_PROTOCOL_AFE_SIZE);
    }
    return length;
}

size_t tf_protocol_encode_vout(int64_t first_sample_ns, const uint16_t *millivolts, size_t count, uint8_t *out, size_t capacity)
{
    if (!count || count > UINT16_MAX || first_sample_ns < 0 || TF_PROTOCOL_VOUT_SIZE(count) > capacity) {
        return 0;
    }
    put_u64(out, (uint64_t)first_sample_ns);
    put_u16(out + 8, (uint16_t)count);
    for (size_t i = 0; i < count; ++i) {
        put_u16(out + 10 + 2 * i, millivolts[i]);
    }
    return TF_PROTOCOL_VOUT_SIZE(count);
}

/* Interval to the previous edge in ticks, or 0 if the edge cannot continue the run. */
static uint32_t interval_ticks(const edge_t *previous, const edge_t *edge, uint32_t ns_per_tick)
{
    int64_t interval_ns = edge->time_ns - previous->time_ns;
    if (edge->level == previous->level || interval_ns <= 0 || interval_ns % ns_per_tick) {
        return 0;
    }
    int64_t ticks = interval_ns / ns_per_tick;
    return ticks <= UINT16_MAX ? (uint32_t)ticks : 0;
}

size_t tf_protocol_encode_edges(const edge_t *edges, size_t count, uint32_t ns_per_tick,
                                uint8_t *out, size_t capacity, size_t *encoded)
{
    *encoded = 0;
    if (!count || edges[0].time_ns < 0 || TF_PROTOCOL_EDGES_SIZE(1) > capacity) {
        return 0;
    }
    size_t n = 1;
    while (n < count && n < UINT16_MAX && TF_PROTOCOL_EDGES_SIZE(n + 1) <= capacity) {
        uint32_t ticks = interval_ticks(&edges[n - 1], &edges[n], ns_per_tick);
        if (!ticks) {
            break;
        }
        put_u16(out + TF_PROTOCOL_EDGES_SIZE(n), (uint16_t)ticks);
        ++n;
    }
    put_u64(out, (uint64_t)edges[0].time_ns);
    out[8] = edges[0].level;
    put_u16(out + 9, (uint16_t)n);
    *encoded = n;
    return TF_PROTOCOL_EDGES_SIZE(n);
}

tone_burst_t tf_protocol_decode_tone(const uint8_t *data)
{
    return (tone_burst_t){.frequency_hz = get_u32(data), .cycles = get_u16(data + 4)};
}
