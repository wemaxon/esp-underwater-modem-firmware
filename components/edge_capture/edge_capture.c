#include "edge_capture.h"

#include <stdlib.h>
#include <string.h>

#include "driver/rmt_rx.h"
#include "esp_check.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"

#define MEM_BLOCK_SYMBOLS 48U   /* one RMT memory block */
#define CHUNK_SYMBOLS     64U   /* RMT hands over received symbols in chunks of up to this size */

_Static_assert(sizeof(rmt_symbol_word_t) == sizeof(uint32_t), "RMT symbols are decoded as 32-bit words");
_Static_assert(EDGE_CAPTURE_READ_MIN_EDGES >= 2 * CHUNK_SYMBOLS, "A chunk decodes to up to two edges per symbol");

static const char *TAG = "EDGE_CAPTURE";

/* Buffered unit: received symbols of one segment, in order. */
typedef struct {
    int64_t segment_start_us;   /* device time of the segment's first edge */
    uint16_t symbol_count;
    bool segment_end;
    uint32_t symbols[CHUNK_SYMBOLS];
} chunk_t;

struct edge_capture {
    edge_capture_config_t config;
    rmt_channel_handle_t channel;
    rmt_receive_config_t receive;
    RingbufHandle_t chunks;
    volatile bool running;
    volatile bool overflowed;
    volatile int64_t segment_start_us;
    chunk_t staged;                         /* interrupt side */
    rmt_symbol_word_t symbols[CHUNK_SYMBOLS];
    edge_decoder_t decoder;                 /* reader side */
    bool segment_open;
};

static void on_first_edge(void *context)
{
    struct edge_capture *capture = context;
    capture->segment_start_us = esp_timer_get_time();
    gpio_intr_disable(capture->config.gpio);
}

static bool on_receive(rmt_channel_handle_t channel, const rmt_rx_done_event_data_t *event, void *context)
{
    struct edge_capture *capture = context;
    capture->staged.segment_start_us = capture->segment_start_us;
    capture->staged.symbol_count = (uint16_t)event->num_symbols;
    capture->staged.segment_end = event->flags.is_last;
    memcpy(capture->staged.symbols, event->received_symbols, event->num_symbols * sizeof(uint32_t));

    BaseType_t woken = pdFALSE;
    size_t size = offsetof(chunk_t, symbols) + event->num_symbols * sizeof(uint32_t);
    if (!capture->overflowed && xRingbufferSendFromISR(capture->chunks, &capture->staged, size, &woken) != pdTRUE) {
        capture->overflowed = true;
    }
    if (event->flags.is_last && capture->running) {
        /* Re-arm for the next segment. Both calls are allowed in interrupt context. */
        rmt_receive(channel, capture->symbols, sizeof(capture->symbols), &capture->receive);
        gpio_intr_enable(capture->config.gpio);
    }
    return woken == pdTRUE;
}

esp_err_t edge_capture_new(const edge_capture_config_t *config, edge_capture_handle_t *handle)
{
    struct edge_capture *capture = calloc(1, sizeof(*capture));
    ESP_RETURN_ON_FALSE(capture, ESP_ERR_NO_MEM, TAG, "Out of memory");
    capture->config = *config;
    capture->receive = (rmt_receive_config_t){
        .signal_range_min_ns = config->min_pulse_ns,
        .signal_range_max_ns = config->idle_timeout_ns,
        .flags.en_partial_rx = true,
    };
    capture->chunks = xRingbufferCreate(config->buffer_bytes, RINGBUF_TYPE_NOSPLIT);
    ESP_RETURN_ON_FALSE(capture->chunks, ESP_ERR_NO_MEM, TAG, "Out of memory");

    rmt_rx_channel_config_t channel = {
        .gpio_num = config->gpio,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = config->resolution_hz,
        .mem_block_symbols = MEM_BLOCK_SYMBOLS,
    };
    rmt_rx_event_callbacks_t callbacks = {.on_recv_done = on_receive};
    ESP_RETURN_ON_ERROR(rmt_new_rx_channel(&channel, &capture->channel), TAG, "Failed to create RMT RX channel");
    ESP_RETURN_ON_ERROR(rmt_rx_register_event_callbacks(capture->channel, &callbacks, capture), TAG, "Failed to register RMT callback");
    ESP_RETURN_ON_ERROR(rmt_enable(capture->channel), TAG, "Failed to enable RMT RX channel");

    esp_err_t error = gpio_install_isr_service(0);
    ESP_RETURN_ON_FALSE(error == ESP_OK || error == ESP_ERR_INVALID_STATE, error, TAG, "Failed to install GPIO ISR service");
    ESP_RETURN_ON_ERROR(gpio_set_intr_type(config->gpio, GPIO_INTR_ANYEDGE), TAG, "Failed to configure edge interrupt");
    ESP_RETURN_ON_ERROR(gpio_isr_handler_add(config->gpio, on_first_edge, capture), TAG, "Failed to add edge interrupt");
    gpio_intr_disable(config->gpio);

    ESP_LOGI(TAG, "GPIO %d: %lu Hz, %lu ns glitch filter, %lu us idle limit", config->gpio,
             (unsigned long)config->resolution_hz, (unsigned long)config->min_pulse_ns,
             (unsigned long)(config->idle_timeout_ns / 1000));
    *handle = capture;
    return ESP_OK;
}

static void discard_buffered(edge_capture_handle_t capture)
{
    size_t size;
    void *item;
    while ((item = xRingbufferReceive(capture->chunks, &size, 0))) {
        vRingbufferReturnItem(capture->chunks, item);
    }
}

esp_err_t edge_capture_start(edge_capture_handle_t capture)
{
    discard_buffered(capture);
    capture->overflowed = false;
    capture->segment_open = false;
    capture->running = true;
    gpio_intr_enable(capture->config.gpio);
    return rmt_receive(capture->channel, capture->symbols, sizeof(capture->symbols), &capture->receive);
}

esp_err_t edge_capture_stop(edge_capture_handle_t capture)
{
    capture->running = false;
    gpio_intr_disable(capture->config.gpio);
    ESP_RETURN_ON_ERROR(rmt_disable(capture->channel), TAG, "Failed to stop RMT RX");
    discard_buffered(capture);
    return rmt_enable(capture->channel);
}

size_t edge_capture_read(edge_capture_handle_t capture, edge_t *edges, size_t capacity)
{
    const uint32_t ns_per_tick = 1000000000U / capture->config.resolution_hz;
    size_t count = 0;
    size_t size;
    chunk_t *chunk;
    while (capacity - count >= 2 * CHUNK_SYMBOLS && (chunk = xRingbufferReceive(capture->chunks, &size, 0))) {
        if (!capture->segment_open) {
            edge_decoder_start(&capture->decoder, ns_per_tick);
            capture->segment_open = true;
        }
        size_t decoded = edge_decoder_feed(&capture->decoder, chunk->symbols, chunk->symbol_count, edges + count);
        for (size_t i = count; i < count + decoded; ++i) {
            edges[i].time_ns += chunk->segment_start_us * 1000;
        }
        count += decoded;
        capture->segment_open = !chunk->segment_end;
        vRingbufferReturnItem(capture->chunks, chunk);
    }
    return count;
}

bool edge_capture_overflowed(edge_capture_handle_t capture)
{
    return capture->overflowed;
}
