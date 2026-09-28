#include "usb_interface.h"

#include "TinyFrame.h"
#include "capture.h"
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

static TinyFrame framing;       /* host requests and their responses */
static TinyFrame log_framing;   /* device log events, frame IDs 0x8000-0xFFFF */
static bool write_failed;
static bool logs_enabled;
static bool capture_pending;
static TF_ID capture_id;
static int64_t last_tick_us;
static uint8_t payload[TF_PROTOCOL_CAPTURE_SIZE(CAPTURE_EDGE_CAPACITY)];

/* Responses wait for USB buffer space; log events are dropped when it is full. */
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

static tf_protocol_result_t capture_result(capture_status_t status)
{
    switch (status) {
    case CAPTURE_OK:
        return TF_PROTOCOL_RESULT_OK;
    case CAPTURE_BUSY:
        return TF_PROTOCOL_RESULT_BUSY;
    case CAPTURE_TIMEOUT:
        return TF_PROTOCOL_RESULT_TIMEOUT;
    case CAPTURE_OVERFLOW:
        return TF_PROTOCOL_RESULT_OVERFLOW;
    default:
        return TF_PROTOCOL_RESULT_DEVICE_ERROR;
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
    tf_protocol_device_info_t info = {.name = DEVICE_NAME, .tick_hz = CAPTURE_CLOCK_HZ, .max_edges = CAPTURE_EDGE_CAPACITY};
    respond_payload(request->type, request->frame_id, tf_protocol_encode_device_info(&info, payload, sizeof(payload)));
    logs_enabled = !write_failed;
    ESP_LOGI(TAG, "Device info requested; protocol %u", TF_PROTOCOL_VERSION);
}

/* The response is sent by poll_capture() once the capture has finished. */
static void start_capture(const TF_Msg *request)
{
    capture_status_t status = capture_start();
    if (status == CAPTURE_OK) {
        capture_pending = true;
        capture_id = request->frame_id;
    } else {
        respond_result(request->type, request->frame_id, capture_result(status));
    }
}

static void stop_capture(const TF_Msg *request)
{
    tf_protocol_result_t result = capture_result(capture_stop());
    if (capture_pending) {
        ESP_LOGI(TAG, "Host requested capture stop; result=%u", result);
        respond_result(TF_PROTOCOL_MSG_CAPTURE, capture_id, result == TF_PROTOCOL_RESULT_OK ? TF_PROTOCOL_RESULT_CANCELLED : result);
        capture_pending = false;
    }
    respond_result(request->type, request->frame_id, result);
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
    {TF_PROTOCOL_MSG_CAPTURE, 0, start_capture},
    {TF_PROTOCOL_MSG_STOP, 0, stop_capture},
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

static void poll_capture(void)
{
    if (!capture_pending || write_failed) {
        return;
    }
    const edge_trace_t *trace;
    capture_status_t status = capture_poll(&trace);
    if (status == CAPTURE_PENDING) {
        return;
    }
    capture_pending = false;
    if (status == CAPTURE_OK) {
        respond_payload(TF_PROTOCOL_MSG_CAPTURE, capture_id, tf_protocol_encode_capture(trace, payload, sizeof(payload)));
    } else {
        respond_result(TF_PROTOCOL_MSG_CAPTURE, capture_id, capture_result(status));
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
    capture_stop();
    capture_pending = false;
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
    poll_capture();
    forward_log();
    if (write_failed) {
        reset();
    }
}
