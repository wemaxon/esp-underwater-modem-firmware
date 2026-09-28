#pragma once

#include "esp_err.h"
#include "driver/rmt_types.h"
#include "driver/spi_master.h"

#define TUSS4470_RX_SYMBOL_CAPACITY 512U
#define TUSS4470_RX_CLOCK_HZ        1000000U

#define TUSS4470_TX_MIN_HZ          40000U
#define TUSS4470_TX_MAX_HZ          1000000U
#define TUSS4470_TX_MAX_CYCLES      255U

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
    TUSS4470_DEV_STATE_LISTEN = 0x00,
    TUSS4470_DEV_STATE_BURST = 0x01,
    TUSS4470_DEV_STATE_STANDBY = 0x02,
    TUSS4470_DEV_STATE_SLEEP = 0x03
} tuss4470_dev_state_t;

typedef enum {
    TUSS4470_IO_MODE_0 = 0x00,
    TUSS4470_IO_MODE_1 = 0x01,
    TUSS4470_IO_MODE_2 = 0x02,
    TUSS4470_IO_MODE_3 = 0x03
} tuss4470_io_mode_t;

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

typedef struct {
    const rmt_symbol_word_t *symbols;
    size_t num_symbols;
} tuss4470_rx_capture_t;


esp_err_t tuss4470_init(tuss4470_config_t *config);
esp_err_t tuss4470_get_status(tuss4470_status_t *status);
void tuss4470_log_status(tuss4470_status_t *status);
bool tuss4470_has_fault(tuss4470_status_t *status);
esp_err_t tuss4470_set_io_mode(tuss4470_io_mode_t io_mode);
esp_err_t tuss4470_set_vdrv(bool enabled);
esp_err_t tuss4470_wait_vdrv_ready(uint32_t timeout_ms);

esp_err_t tuss4470_send_burst(uint32_t frequency_hz, uint16_t cycles);
esp_err_t tuss4470_receive_start(void);
esp_err_t tuss4470_receive_stop(void);
esp_err_t tuss4470_receive_wait(tuss4470_rx_capture_t *capture, uint32_t timeout_ms);
