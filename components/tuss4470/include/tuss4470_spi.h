#pragma once

#include "driver/spi_master.h"

uint16_t tuss4470_spi_set_parity(uint16_t frame);
esp_err_t tuss4470_spi_write_register(spi_device_handle_t spi, uint8_t address, uint8_t data);
esp_err_t tuss4470_spi_read_register(spi_device_handle_t spi, uint8_t address, uint8_t *data);