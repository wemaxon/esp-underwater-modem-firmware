#include "capture.h"

#include "esp_log.h"
#include "esp_timer.h"

#define CAPTURE_TIMEOUT_US      (2000 * 1000)
#define CAPTURE_MIN_PULSE_NS    1000U
#define CAPTURE_IDLE_NS         (20U * 1000 * 1000)

static const char *TAG = "CAPTURE";

static edge_capture_handle_t receiver;
static bool active;
static bool faulted;            /* a failed stop leaves the receiver in an unknown state */
static int64_t deadline_us;
static uint32_t edges[CAPTURE_EDGE_CAPACITY];
static edge_trace_t trace = {.edges = edges, .edge_capacity = CAPTURE_EDGE_CAPACITY};

esp_err_t capture_init(gpio_num_t out3_gpio)
{
    edge_capture_config_t config = {
        .gpio = out3_gpio,
        .resolution_hz = CAPTURE_CLOCK_HZ,
        .symbol_capacity = CAPTURE_SYMBOL_CAPACITY,
        .min_pulse_ns = CAPTURE_MIN_PULSE_NS,
        .idle_timeout_ns = CAPTURE_IDLE_NS,
    };
    return edge_capture_new(&config, &receiver);
}

capture_status_t capture_start(void)
{
    if (active) {
        ESP_LOGW(TAG, "Rejected request: OUT3 capture already active");
        return CAPTURE_BUSY;
    }
    if (faulted) {
        ESP_LOGE(TAG, "Cannot arm OUT3: receiver stop previously failed");
        return CAPTURE_ERROR;
    }
    esp_err_t error = edge_capture_start(receiver);
    if (error != ESP_OK) {
        ESP_LOGE(TAG, "Failed to arm OUT3: %s", esp_err_to_name(error));
        return CAPTURE_ERROR;
    }
    active = true;
    deadline_us = esp_timer_get_time() + CAPTURE_TIMEOUT_US;
    ESP_LOGI(TAG, "OUT3 armed; waiting for capture (%d ms timeout)", CAPTURE_TIMEOUT_US / 1000);
    return CAPTURE_OK;
}

capture_status_t capture_stop(void)
{
    if (!active && !faulted) {
        return CAPTURE_OK;
    }
    esp_err_t error = edge_capture_stop(receiver);
    faulted = error != ESP_OK;
    active = false;
    if (faulted) {
        ESP_LOGE(TAG, "Failed to stop OUT3: %s", esp_err_to_name(error));
        return CAPTURE_ERROR;
    }
    ESP_LOGD(TAG, "OUT3 stopped");
    return CAPTURE_OK;
}

static capture_status_t finish(edge_capture_result_t result, const edge_trace_t **output)
{
    active = false;
    switch (result) {
    case EDGE_CAPTURE_COMPLETE:
        *output = &trace;
        ESP_LOGI(TAG, "OUT3 complete: %u edges, %lu ticks at %u Hz", (unsigned)trace.edge_count,
                 (unsigned long)trace.duration_ticks, CAPTURE_CLOCK_HZ);
        return CAPTURE_OK;
    case EDGE_CAPTURE_TRUNCATED:
        ESP_LOGW(TAG, "OUT3 overflow: capacity %u symbols; capture discarded", CAPTURE_SYMBOL_CAPACITY);
        return CAPTURE_OVERFLOW;
    default:
        ESP_LOGE(TAG, "Invalid OUT3 capture: no signal recorded");
        return CAPTURE_ERROR;
    }
}

capture_status_t capture_poll(const edge_trace_t **output)
{
    *output = NULL;
    if (!active) {
        return CAPTURE_ERROR;
    }
    edge_capture_result_t result = edge_capture_take(receiver, &trace);
    if (result != EDGE_CAPTURE_PENDING) {
        return finish(result, output);
    }
    if (esp_timer_get_time() < deadline_us) {
        return CAPTURE_PENDING;
    }
    if (capture_stop() != CAPTURE_OK) {
        return CAPTURE_ERROR;
    }
    ESP_LOGW(TAG, "OUT3 timeout: no completed capture within %d ms", CAPTURE_TIMEOUT_US / 1000);
    return CAPTURE_TIMEOUT;
}
