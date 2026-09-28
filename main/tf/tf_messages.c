#include "tf/tf_messages.h"

#include "TinyFrame.h"
#include "capture.h"
#include "device_log.h"
#include "esp_log.h"
#include "tf/tf_protocol.h"
#include "usb_transport.h"

static TinyFrame framing;
static bool request_pending;
static bool write_failed;
static TF_ID capture_id;
static bool logs_enabled;
static bool sending_log;
static const char *TAG = "TF";

_Static_assert(TF_SENDBUF_LEN >= DEVICE_LOG_TEXT_CAPACITY - 1 + 14, "Log frames must fit in one transport write");

void TF_WriteImpl(TinyFrame *tf, const uint8_t *data, uint32_t length)
{
    (void)tf;
    if (sending_log) {
        usb_transport_try_write(data, length);
        return;
    }
    if (!write_failed && usb_transport_write(data, length) != ESP_OK) {
        write_failed = true;
    }
}

static void respond(TF_TYPE type, TF_ID id, const uint8_t *data, size_t length)
{
    TF_Msg response = {.type = type, .frame_id = id, .data = data, .len = (TF_LEN)length};
    TF_Respond(&framing, &response);
}

static uint8_t wire_result(capture_status_t status)
{
    switch (status) {
        case CAPTURE_OK:
            return TF_USB_RESULT_OK;
        case CAPTURE_BUSY:
            return TF_USB_RESULT_BUSY;
        case CAPTURE_TIMEOUT:
            return TF_USB_RESULT_TIMEOUT;
        case CAPTURE_OVERFLOW:
            return TF_USB_RESULT_OVERFLOW;
        default:
            return TF_USB_RESULT_DEVICE_ERROR;
    }
}

static uint8_t transmit_result(transmit_status_t status)
{
    switch (status) {
        case TRANSMIT_OK:
            return TF_USB_RESULT_OK;
        case TRANSMIT_INVALID:
            return TF_USB_RESULT_INVALID_REQUEST;
        case TRANSMIT_TIMEOUT:
            return TF_USB_RESULT_TIMEOUT;
        default:
            return TF_USB_RESULT_DEVICE_ERROR;
    }
}

static TF_Result command(TinyFrame *tf, TF_Msg *message)
{
    (void)tf;
    uint8_t result = TF_USB_RESULT_OK;
    if (message->type == TF_USB_MSG_TRANSMIT) {
        tone_burst_t tone;
        if (!tf_protocol_decode_tone(message->data, message->len, &tone)) {
            result = TF_USB_RESULT_INVALID_REQUEST;
        } else {
            result = transmit_result(transmit_send(&tone));
        }
    } else if (message->len) {
        result = TF_USB_RESULT_INVALID_REQUEST;
    } else if (message->type == TF_USB_MSG_GET_DEVICE_INFO) {
        tf_payload_t payload = tf_protocol_device_info("ESP32-C3 / TUSS4470", capture_clock_hz(), CAPTURE_OUT3_EDGE_CAPACITY);
        respond(message->type, message->frame_id, payload.data, payload.length);
        logs_enabled = !write_failed;
        ESP_LOGI(TAG, "Device info requested; protocol %u", TF_USB_PROTOCOL_VERSION);
        return TF_STAY;
    } else if (message->type == TF_USB_MSG_CAPTURE) {
        capture_status_t status = capture_start();
        if (status == CAPTURE_OK) {
            request_pending = true;
            capture_id = message->frame_id;
            return TF_STAY;
        }
        result = wire_result(status);
    } else if (message->type == TF_USB_MSG_STOP) {
        result = wire_result(capture_stop());
        if (request_pending) {
            ESP_LOGI(TAG, "Host requested capture stop; result=%u", result);
            uint8_t cancelled = result == TF_USB_RESULT_OK ? TF_USB_RESULT_CANCELLED : result;
            respond(TF_USB_MSG_CAPTURE, capture_id, &cancelled, 1);
            request_pending = false;
        }
    } else {
        result = TF_USB_RESULT_INVALID_REQUEST;
    }
    respond(message->type, message->frame_id, &result, 1);
    return TF_STAY;
}

void tf_messages_init(void)
{
    TF_InitStatic(&framing, TF_MASTER);
    TF_AddGenericListener(&framing, command);
}

void tf_messages_accept(const uint8_t *data, size_t length)
{
    TF_Accept(&framing, data, length);
}

void tf_messages_tick(void)
{
    TF_Tick(&framing);
}

static void poll_capture(void)
{
    if (!request_pending || write_failed) {
        return;
    }
    const capture_result_t *capture;
    capture_status_t status = capture_poll(&capture);
    if (status == CAPTURE_PENDING) {
        return;
    }
    request_pending = false;
    if (status == CAPTURE_OK) {
        tf_payload_t payload = tf_protocol_capture(capture);
        respond(TF_USB_MSG_CAPTURE, capture_id, payload.data, payload.length);
    } else {
        uint8_t result = wire_result(status);
        respond(TF_USB_MSG_CAPTURE, capture_id, &result, 1);
    }
}

void tf_messages_poll(void)
{
    poll_capture();
    if (logs_enabled && !write_failed) {
        device_log_entry_t entry;
        if (device_log_read(&entry)) {
            sending_log = true;
            TF_SendSimple(&framing, TF_USB_MSG_LOG, (const uint8_t *)entry.text, entry.length);
            sending_log = false;
        }
    }
}

void tf_messages_reset(void)
{
    capture_stop();
    request_pending = false;
    logs_enabled = false;
    TF_ResetParser(&framing);
    write_failed = false;
}

bool tf_messages_write_failed(void)
{
    return write_failed;
}
