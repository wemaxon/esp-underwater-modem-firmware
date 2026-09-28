#include "edge_capture.h"

#include <stdlib.h>

#include "driver/rmt_rx.h"
#include "esp_check.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

#define MEM_BLOCK_SYMBOLS 48U   /* one RMT memory block */

static const char *TAG = "EDGE_CAPTURE";

struct edge_capture {
    edge_capture_config_t config;
    rmt_channel_handle_t channel;
    QueueHandle_t done;         /* symbol count of each finished capture */
    rmt_symbol_word_t symbols[];
};

_Static_assert(sizeof(rmt_symbol_word_t) == sizeof(uint32_t), "RMT symbols are decoded as 32-bit words");

static bool on_receive_done(rmt_channel_handle_t channel, const rmt_rx_done_event_data_t *event, void *user_data)
{
    struct edge_capture *capture = user_data;
    size_t symbol_count = event->num_symbols;
    BaseType_t woken = pdFALSE;
    xQueueOverwriteFromISR(capture->done, &symbol_count, &woken);
    return woken == pdTRUE;
}

esp_err_t edge_capture_new(const edge_capture_config_t *config, edge_capture_handle_t *handle)
{
    struct edge_capture *capture = calloc(1, sizeof(*capture) + config->symbol_capacity * sizeof(rmt_symbol_word_t));
    ESP_RETURN_ON_FALSE(capture, ESP_ERR_NO_MEM, TAG, "Out of memory");
    capture->config = *config;
    capture->done = xQueueCreate(1, sizeof(size_t));
    ESP_RETURN_ON_FALSE(capture->done, ESP_ERR_NO_MEM, TAG, "Out of memory");

    rmt_rx_channel_config_t channel = {
        .gpio_num = config->gpio,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = config->resolution_hz,
        .mem_block_symbols = MEM_BLOCK_SYMBOLS,
    };
    rmt_rx_event_callbacks_t callbacks = {.on_recv_done = on_receive_done};
    ESP_RETURN_ON_ERROR(rmt_new_rx_channel(&channel, &capture->channel), TAG, "Failed to create RMT RX channel");
    ESP_RETURN_ON_ERROR(rmt_rx_register_event_callbacks(capture->channel, &callbacks, capture), TAG, "Failed to register RMT callback");
    ESP_RETURN_ON_ERROR(rmt_enable(capture->channel), TAG, "Failed to enable RMT RX channel");

    ESP_LOGI(TAG, "GPIO %d: %lu Hz, %u symbols, %lu ns glitch filter, %lu us idle limit", config->gpio,
             (unsigned long)config->resolution_hz, (unsigned)config->symbol_capacity,
             (unsigned long)config->min_pulse_ns, (unsigned long)(config->idle_timeout_ns / 1000));
    *handle = capture;
    return ESP_OK;
}

esp_err_t edge_capture_start(edge_capture_handle_t capture)
{
    rmt_receive_config_t receive = {
        .signal_range_min_ns = capture->config.min_pulse_ns,
        .signal_range_max_ns = capture->config.idle_timeout_ns,
    };
    xQueueReset(capture->done);
    return rmt_receive(capture->channel, capture->symbols, capture->config.symbol_capacity * sizeof(rmt_symbol_word_t), &receive);
}

esp_err_t edge_capture_stop(edge_capture_handle_t capture)
{
    ESP_RETURN_ON_ERROR(rmt_disable(capture->channel), TAG, "Failed to stop RMT RX");
    xQueueReset(capture->done);
    return rmt_enable(capture->channel);
}

edge_capture_result_t edge_capture_take(edge_capture_handle_t capture, edge_trace_t *trace)
{
    size_t symbol_count;
    if (xQueueReceive(capture->done, &symbol_count, 0) != pdTRUE) {
        return EDGE_CAPTURE_PENDING;
    }
    edge_trace_status_t status = edge_trace_decode_rmt((const uint32_t *)capture->symbols, symbol_count, trace);
    if (status == EDGE_TRACE_EMPTY) {
        return EDGE_CAPTURE_EMPTY;
    }
    if (status == EDGE_TRACE_FULL || symbol_count >= capture->config.symbol_capacity) {
        return EDGE_CAPTURE_TRUNCATED;
    }
    return EDGE_CAPTURE_COMPLETE;
}
