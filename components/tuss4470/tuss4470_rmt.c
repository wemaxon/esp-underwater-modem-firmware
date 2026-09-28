#include "tuss4470_rmt.h"

#include "esp_check.h"
#include "esp_log.h"

static const char* TAG = "TUSS4470_RMT";


static bool rx_done_callback(rmt_channel_handle_t channel, const rmt_rx_done_event_data_t *event, void *user_data){
    (void)channel;

    BaseType_t task_woken = pdFALSE;
    xQueueSendFromISR(user_data, event, &task_woken);
    return task_woken == pdTRUE;
}

esp_err_t tuss4470_rmt_receive_start(tuss4470_rmt_t *tuss4470_rmt){
    ESP_RETURN_ON_FALSE(tuss4470_rmt != NULL, ESP_ERR_INVALID_ARG, TAG, "RMT context is NULL");
    ESP_RETURN_ON_FALSE(tuss4470_rmt->rx_channel != NULL, ESP_ERR_INVALID_STATE, TAG, "RMT RX is not initialized");
    ESP_RETURN_ON_FALSE(tuss4470_rmt->rx_done_queue != NULL, ESP_ERR_INVALID_STATE, TAG, "RMT RX queue is not initialized");

    rmt_receive_config_t rx_config = {
        .signal_range_min_ns = 1000,
        .signal_range_max_ns = 20000000,
    };

    xQueueReset(tuss4470_rmt->rx_done_queue);

    ESP_RETURN_ON_ERROR(rmt_receive(tuss4470_rmt->rx_channel, tuss4470_rmt->rx_symbols, sizeof(tuss4470_rmt->rx_symbols), &rx_config), TAG, "Failed to start RMT RX");
    return ESP_OK;
}

esp_err_t tuss4470_rmt_receive_wait(tuss4470_rmt_t *tuss4470_rmt, const rmt_symbol_word_t **symbols, size_t *num_symbols, uint32_t timeout_ms){
    ESP_RETURN_ON_FALSE(tuss4470_rmt != NULL, ESP_ERR_INVALID_ARG, TAG, "RMT context is NULL");
    ESP_RETURN_ON_FALSE(symbols != NULL, ESP_ERR_INVALID_ARG, TAG, "symbols is NULL");
    ESP_RETURN_ON_FALSE(num_symbols != NULL, ESP_ERR_INVALID_ARG, TAG, "num_symbols is NULL");
    ESP_RETURN_ON_FALSE(tuss4470_rmt->rx_done_queue != NULL, ESP_ERR_INVALID_STATE, TAG, "RMT RX queue is not initialized");

    rmt_rx_done_event_data_t event = {0};
    if (xQueueReceive(tuss4470_rmt->rx_done_queue, &event, pdMS_TO_TICKS(timeout_ms)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    *symbols = event.received_symbols;
    *num_symbols = event.num_symbols;
    return ESP_OK;
}

esp_err_t tuss4470_rmt_init(tuss4470_rmt_t *tuss4470_rmt, gpio_num_t io2_io_num, gpio_num_t out3_io_num){
    ESP_RETURN_ON_FALSE(tuss4470_rmt != NULL, ESP_ERR_INVALID_ARG, TAG, "RMT context is NULL");

    rmt_tx_channel_config_t tx_config = {
        .gpio_num = io2_io_num,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = BURST_RMT_RESOLUTION_HZ,
        .mem_block_symbols = 64,
        .trans_queue_depth = 1,
        .flags.init_level = 1,
    };
    
    ESP_RETURN_ON_ERROR(rmt_new_tx_channel(&tx_config, &(tuss4470_rmt->tx_channel)), TAG, "Failed to create rmt tx channel");

    rmt_copy_encoder_config_t encoder_config = {};
    ESP_RETURN_ON_ERROR(rmt_new_copy_encoder(&encoder_config, &(tuss4470_rmt->rmt_encoder)), TAG, "Failed to create rmt copy encoder");


    rmt_rx_channel_config_t rx_config = {
        .gpio_num = out3_io_num,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = RECEIVE_RMT_RESOLUTION_HZ,
        .mem_block_symbols = 48,
        .intr_priority = 0,
    };
    ESP_RETURN_ON_ERROR(rmt_new_rx_channel(&rx_config, &(tuss4470_rmt->rx_channel)), TAG, "Failed to create rmt rx channel");

    tuss4470_rmt->rx_done_queue = xQueueCreate(1, sizeof(rmt_rx_done_event_data_t));
    ESP_RETURN_ON_FALSE(tuss4470_rmt->rx_done_queue != NULL, ESP_ERR_NO_MEM, TAG, "Failed to create RMT RX queue");

    rmt_rx_event_callbacks_t callbacks = {
        .on_recv_done = rx_done_callback,
    };
    ESP_RETURN_ON_ERROR(rmt_rx_register_event_callbacks(tuss4470_rmt->rx_channel, &callbacks, tuss4470_rmt->rx_done_queue), TAG, "Failed to register RMT RX callback");

    ESP_RETURN_ON_ERROR(rmt_enable(tuss4470_rmt->tx_channel), TAG, "Failed to enable rmt tx channel");
    ESP_RETURN_ON_ERROR(rmt_enable(tuss4470_rmt->rx_channel), TAG, "Failed to enable rmt rx channel");
    ESP_LOGI(TAG, "OUT3 RX: GPIO %d, %u Hz, %u symbols, 1 us glitch filter, 20 ms idle limit", out3_io_num, RECEIVE_RMT_RESOLUTION_HZ, TUSS4470_RX_SYMBOL_CAPACITY);
    ESP_LOGI(TAG, "IO2 TX: GPIO %d, %u Hz clock", io2_io_num, BURST_RMT_RESOLUTION_HZ);
    return ESP_OK;
}
