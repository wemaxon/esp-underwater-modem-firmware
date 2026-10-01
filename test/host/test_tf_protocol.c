/*
 * Payload encoding tests. With --frames, prints TinyFrame-encoded frames as
 * hex lines instead, for the GUI's C/Python interoperability test.
 */

#include <string.h>

#include "TinyFrame.h"
#include "check.h"
#include "tf_protocol.h"

static uint8_t written[4096];
static size_t written_length;

void TF_WriteImpl(TinyFrame *tf, const uint8_t *data, uint32_t length)
{
    (void)tf;
    CHECK(written_length + length <= sizeof(written));
    memcpy(written + written_length, data, length);
    written_length += length;
}

static const uint16_t sample_millivolts[] = {1234, 3300};
static const edge_t sample_edges[] = {{1000, true}, {1100, false}, {1300, true}};

static void encodes_device_info(void)
{
    uint8_t out[32];
    tf_protocol_device_info_t info = {.name = "Dev", .vout_rate_hz = 20000, .edge_clock_hz = 10000000};
    const uint8_t expected[] = {8, 0x20, 0x4E, 0, 0, 0x80, 0x96, 0x98, 0, 'D', 'e', 'v'};
    CHECK(tf_protocol_encode_device_info(&info, out, sizeof(out)) == sizeof(expected));
    CHECK(memcmp(out, expected, sizeof(expected)) == 0);
    CHECK(tf_protocol_encode_device_info(&info, out, sizeof(expected) - 1) == 0);
    info.name = "";
    CHECK(tf_protocol_encode_device_info(&info, out, sizeof(out)) == 0);
}

static void encodes_vout(void)
{
    uint8_t out[16];
    const uint8_t expected[] = {0xE8, 0x03, 0, 0, 0, 0, 0, 0, 2, 0, 0xD2, 0x04, 0xE4, 0x0C};
    CHECK(tf_protocol_encode_vout(1000, sample_millivolts, 2, out, sizeof(out)) == sizeof(expected));
    CHECK(memcmp(out, expected, sizeof(expected)) == 0);
    CHECK(tf_protocol_encode_vout(1000, sample_millivolts, 2, out, sizeof(expected) - 1) == 0);
    CHECK(tf_protocol_encode_vout(-1, sample_millivolts, 2, out, sizeof(out)) == 0);
    CHECK(tf_protocol_encode_vout(1000, sample_millivolts, 0, out, sizeof(out)) == 0);
}

static void encodes_edges_as_tick_intervals(void)
{
    uint8_t out[32];
    size_t encoded;
    const uint8_t expected[] = {0xE8, 0x03, 0, 0, 0, 0, 0, 0, 1, 3, 0, 1, 0, 2, 0};
    CHECK(tf_protocol_encode_edges(sample_edges, 3, 100, out, sizeof(out), &encoded) == sizeof(expected));
    CHECK(encoded == 3);
    CHECK(memcmp(out, expected, sizeof(expected)) == 0);

    CHECK(tf_protocol_encode_edges(sample_edges, 3, 100, out, TF_PROTOCOL_EDGES_SIZE(2), &encoded) == TF_PROTOCOL_EDGES_SIZE(2));
    CHECK(encoded == 2);
}

static void starts_a_new_run_where_edges_cannot_continue(void)
{
    uint8_t out[32];
    size_t encoded;
    const edge_t same_level[] = {{0, true}, {100, true}};
    const edge_t off_tick[] = {{0, true}, {150, false}};
    const edge_t too_far[] = {{0, true}, {100LL * 65536, false}};
    CHECK(tf_protocol_encode_edges(same_level, 2, 100, out, sizeof(out), &encoded) == TF_PROTOCOL_EDGES_SIZE(1) && encoded == 1);
    CHECK(tf_protocol_encode_edges(off_tick, 2, 100, out, sizeof(out), &encoded) == TF_PROTOCOL_EDGES_SIZE(1) && encoded == 1);
    CHECK(tf_protocol_encode_edges(too_far, 2, 100, out, sizeof(out), &encoded) == TF_PROTOCOL_EDGES_SIZE(1) && encoded == 1);
    CHECK(tf_protocol_encode_edges(sample_edges, 3, 100, out, TF_PROTOCOL_EDGES_SIZE(1) - 1, &encoded) == 0 && encoded == 0);
}

static void encodes_config(void)
{
    const uint8_t values[TF_PROTOCOL_CONFIG_SIZE] = {0x00, 0x10, 0x00, 0x02, 0x17, 0x94, 0x20, 0x80};
    const uint8_t expected[] = {0, 0x00, 0x10, 0x00, 0x02, 0x17, 0x94, 0x20, 0x80};
    uint8_t out[10];
    CHECK(tf_protocol_encode_config(TF_PROTOCOL_RESULT_OK, values, out, sizeof(out)) == sizeof(expected));
    CHECK(memcmp(out, expected, sizeof(expected)) == 0);
    CHECK(tf_protocol_encode_config(TF_PROTOCOL_RESULT_DEVICE_ERROR, values, out, sizeof(out)) == 1 && out[0] == TF_PROTOCOL_RESULT_DEVICE_ERROR);
    CHECK(tf_protocol_encode_config(TF_PROTOCOL_RESULT_OK, values, out, sizeof(expected) - 1) == 0);
}

static void decodes_tone(void)
{
    const uint8_t payload[] = {0x40, 0x9C, 0x00, 0x00, 0x20, 0x00};
    tone_burst_t tone = tf_protocol_decode_tone(payload);
    CHECK(tone.frequency_hz == 40000 && tone.cycles == 32);
}

static void print_frame(void)
{
    for (size_t i = 0; i < written_length; ++i) {
        printf("%02x", written[i]);
    }
    printf("\n");
    written_length = 0;
}

/* Frames as the firmware sends them: responses echo request IDs, events use device IDs. */
static void print_frames(void)
{
    TinyFrame framing;
    TinyFrame log_framing;
    TF_InitStatic(&framing, TF_MASTER);
    TF_InitStatic(&log_framing, TF_MASTER);

    uint8_t result = TF_PROTOCOL_RESULT_OK;
    TF_Msg started = {.type = TF_PROTOCOL_MSG_STREAM_START, .frame_id = 5, .data = &result, .len = 1};
    TF_Respond(&framing, &started);
    print_frame();

    uint8_t payload[64];
    size_t encoded;
    size_t length = tf_protocol_encode_vout(1000, sample_millivolts, 2, payload, sizeof(payload));
    TF_SendSimple(&framing, TF_PROTOCOL_MSG_VOUT_SAMPLES, payload, (TF_LEN)length);
    print_frame();
    length = tf_protocol_encode_edges(sample_edges, 3, 100, payload, sizeof(payload), &encoded);
    TF_SendSimple(&framing, TF_PROTOCOL_MSG_OUT3_EDGES, payload, (TF_LEN)length);
    print_frame();
    result = TF_PROTOCOL_RESULT_OVERFLOW;
    TF_SendSimple(&framing, TF_PROTOCOL_MSG_STREAM_END, &result, 1);
    print_frame();

    char text[TF_PROTOCOL_LOG_MAX_LENGTH];
    memset(text, 'x', sizeof(text));
    TF_SendSimple(&log_framing, TF_PROTOCOL_MSG_LOG, (const uint8_t *)text, sizeof(text));
    print_frame();
}

int main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "--frames") == 0) {
        print_frames();
        return 0;
    }
    encodes_device_info();
    encodes_vout();
    encodes_config();
    encodes_edges_as_tick_intervals();
    starts_a_new_run_where_edges_cannot_continue();
    decodes_tone();
    return 0;
}
