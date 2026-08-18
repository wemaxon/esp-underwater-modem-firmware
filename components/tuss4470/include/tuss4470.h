#pragma once

#include "esp_err.h"
#include "driver/spi_master.h"


typedef struct {
    spi_host_device_t host_id;
    int spics_io_num;
    int io1_io_num;
    int io2_io_num;
    int out3_io_num;
    int out4_io_num;
    int vout_io_num;
} tuss4470_config_t;


esp_err_t tuss4470_init(tuss4470_config_t *config);