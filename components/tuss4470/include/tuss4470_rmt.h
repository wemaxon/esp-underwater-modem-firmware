#pragma once


#include "driver/rmt_tx.h"


#define BURST_RMT_RESOLUTION_HZ     20000000U



esp_err_t tuss4470_rmt_init(rmt_channel_handle_t *rmt_tx_channel, rmt_encoder_handle_t *rmt_encoder, gpio_num_t io2_io_num);