#include "usb_interface.h"

#include "TinyFrame.h"
#include "acquisition.h"
#include "edge_capture.h"
#include "device_log.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "tf_protocol.h"
#include "transmit.h"
#include "usb_transport.h"

#define DEVICE_NAME     "ESP32-C3 / TUSS4470"
#define RX_CHUNK_SIZE   64U
#define RX_WAIT_MS      10U
#define TF_TICK_US      10000
#define FRAME_OVERHEAD  14U     /* SOF, ID, length, type and two CRC32s */

_Static_assert(DEVICE_LOG_TEXT_CAPACITY - 1 <= TF_PROTOCOL_LOG_MAX_LENGTH, "Log entries must fit in one LOG frame");
_Static_assert(TF_SENDBUF_LEN >= TF_PROTOCOL_LOG_MAX_LENGTH + FRAME_OVERHEAD, "LOG frames must go out in one USB write");

static const char *TAG = "USB_INTERFACE";

#define EDGE_BATCH      512U
#define PAYLOAD_SIZE    TF_PROTOCOL_EDGES_SIZE(EDGE_BATCH)

_Static_assert(PAYLOAD_SIZE >= TF_PROTOCOL_VOUT_SIZE(ACQUISITION_VOUT_BLOCK), "Payload must hold a VOUT block");
_Static_assert(EDGE_BATCH >= EDGE_CAPTURE_READ_MIN_EDGES, "Edge batch too small for one read");

static TinyFrame framing;       /* requests, responses and stream data; data uses frame IDs 0x8000-0xFFFF */
static TinyFrame log_framing;   /* device log events, frame IDs 0x8000-0xFFFF */
static bool write_failed;
static bool logs_enabled;
static bool streaming;
static int64_t last_tick_us;
static uint8_t payload[PAYLOAD_SIZE];
static edge_t edges[EDGE_BATCH];

/* Responses and stream data wait for USB buffer space; log events are dropped when it is full. */
void TF_WriteImpl(TinyFrame *tf, const uint8_t *data, uint32_t length)
{
    if (tf == &log_framing) {
        usb_transport_try_write(data, length);
    } else if (!write_failed && usb_transport_write(data, length) != ESP_OK) {
        write_failed = true;
    }
}

static void respond(uint8_t type, TF_ID id, const uint8_t *data, size_t length)
{
    TF_Msg response = {.type = type, .frame_id = id, .data = data, .len = (TF_LEN)length};
    TF_Respond(&framing, &response);
}

static void respond_result(uint8_t type, TF_ID id, tf_protocol_result_t result)
{
    uint8_t data = (uint8_t)result;
    respond(type, id, &data, sizeof(data));
}

/* Sends the first length bytes of payload; a length of 0 means encoding failed. */
static void respond_payload(uint8_t type, TF_ID id, size_t length)
{
    if (length) {
        respond(type, id, payload, length);
    } else {
        respond_result(type, id, TF_PROTOCOL_RESULT_DEVICE_ERROR);
    }
}

static tf_protocol_result_t transmit_result(transmit_status_t status)
{
    switch (status) {
    case TRANSMIT_OK:
        return TF_PROTOCOL_RESULT_OK;
    case TRANSMIT_INVALID:
        return TF_PROTOCOL_RESULT_INVALID_REQUEST;
    case TRANSMIT_TIMEOUT:
        return TF_PROTOCOL_RESULT_TIMEOUT;
    default:
        return TF_PROTOCOL_RESULT_DEVICE_ERROR;
    }
}

static void get_device_info(const TF_Msg *request)
{
    tf_protocol_device_info_t info = {.name = DEVICE_NAME, .vout_rate_hz = ACQUISITION_VOUT_RATE_HZ, .edge_clock_hz = ACQUISITION_EDGE_CLOCK_HZ};
    respond_payload(request->type, request->frame_id, tf_protocol_encode_device_info(&info, payload, sizeof(payload)));
    logs_enabled = !write_failed;
    ESP_LOGI(TAG, "Device info requested; protocol %u", TF_PROTOCOL_VERSION);
}

static tf_protocol_result_t stop_streaming(void)
{
    if (!streaming) {
        return TF_PROTOCOL_RESULT_OK;
    }
    streaming = false;
    return acquisition_stop() == ESP_OK ? TF_PROTOCOL_RESULT_OK : TF_PROTOCOL_RESULT_DEVICE_ERROR;
}

static void start_stream(const TF_Msg *request)
{
    if (!streaming) {
        streaming = acquisition_start() == ESP_OK;
    }
    respond_result(request->type, request->frame_id, streaming ? TF_PROTOCOL_RESULT_OK : TF_PROTOCOL_RESULT_DEVICE_ERROR);
}

static void stop_stream(const TF_Msg *request)
{
    respond_result(request->type, request->frame_id, stop_streaming());
}

static void transmit(const TF_Msg *request)
{
    tone_burst_t tone = tf_protocol_decode_tone(request->data);
    respond_result(request->type, request->frame_id, transmit_result(transmit_send(&tone)));
}

typedef struct {
    uint8_t type;
    size_t payload_size;
    void (*handle)(const TF_Msg *request);
} command_t;

static const command_t commands[] = {
    {TF_PROTOCOL_MSG_GET_DEVICE_INFO, 0, get_device_info},
    {TF_PROTOCOL_MSG_STREAM_START, 0, start_stream},
    {TF_PROTOCOL_MSG_STREAM_STOP, 0, stop_stream},
    {TF_PROTOCOL_MSG_TRANSMIT, TF_PROTOCOL_TONE_SIZE, transmit},
};

static TF_Result on_request(TinyFrame *tf, TF_Msg *request)
{
    (void)tf;
    for (size_t i = 0; i < sizeof(commands) / sizeof(commands[0]); ++i) {
        if (commands[i].type == request->type && commands[i].payload_size == request->len) {
            commands[i].handle(request);
            return TF_STAY;
        }
    }
    ESP_LOGW(TAG, "Rejected request type %u with %u payload bytes", request->type, request->len);
    respond_result(request->type, request->frame_id, TF_PROTOCOL_RESULT_INVALID_REQUEST);
    return TF_STAY;
}

static void send_event(uint8_t type, const uint8_t *data, size_t length)
{
    TF_SendSimple(&framing, type, data, (TF_LEN)length);
}

/* Each returns false if data could not be encoded. */
static bool forward_vout(void)
{
    static uint16_t millivolts[ACQUISITION_VOUT_BLOCK];
    int64_t first_sample_ns;
    size_t count;
    while (!write_failed && (count = acquisition_read_vout(&first_sample_ns, millivolts))) {
        size_t length = tf_protocol_encode_vout(first_sample_ns, millivolts, count, payload, sizeof(payload));
        if (!length) {
            return false;
        }
        send_event(TF_PROTOCOL_MSG_VOUT_SAMPLES, payload, length);
    }
    return true;
}

static bool forward_out3(void)
{
    const uint32_t ns_per_tick = 1000000000U / ACQUISITION_EDGE_CLOCK_HZ;
    size_t count;
    while (!write_failed && (count = acquisition_read_out3(edges, EDGE_BATCH))) {
        size_t encoded;
        for (size_t sent = 0; sent < count; sent += encoded) {
            size_t length = tf_protocol_encode_edges(edges + sent, count - sent, ns_per_tick, payload, sizeof(payload), &encoded);
            if (!length) {
                return false;
            }
            send_event(TF_PROTOCOL_MSG_OUT3_EDGES, payload, length);
        }
    }
    return true;
}

static void end_stream(tf_protocol_result_t result)
{
    ESP_LOGE(TAG, "Stream ended: %s", result == TF_PROTOCOL_RESULT_OVERFLOW ? "data lost, buffer overflow" : "device error");
    stop_streaming();
    uint8_t data = (uint8_t)result;
    send_event(TF_PROTOCOL_MSG_STREAM_END, &data, sizeof(data));
}

/* Sends buffered stream data; ends the stream if the device lost data or failed. */
static void forward_stream(void)
{
    if (!streaming || write_failed) {
        return;
    }
    bool encoded = forward_vout() && forward_out3();
    acquisition_status_t status = acquisition_status();
    if (status == ACQUISITION_OVERFLOW) {
        end_stream(TF_PROTOCOL_RESULT_OVERFLOW);
    } else if (!encoded || status == ACQUISITION_ERROR) {
        end_stream(TF_PROTOCOL_RESULT_DEVICE_ERROR);
    }
}

static void forward_log(void)
{
    device_log_entry_t entry;
    if (logs_enabled && !write_failed && device_log_read(&entry)) {
        TF_SendSimple(&log_framing, TF_PROTOCOL_MSG_LOG, (const uint8_t *)entry.text, entry.length);
    }
}

/* Drops all host state: the host disconnected or stopped reading. */
static void reset(void)
{
    stop_streaming();
    logs_enabled = false;
    TF_ResetParser(&framing);
    write_failed = false;
}

esp_err_t usb_interface_init(void)
{
    TF_InitStatic(&framing, TF_MASTER);
    TF_InitStatic(&log_framing, TF_MASTER);
    TF_AddGenericListener(&framing, on_request);
    last_tick_us = esp_timer_get_time();
    return usb_transport_init();
}

void usb_interface_poll(void)
{
    uint8_t chunk[RX_CHUNK_SIZE];
    int count = usb_transport_read(chunk, sizeof(chunk), pdMS_TO_TICKS(RX_WAIT_MS));
    int64_t now = esp_timer_get_time();
    if (!usb_transport_connected()) {
        reset();
        last_tick_us = now;
        return;
    }
    if (count > 0) {
        TF_Accept(&framing, chunk, (uint32_t)count);
    }
    for (; now - last_tick_us >= TF_TICK_US; last_tick_us += TF_TICK_US) {
        TF_Tick(&framing);
    }
    forward_stream();
    forward_log();
    if (write_failed) {
        reset();
    }
}
