#include "tuss4470_rmt.h"

#include "esp_check.h"
#include "esp_log.h"



static const char* TAG = "TUSS4470_RMT";

esp_err_t tuss4470_rmt_init(rmt_channel_handle_t *rmt_tx_channel, rmt_encoder_handle_t *rmt_encoder, gpio_num_t io2_io_num){
    rmt_tx_channel_config_t channel_config = {
        .gpio_num = io2_io_num,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = BURST_RMT_RESOLUTION_HZ,
        .mem_block_symbols = 64,
        .trans_queue_depth = 1,
        .flags.init_level = 1,
    };
    
    ESP_RETURN_ON_ERROR(rmt_new_tx_channel(&channel_config, rmt_tx_channel), TAG, "Failed to create rmt rx channel");

    rmt_copy_encoder_config_t encoder_config = {};
    ESP_RETURN_ON_ERROR(rmt_new_copy_encoder(&encoder_config, rmt_encoder), TAG, "Failed to create rmt copy encoder");
    ESP_RETURN_ON_ERROR(rmt_enable(*rmt_tx_channel), TAG, "Failed to enable rmt tx channel");

    return ESP_OK;
}