#pragma once

#include "esp_err.h"
#include "driver/spi_master.h"


#define TUSS4470_STATUS_


typedef struct {
    spi_host_device_t host_id;
    int spics_io_num;
    int io1_io_num;
    int io2_io_num;
    int out3_io_num;
    int out4_io_num;
    int vout_io_num;
} tuss4470_config_t;

typedef enum {
    TUSS4470_DEV_STATE_LISTEN,
    TUSS4470_DEV_STATE_BURST,
    TUSS4470_DEV_STATE_STANDBY,
    TUSS4470_DEV_STATE_SLEEP
} tuss4470_dev_state_t;


typedef union {
    uint32_t value;
    struct {
        uint32_t dev_state  : 2;
        uint32_t ee_crc_flt : 1;
        uint32_t drv_pulse_flt : 1;
        uint32_t pulse_num_flt : 1;
    };
} tuss4470_status_t;

esp_err_t tuss4470_init(tuss4470_config_t *config);
