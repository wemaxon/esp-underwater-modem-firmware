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

typedef enum {
    TUSS4470_DEV_STATE_LISTEN,
    TUSS4470_DEV_STATE_BURST,
    TUSS4470_DEV_STATE_STANDBY,
    TUSS4470_DEV_STATE_SLEEP
} tuss4470_dev_state_t;

typedef union {
    uint8_t raw;

    struct {
        uint8_t dev_state     : 2;
        uint8_t ee_crc_flt    : 1;
        uint8_t drv_pulse_flt : 1;
        uint8_t pulse_num_flt : 1;
        uint8_t vdrv_ready    : 1;
        uint8_t reserved      : 2;
    };
} tuss4470_status_t;

esp_err_t tuss4470_init(tuss4470_config_t *config);
esp_err_t tuss4470_get_status(tuss4470_status_t *status);
void tuss4470_log_status(tuss4470_status_t *status);
uint8_t tuss4470_has_fault(tuss4470_status_t *status);
