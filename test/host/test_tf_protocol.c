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

static uint32_t sample_edges[] = {100, 200, 300, 400};
static const edge_trace_t sample_trace = {.duration_ticks = 1000, .edge_count = 4, .edge_capacity = 4, .edges = sample_edges};

static void encodes_device_info(void)
{
    uint8_t out[32];
    tf_protocol_device_info_t info = {.name = "Dev", .tick_hz = 1000000, .max_edges = 1023};
    const uint8_t expected[] = {5, 0x40, 0x42, 0x0F, 0x00, 0xFF, 0x03, 'D', 'e', 'v'};
    CHECK(tf_protocol_encode_device_info(&info, out, sizeof(out)) == sizeof(expected));
    CHECK(memcmp(out, expected, sizeof(expected)) == 0);
    CHECK(tf_protocol_encode_device_info(&info, out, sizeof(expected) - 1) == 0);
    info.name = "";
    CHECK(tf_protocol_encode_device_info(&info, out, sizeof(out)) == 0);
}

static void encodes_capture(void)
{
    uint8_t out[64];
    const uint8_t expected[] = {
        0, 0, 0xE8, 0x03, 0, 0, 4, 0,
        100, 0, 0, 0, 200, 0, 0, 0, 0x2C, 0x01, 0, 0, 0x90, 0x01, 0, 0,
    };
    CHECK(tf_protocol_encode_capture(&sample_trace, out, sizeof(out)) == sizeof(expected));
    CHECK(memcmp(out, expected, sizeof(expected)) == 0);
    CHECK(tf_protocol_encode_capture(&sample_trace, out, sizeof(expected) - 1) == 0);
    edge_trace_t empty = {.duration_ticks = 0};
    CHECK(tf_protocol_encode_capture(&empty, out, sizeof(out)) == 0);
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

/* Frames as the firmware sends them: responses echo request IDs, log events use device IDs. */
static void print_frames(void)
{
    TinyFrame framing;
    TinyFrame log_framing;
    TF_InitStatic(&framing, TF_MASTER);
    TF_InitStatic(&log_framing, TF_MASTER);

    uint8_t payload[TF_PROTOCOL_CAPTURE_SIZE(4)];
    size_t length = tf_protocol_encode_capture(&sample_trace, payload, sizeof(payload));
    TF_Msg capture = {.type = TF_PROTOCOL_MSG_CAPTURE, .frame_id = 5, .data = payload, .len = (TF_LEN)length};
    TF_Respond(&framing, &capture);
    print_frame();

    uint8_t result = TF_PROTOCOL_RESULT_CANCELLED;
    TF_Msg cancelled = {.type = TF_PROTOCOL_MSG_CAPTURE, .frame_id = 0x7FFF, .data = &result, .len = 1};
    TF_Respond(&framing, &cancelled);
    print_frame();

    char text[TF_PROTOCOL_LOG_MAX_LENGTH];
    memset(text, 'x', sizeof(text));
    TF_SendSimple(&log_framing, TF_PROTOCOL_MSG_LOG, (const uint8_t *)"hello\n", 6);
    print_frame();
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
    encodes_capture();
    decodes_tone();
    return 0;
}
