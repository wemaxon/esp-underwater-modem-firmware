#include "capture.h"

#include "esp_timer.h"
#include "esp_log.h"
#include "tuss4470.h"

static bool active;
static bool faulted;
static int64_t deadline;
static capture_result_t result;
static const char *TAG = "CAPTURE";

uint32_t capture_clock_hz(void)
{
    return TUSS4470_RX_CLOCK_HZ;
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
    esp_err_t error = tuss4470_receive_start();
    if (error != ESP_OK) {
        ESP_LOGE(TAG, "Failed to arm OUT3: %s", esp_err_to_name(error));
        return CAPTURE_ERROR;
    }
    active = true;
    deadline = esp_timer_get_time() + 2000000;
    ESP_LOGI(TAG, "OUT3 armed; waiting for capture (2000 ms timeout)");
    return CAPTURE_OK;
}

capture_status_t capture_stop(void)
{
    if (!active && !faulted) {
        return CAPTURE_OK;
    }
    esp_err_t error = tuss4470_receive_stop();
    faulted = error != ESP_OK;
    active = false;
    if (faulted) {
        ESP_LOGE(TAG, "Failed to stop OUT3: %s", esp_err_to_name(error));
    } else {
        ESP_LOGD(TAG, "OUT3 stopped");
    }
    return faulted ? CAPTURE_ERROR : CAPTURE_OK;
}

static capture_status_t convert(const tuss4470_rx_capture_t *raw)
{
    if (!raw->num_symbols) {
        return CAPTURE_ERROR;
    }
    if (raw->num_symbols >= TUSS4470_RX_SYMBOL_CAPACITY) {
        return CAPTURE_OVERFLOW;
    }
    result.duration_ticks = 0;
    result.edge_count = 0;
    bool level = false;
    for (size_t segment = 0; segment < 2 * raw->num_symbols; ++segment) {
        uint32_t symbol = raw->symbols[segment / 2].val;
        unsigned shift = (segment % 2) * 16;
        uint32_t ticks = (symbol >> shift) & 0x7fff;
        bool next_level = (symbol >> (shift + 15)) & 1;
        if (!ticks) {
            break;
        }
        if (!result.duration_ticks) {
            result.initial_high = next_level;
        } else if (next_level != level) {
            result.edges[result.edge_count++] = result.duration_ticks;
        }
        level = next_level;
        result.duration_ticks += ticks;
    }
    return result.duration_ticks ? CAPTURE_OK : CAPTURE_ERROR;
}

capture_status_t capture_poll(const capture_result_t **output)
{
    *output = NULL;
    if (!active) {
        return CAPTURE_ERROR;
    }
    tuss4470_rx_capture_t raw;
    esp_err_t error = tuss4470_receive_wait(&raw, 0);
    if (error == ESP_OK) {
        active = false;
        capture_status_t status = convert(&raw);
        if (status == CAPTURE_OK) {
            *output = &result;
            ESP_LOGI(TAG, "OUT3 complete: %u symbols, %u edges, %lu ticks at %lu Hz", (unsigned)raw.num_symbols, result.edge_count, (unsigned long)result.duration_ticks, (unsigned long)capture_clock_hz());
        } else if (status == CAPTURE_OVERFLOW) {
            ESP_LOGW(TAG, "OUT3 overflow: %u symbols, capacity %u; capture discarded", (unsigned)raw.num_symbols, TUSS4470_RX_SYMBOL_CAPACITY);
        } else {
            ESP_LOGE(TAG, "Invalid OUT3 capture: %u symbols", (unsigned)raw.num_symbols);
        }
        return status;
    }
    if (error == ESP_ERR_TIMEOUT && esp_timer_get_time() < deadline) {
        return CAPTURE_PENDING;
    }
    if (capture_stop() != CAPTURE_OK) {
        return CAPTURE_ERROR;
    }
    if (error == ESP_ERR_TIMEOUT) {
        ESP_LOGW(TAG, "OUT3 timeout: no completed capture within 2000 ms");
        return CAPTURE_TIMEOUT;
    }
    ESP_LOGE(TAG, "Failed to read OUT3: %s", esp_err_to_name(error));
    return CAPTURE_ERROR;
}
