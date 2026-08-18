#pragma once

#include <stdint.h>

#include "driver/spi_master.h"

typedef union {
    uint16_t raw;

    struct {
        uint16_t payload                     : 8;
        uint16_t parity                      : 1;
        uint16_t status                      : 6;
        uint16_t previous_frame_parity_error : 1;
    };
} tuss4470_spi_response_t;

uint16_t tuss4470_spi_set_parity(uint16_t frame);
esp_err_t tuss4470_spi_write_register(spi_device_handle_t spi, uint8_t address, uint8_t data, tuss4470_spi_response_t *response);
esp_err_t tuss4470_spi_read_register(spi_device_handle_t spi, uint8_t address, tuss4470_spi_response_t *response);
