#pragma once

#include "driver/rmt_tx.h"
#include "driver/rmt_rx.h"
#include "tuss4470.h"

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"


#define BURST_RMT_RESOLUTION_HZ     20000000U
#define RECEIVE_RMT_RESOLUTION_HZ   TUSS4470_RX_CLOCK_HZ


typedef struct {
    rmt_channel_handle_t tx_channel;
    rmt_channel_handle_t rx_channel;
    rmt_encoder_handle_t rmt_encoder;
    QueueHandle_t rx_done_queue;
    rmt_symbol_word_t rx_symbols[TUSS4470_RX_SYMBOL_CAPACITY];
} tuss4470_rmt_t;


esp_err_t tuss4470_rmt_init(tuss4470_rmt_t *tuss4470_rmt, gpio_num_t io2_io_num, gpio_num_t out3_io_num);
esp_err_t tuss4470_rmt_receive_start(tuss4470_rmt_t *tuss4470_rmt);
esp_err_t tuss4470_rmt_receive_wait(tuss4470_rmt_t *tuss4470_rmt, const rmt_symbol_word_t **symbols, size_t *num_symbols, uint32_t timeout_ms);
